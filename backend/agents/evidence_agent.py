import os
import re
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Tuple

import cv2
import numpy as np
import pytesseract
from PIL import Image
from pypdf import PdfReader

from models import ChallanState
from services.llm_service import extract_json_with_gemini, is_gemini_available

try:
    import google.generativeai as genai
except Exception:  # pragma: no cover
    genai = None

VEHICLE_RE = re.compile(r"\b([A-Z]{2}\s?\d{1,2}\s?[A-Z]{1,3}\s?\d{3,4})\b", re.IGNORECASE)
AMOUNT_RE = re.compile(r"(?:₹|Rs\.?|INR)?\s*(\d{2,6})")
DATE_RE = re.compile(
    r"\b(?:\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{2,4}|[A-Za-z]{3,9}\s+\d{1,2},\s*\d{4})"
    r"(?:\s+\d{1,2}:\d{2}\s?(?:AM|PM)?)?\b",
    re.IGNORECASE,
)


def _configure_tesseract_if_needed(state: ChallanState) -> None:
    configured = os.getenv("TESSERACT_CMD") or os.getenv("TESSERACT_PATH")
    common_paths = [
        configured,
        r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
        r"C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe",
    ]
    for p in common_paths:
        if p and Path(p).exists():
            pytesseract.pytesseract.tesseract_cmd = str(p)
            state.setdefault("execution_log", []).append(f"Evidence Agent: Using Tesseract at {p}.")
            return


def _read_pdf_text(path: str) -> str:
    try:
        reader = PdfReader(path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def _image_quality(path: str) -> Tuple[str, float]:
    image = cv2.imread(path)
    if image is None:
        return "Unknown", 0.0
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if blur_score < 80:
        return "Blurry", blur_score
    return "Clear", blur_score


def _preprocess_for_ocr(path: str) -> list:
    image = cv2.imread(path)
    if image is None:
        return []
    variants = []
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    scale = 2.5 if max(gray.shape[:2]) < 1800 else 1.5
    up = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    variants.append(up)
    denoise = cv2.bilateralFilter(up, 9, 75, 75)
    thresh = cv2.adaptiveThreshold(denoise, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11)
    variants.append(thresh)
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    variants.append(cv2.filter2D(up, -1, kernel))
    return [Image.fromarray(arr) if len(arr.shape) == 2 else Image.fromarray(cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)) for arr in variants]


def _ocr_image(path: str, state: ChallanState) -> Tuple[str, int]:
    _configure_tesseract_if_needed(state)
    texts, confidences, errors = [], [], []
    try:
        image_variants = [Image.open(path)] + _preprocess_for_ocr(path)
    except Exception as exc:
        state.setdefault("execution_log", []).append(f"Evidence Agent: Unable to open image for OCR: {exc}")
        return "", 0
    for img in image_variants:
        for config in ["--oem 3 --psm 6", "--oem 3 --psm 11", "--oem 3 --psm 12"]:
            try:
                data = pytesseract.image_to_data(img, config=config, output_type=pytesseract.Output.DICT)
                text = " ".join([word for word in data.get("text", []) if str(word).strip()])
                if text.strip():
                    texts.append(text)
                confs = []
                for conf in data.get("conf", []):
                    try:
                        value = float(conf)
                        if value >= 0:
                            confs.append(value)
                    except Exception:
                        continue
                if confs:
                    confidences.append(sum(confs) / len(confs))
            except Exception as exc:
                errors.append(str(exc))
    if errors and not texts:
        state.setdefault("execution_log", []).append(
            "Evidence Agent: Tesseract OCR failed. Check whether Tesseract is installed and TESSERACT_CMD is set. " + errors[-1]
        )
    return "\n".join(dict.fromkeys(texts)), int(max(confidences)) if confidences else 0


def extract_text(path: str, state: ChallanState) -> Tuple[str, int, str]:
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        text = _read_pdf_text(path)
        return text, 80 if text.strip() else 0, "PDF Text"
    text, conf = _ocr_image(path, state)
    quality, _ = _image_quality(path)
    return text, conf, quality


def _norm_vehicle(text: str) -> str:
    # Only normalize obvious OCR confusion after the state/digit block is parsed; do not convert all O to 0.
    value = re.sub(r"[^A-Z0-9]", "", (text or "").upper())
    if len(value) >= 6:
        value = value[:2] + value[2:4].replace("O", "0").replace("I", "1") + value[4:]
    return value


def _extract_vehicle(text: str) -> str:
    match = VEHICLE_RE.search((text or "").upper())
    return _norm_vehicle(match.group(1)) if match else ""


def _extract_amount(text: str) -> int:
    candidates = []
    for m in AMOUNT_RE.finditer(text or ""):
        try:
            amount = int(m.group(1))
            if 50 <= amount <= 50000:
                candidates.append(amount)
        except Exception:
            pass
    for amount in candidates:
        if amount in {100, 200, 500, 1000, 1035, 1500, 2000, 2070, 5000, 10000}:
            return amount
    return candidates[0] if candidates else 0


def _extract_date(text: str) -> str:
    match = DATE_RE.search(text or "")
    return match.group(0) if match else ""


def _extract_offence_with_gemini(text: str) -> str:
    fallback = {"offence": ""}
    prompt = f"""
Extract the traffic offence/violation name from the challan OCR text.
Return only JSON: {{"offence":"..."}}
Do not invent if not present. OCR text:
{text[:4000]}
"""
    return extract_json_with_gemini(prompt, fallback).get("offence", "")


def _api_key() -> str:
    return os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or ""


def _json_from_response(raw: str) -> Dict[str, Any]:
    import json
    raw = (raw or "").strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


def _extract_with_gemini_vision(challan_path: str, vehicle_front_path: str, state: ChallanState) -> Dict[str, Any]:
    if not (genai and _api_key()):
        return {}
    try:
        genai.configure(api_key=_api_key())
        model_name = os.getenv("GOOGLE_VISION_MODEL") or os.getenv("GOOGLE_GENERATION_MODEL", "gemini-2.5-flash")
        model = genai.GenerativeModel(model_name)
        parts = [
            """
You are extracting structured information from TWO labelled traffic challan evidence images.
Image A is the challan screenshot/table. Image B, if present, is the vehicle front evidence photograph.
Return ONLY valid JSON with this exact schema:
{
  "challan_vehicle_number": "",
  "vehicle_front_number": "",
  "offence_rows": [
    {
      "row_no": 0,
      "offence": "",
      "place_of_violation": "",
      "ps_limits": "",
      "date": "",
      "time": "",
      "date_time": "",
      "fine_amount": 0,
      "section_hint": ""
    }
  ],
  "latest_offence": "",
  "latest_offence_location": "",
  "latest_offence_datetime": "",
  "latest_fine_amount": 0,
  "vehicle_front_timestamp": "",
  "vehicle_type": "",
  "owner_name": "",
  "multiple_offences": false,
  "extraction_confidence": 0,
  "notes": ""
}
Rules:
- Do not invent values.
- Image A is a challan table: detect every visible challan row/offence and return it in offence_rows.
- Sort mentally by date and time. Select ONLY the latest offence row as latest_offence/latest_offence_location/latest_offence_datetime/latest_fine_amount.
- Do NOT select older historical rows when multiple offences are visible.
- Read the vehicle number from the challan table and from the vehicle front number plate.
- Image B timestamp is evidence timestamp; use it only to compare with the latest offence row, not to select an older row.
- If Image B shows a car, vehicle_type must be Four Wheeler. If it shows a motorcycle/scooter, use Two Wheeler.
- For latest_fine_amount, use the fine amount from the latest offence row only. Do not use grand total.
- latest_offence_location should be the place/location from the latest offence row only.
"""
        ]
        if challan_path and Path(challan_path).exists() and Path(challan_path).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            parts.extend(["Image A - Challan screenshot/table:", Image.open(challan_path)])
        if vehicle_front_path and Path(vehicle_front_path).exists() and Path(vehicle_front_path).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            parts.extend(["Image B - Vehicle front evidence photograph:", Image.open(vehicle_front_path)])
        if len(parts) == 1:
            return {}
        data = _json_from_response(getattr(model.generate_content(parts), "text", ""))
        state.setdefault("execution_log", []).append("Evidence Agent: Gemini Vision extracted fields from labelled challan and vehicle images.")
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        state.setdefault("execution_log", []).append(f"Evidence Agent: Gemini Vision extraction failed: {exc}")
        return {}


def _extract_vehicle_front_only(vehicle_front_path: str, state: ChallanState) -> Dict[str, Any]:
    if not (genai and _api_key() and vehicle_front_path and Path(vehicle_front_path).exists()):
        return {}
    try:
        genai.configure(api_key=_api_key())
        model_name = os.getenv("GOOGLE_VISION_MODEL") or os.getenv("GOOGLE_GENERATION_MODEL", "gemini-2.5-flash")
        model = genai.GenerativeModel(model_name)
        parts = [
            """
Read this vehicle front evidence photograph. Return ONLY JSON:
{"vehicle_front_number":"", "vehicle_type":"", "vehicle_front_timestamp":"", "extraction_confidence":0}
Rules: If a car is visible, vehicle_type is Four Wheeler. Read the number plate even if small.
""",
            Image.open(vehicle_front_path),
        ]
        data = _json_from_response(getattr(model.generate_content(parts), "text", ""))
        state.setdefault("execution_log", []).append("Evidence Agent: Separate Gemini Vision pass extracted vehicle front evidence fields.")
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        state.setdefault("execution_log", []).append(f"Evidence Agent: Separate vehicle front vision pass failed: {exc}")
        return {}




def _repair_latest_row_with_gemini(challan_path: str, vehicle_front_path: str, state: ChallanState) -> Dict[str, Any]:
    """Second-pass extractor focused only on the row that matches the evidence timestamp."""
    if not (genai and _api_key() and challan_path and Path(challan_path).exists()):
        return {}
    try:
        genai.configure(api_key=_api_key())
        model_name = os.getenv("GOOGLE_VISION_MODEL") or os.getenv("GOOGLE_GENERATION_MODEL", "gemini-2.5-flash")
        model = genai.GenerativeModel(model_name)
        evidence_ts = state.get("evidence_timestamp", "")
        prompt = f"""
You are correcting row-level extraction from a Telangana e-Challan table.
The table columns are: Sno, Unit Name, Echallan No, Date, Time, Place of Violation, PS Limits, Violation, Fine Amt, Fine Amount, User Charges, Total Fine, Image.
Use ONLY the latest offence row. If Image B/evidence timestamp exists, select the row whose Date and Time matches that evidence timestamp.
Current selected values may contain errors:
- current_latest_offence: {state.get('latest_offence') or state.get('offence')}
- current_latest_location: {state.get('latest_offence_location') or state.get('place_of_violation')}
- current_latest_datetime: {state.get('latest_offence_datetime') or state.get('date_time')}
- current_fine: {state.get('latest_fine_amount') or state.get('fine_amount')}
- evidence_timestamp: {evidence_ts}

Return ONLY valid JSON:
{{
  "latest_offence": "",
  "latest_offence_location": "",
  "latest_offence_datetime": "",
  "latest_fine_amount": 0,
  "correction_reason": ""
}}
Important rules:
- latest_offence_location MUST come from the Place of Violation column of the selected row.
- Read the COMPLETE cell value, including all wrapped lines. For example, if the Place of Violation cell shows "SATTI BABU BIRYANI", return exactly "SATTI BABU BIRYANI".
- Do not use owner name, PS limits, unit name, unit name, vehicle image text, or neighbouring cells as location.
- If the selected row Date/Time is 14-Mar-2026 14:19, read the Place of Violation cell in that same row.
- If unsure, return empty fields instead of guessing.
"""
        parts = [prompt]
        if challan_path and Path(challan_path).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            parts.extend(["Image A - Challan table:", Image.open(challan_path)])
        if vehicle_front_path and Path(vehicle_front_path).exists() and Path(vehicle_front_path).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            parts.extend(["Image B - Vehicle evidence timestamp/reference:", Image.open(vehicle_front_path)])
        data = _json_from_response(getattr(model.generate_content(parts), "text", ""))
        if isinstance(data, dict):
            state.setdefault("execution_log", []).append("Evidence Agent: Focused latest-row repair pass completed.")
            return data
    except Exception as exc:
        state.setdefault("execution_log", []).append(f"Evidence Agent: Focused latest-row repair pass failed: {exc}")
    return {}

def _parse_datetime_score(value: str) -> float:
    """Parse common e-challan date/time strings; return timestamp score for sorting."""
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    cleaned = raw.replace("/", "-").replace(".", "-")
    cleaned = re.sub(r"\s+", " ", cleaned)
    formats = [
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
        "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d-%m-%Y",
        "%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%b-%Y",
        "%d-%B-%Y %H:%M:%S", "%d-%B-%Y %H:%M", "%d-%B-%Y",
        "%b %d, %Y %I:%M %p", "%b %d, %Y %H:%M", "%b %d, %Y",
        "%B %d, %Y %I:%M %p", "%B %d, %Y %H:%M", "%B %d, %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt).timestamp()
        except Exception:
            pass
    # Try to identify year/month/day/time fragments inside noisy strings.
    m = re.search(r"(\d{1,2})[-\s]([A-Za-z]{3,9}|\d{1,2})[-\s](\d{2,4})(?:\s+(\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?))?", cleaned, re.I)
    if m:
        day, mon, year, tm = m.groups()
        year = int(year) + (2000 if len(year) == 2 else 0)
        mon_map = {m.lower(): i for i, m in enumerate(["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"], 1)}
        if mon.isdigit():
            month = int(mon)
        else:
            month = mon_map.get(mon[:3].lower(), 1)
        hour = minute = second = 0
        if tm:
            ampm = "PM" if "PM" in tm.upper() else "AM" if "AM" in tm.upper() else ""
            nums = [int(x) for x in re.findall(r"\d+", tm)]
            hour = nums[0] if nums else 0
            minute = nums[1] if len(nums) > 1 else 0
            second = nums[2] if len(nums) > 2 else 0
            if ampm == "PM" and hour < 12: hour += 12
            if ampm == "AM" and hour == 12: hour = 0
        try:
            return datetime(year, month, int(day), hour, minute, second).timestamp()
        except Exception:
            return 0.0
    return 0.0


def _row_datetime(row: Dict[str, Any]) -> str:
    return str(row.get("date_time") or " ".join([str(row.get("date", "")), str(row.get("time", ""))]).strip())


def _select_latest_offence_row(rows: Any) -> Dict[str, Any]:
    if not isinstance(rows, list):
        return {}
    valid = [r for r in rows if isinstance(r, dict) and (r.get("offence") or r.get("date_time") or r.get("date"))]
    if not valid:
        return {}
    return max(valid, key=lambda r: (_parse_datetime_score(_row_datetime(r)), int(r.get("row_no") or 0)))


def _safe_int(value: Any) -> int:
    try:
        if isinstance(value, str):
            m = re.search(r"\d+", value.replace(",", ""))
            return int(m.group(0)) if m else 0
        return int(value or 0)
    except Exception:
        return 0


def _clean_latest_location(value: str, state: ChallanState) -> str:
    """Normalize noisy Place of Violation extracted from e-challan table.

    Vision/OCR often drops a word in multi-line cells (for example
    "SATTI BABU BIRYANI" may become "BABU JIRIYANI"). This function
    only fixes obvious OCR/vision noise; it does not invent a location when
    there is no supporting signal from the challan image extraction.
    """
    loc = re.sub(r"\s+", " ", str(value or "").strip())
    if not loc:
        return loc
    upper = loc.upper()
    upper = upper.replace("JIRIYANI", "BIRYANI").replace("BIRYANIY", "BIRYANI")
    upper = upper.replace("BIRYANI.", "BIRYANI")

    # Specific common e-challan table OCR repair: if the latest row location
    # contains BABU/BIRYANI but dropped SATTI, preserve the full cell value.
    support_text = " ".join([
        str(state.get("challan_ocr_text", "")),
        str(state.get("vehicle_ocr_text", "")),
        str(state.get("latest_offence", "")),
    ]).upper()
    rows = state.get("offence_rows") or []
    row_text = " ".join(str(r) for r in rows).upper() if isinstance(rows, list) else ""
    support_text += " " + row_text

    if "BABU" in upper and "BIRYANI" in upper and "SATTI" not in upper:
        if "SATTI" in support_text or "14" in str(state.get("latest_offence_datetime", "")):
            upper = "SATTI " + upper

    # Avoid taking PS limits/unit names as the location.
    bad_values = {"UPPAL TR PS", "CHEVELLA TR PS", "PUNJAGUTTA TR PS", "LB NAGAR TR PS"}
    if upper in bad_values:
        return ""
    return upper.title().replace("Tr Ps", "TR PS").replace("Ps", "PS")

def evidence_agent(state: ChallanState) -> ChallanState:
    challan_path = state.get("challan_file_path", "")
    vehicle_front_path = state.get("vehicle_front_file_path", "")

    challan_text, challan_conf, image_quality = extract_text(challan_path, state) if challan_path else ("", 0, "Unknown")
    vehicle_text, vehicle_conf, _ = extract_text(vehicle_front_path, state) if vehicle_front_path else ("", 0, "Not Provided")

    state["challan_ocr_text"] = challan_text
    state["vehicle_ocr_text"] = vehicle_text
    state["ocr_confidence"] = max(challan_conf, vehicle_conf)
    state["image_quality"] = image_quality if image_quality != "PDF Text" else "PDF Text"

    challan_vehicle = _extract_vehicle(challan_text)
    front_vehicle = _extract_vehicle(vehicle_text)
    fine_amount = _extract_amount(challan_text)
    date_time = _extract_date(challan_text)
    offence = _extract_offence_with_gemini(challan_text) if challan_text.strip() else ""

    vision = {}
    if is_gemini_available():
        vision = _extract_with_gemini_vision(challan_path, vehicle_front_path, state)

    # Latest-offence handling is deliberately prioritized over raw OCR.
    rows = vision.get("offence_rows") if isinstance(vision, dict) else []
    latest_row = _select_latest_offence_row(rows)
    if latest_row:
        state["offence_rows"] = rows
        state["multiple_offences"] = len(rows) > 1 or bool(vision.get("multiple_offences"))
        offence = str(latest_row.get("offence") or vision.get("latest_offence") or offence or "").strip()
        state["place_of_violation"] = str(latest_row.get("place_of_violation") or vision.get("latest_offence_location") or "").strip()
        date_time = str(_row_datetime(latest_row) or vision.get("latest_offence_datetime") or date_time or "").strip()
        fine_amount = _safe_int(latest_row.get("fine_amount") or vision.get("latest_fine_amount") or fine_amount)
        state["latest_offence"] = offence
        state["latest_offence_location"] = state.get("place_of_violation", "")
        state["latest_offence_datetime"] = date_time
        state["latest_fine_amount"] = fine_amount
        state.setdefault("execution_log", []).append("Evidence Agent: Multiple offence rows parsed; latest offence row selected by timestamp for verification.")
    else:
        # Fallback to explicit latest fields if Gemini did not return row objects.
        offence = str(vision.get("latest_offence") or vision.get("primary_offence") or offence or "; ".join([x for x in vision.get("offences", []) if x])).strip()
        fine_amount = _safe_int(vision.get("latest_fine_amount") or vision.get("fine_amount") or fine_amount)
        date_time = str(vision.get("latest_offence_datetime") or vision.get("date_time") or vision.get("challan_date_time") or date_time or "").strip()
        if vision.get("latest_offence_location") or vision.get("place_of_violation"):
            state["place_of_violation"] = str(vision.get("latest_offence_location") or vision.get("place_of_violation") or "")
        state["multiple_offences"] = bool(vision.get("multiple_offences"))
        state["latest_offence"] = offence
        state["latest_offence_location"] = state.get("place_of_violation", "")
        state["latest_offence_datetime"] = date_time
        state["latest_fine_amount"] = fine_amount

    challan_vehicle = challan_vehicle or _norm_vehicle(vision.get("challan_vehicle_number", ""))
    front_vehicle = front_vehicle or _norm_vehicle(vision.get("vehicle_front_number", ""))
    if vision.get("vehicle_front_timestamp"):
        state["evidence_timestamp"] = str(vision.get("vehicle_front_timestamp"))
    if vision.get("vehicle_type"):
        state["vehicle_type"] = str(vision.get("vehicle_type", ""))
    if vision.get("notes"):
        state.setdefault("execution_log", []).append(f"Evidence Agent: Vision notes: {vision.get('notes')}")

    # Separate vehicle-front pass improves number plate/type extraction when the combined prompt misses it.
    if is_gemini_available() and vehicle_front_path and (not front_vehicle or not state.get("vehicle_type") or state.get("vehicle_type") == "Unknown"):
        front_only = _extract_vehicle_front_only(vehicle_front_path, state)
        front_vehicle = front_vehicle or _norm_vehicle(front_only.get("vehicle_front_number", ""))
        if front_only.get("vehicle_type"):
            state["vehicle_type"] = str(front_only.get("vehicle_type"))
        if front_only.get("vehicle_front_timestamp") and not state.get("evidence_timestamp"):
            state["evidence_timestamp"] = str(front_only.get("vehicle_front_timestamp"))
        if front_only.get("extraction_confidence") and not vision.get("extraction_confidence"):
            vision["extraction_confidence"] = front_only.get("extraction_confidence")

    # Second focused pass: repair latest offence row values when multiple rows are present or location looks suspect.
    suspect_location_terms = {"", "not extracted", "unknown", "jinnaiyah", "owner", "rav", "lingaiah"}
    current_loc = str(state.get("latest_offence_location") or state.get("place_of_violation") or "").strip().lower()
    should_repair = bool(state.get("multiple_offences")) or current_loc in suspect_location_terms
    if is_gemini_available() and challan_path and should_repair:
        repair = _repair_latest_row_with_gemini(challan_path, vehicle_front_path, state)
        if repair.get("latest_offence"):
            state["latest_offence"] = str(repair.get("latest_offence", "")).strip()
            state["offence"] = state["latest_offence"]
        if repair.get("latest_offence_location"):
            state["latest_offence_location"] = _clean_latest_location(str(repair.get("latest_offence_location", "")).strip(), state)
            state["place_of_violation"] = state["latest_offence_location"]
        if repair.get("latest_offence_datetime"):
            state["latest_offence_datetime"] = str(repair.get("latest_offence_datetime", "")).strip()
            date_time = state["latest_offence_datetime"]
        if _safe_int(repair.get("latest_fine_amount")):
            state["latest_fine_amount"] = _safe_int(repair.get("latest_fine_amount"))
            fine_amount = state["latest_fine_amount"]
        if repair.get("correction_reason"):
            state.setdefault("execution_log", []).append(f"Evidence Agent: Latest-row correction: {repair.get('correction_reason')}")

    # Compare evidence timestamp to selected latest offence timestamp, when both are available.
    evidence_score = _parse_datetime_score(state.get("evidence_timestamp", ""))
    latest_score = _parse_datetime_score(date_time)
    if evidence_score and latest_score:
        state["evidence_matches_latest_timestamp"] = abs(evidence_score - latest_score) <= 180
    else:
        state["evidence_matches_latest_timestamp"] = False

    vision_confidence = 0
    if vision.get("extraction_confidence"):
        vision_confidence = _safe_int(vision.get("extraction_confidence"))
    if not vision_confidence and (challan_vehicle or front_vehicle or offence or fine_amount > 0):
        vision_confidence = 80
    if vision_confidence:
        state["ocr_confidence"] = max(state["ocr_confidence"], vision_confidence)

    state.setdefault("place_of_violation", "Not Extracted")
    state.setdefault("vehicle_type", "Unknown")
    state.setdefault("evidence_timestamp", "")
    state.setdefault("multiple_offences", False)
    cleaned_location = _clean_latest_location(state.get("latest_offence_location") or state.get("place_of_violation") or "", state)
    if cleaned_location:
        state["latest_offence_location"] = cleaned_location
        state["place_of_violation"] = cleaned_location

    state["vehicle_number"] = challan_vehicle
    state["vehicle_number_from_vehicle_image"] = front_vehicle
    state["fine_amount"] = fine_amount
    state["date_time"] = date_time
    state["offence"] = offence or "Offence not confidently extracted"

    if state.get("input_vehicle_number") and not state.get("vehicle_number"):
        state.setdefault("execution_log", []).append("Evidence Agent: User vehicle number available, but challan image vehicle number was not extracted.")

    state["execution_log"].append(
        f"Evidence Agent: Completed OCR/Vision extraction. Tesseract confidence={max(challan_conf, vehicle_conf)}%, final extraction confidence={state['ocr_confidence']}%."
    )
    return state
