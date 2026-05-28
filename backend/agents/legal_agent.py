import json
import re
from typing import Dict, Any, List, Tuple

from models import ChallanState
from services.llm_service import extract_json_with_gemini, generate_text, gemini_status
from services.rag_service import clean_legal_text


def _context_text(state: ChallanState) -> str:
    return "\n\n".join([
        f"Reference {idx}: {s.get('section')} | State DB: {s.get('state_db')} | Page: {s.get('page')}\n{clean_legal_text(s.get('summary', ''))}"
        for idx, s in enumerate(state.get("retrieved_sections", []), start=1)
    ])


def _remove_source_references(text: str) -> str:
    cleaned = clean_legal_text(text or "")
    cleaned = re.sub(r"\bSource\s*\d+\s*,?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\bReference\s*\d+\s*,?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\bchunk\s*id\s*[:#]?\s*\w+", "", cleaned, flags=re.I)
    return clean_legal_text(cleaned)


def _offence_kind(offence: str) -> str:
    low = (offence or "").lower()
    if any(k in low for k in ["helmet", "headgear", "194d", "129"]):
        return "helmet"
    if any(k in low for k in ["parking", "obstruction", "passageway", "carriageway", "no parking", "unauthor", "unauthoriz"]):
        return "parking"
    if any(k in low for k in ["dangerous", "184"]):
        return "dangerous"
    if any(k in low for k in ["speed", "over speed", "overspeed", "183"]):
        return "speed"
    if any(k in low for k in ["signal", "red light", "stop line"]):
        return "signal"
    return "general"


def _is_state_db(item: Dict[str, Any], selected_state: str) -> bool:
    db = (item.get("state_db") or "").lower()
    state = (selected_state or "").lower()
    if state == "ts":
        return "ts_db" in db or "telangana" in db
    if state == "ap":
        return "ap_db" in db or "andhra" in db
    if state == "ka":
        return "ka_db" in db or "karnataka" in db
    return False


def _numbers_from_text(text: str) -> List[int]:
    src = (text or "").lower().replace(",", "")
    word_map = {
        "one hundred": 100,
        "two hundred": 200,
        "five hundred": 500,
        "one thousand": 1000,
        "two thousand": 2000,
        "four thousand": 4000,
        "five thousand": 5000,
        "ten thousand": 10000,
    }
    nums = []
    for phrase, value in word_map.items():
        if phrase in src:
            nums.append(value)
    for m in re.finditer(r"(?:rs\.?|₹|rupees|fine|penalty)\s*(?:of|up to|not less than|may extend to|:)??\s*(\d{2,5})", src):
        nums.append(int(m.group(1)))
    return sorted(set(nums))


def _state_specific_fine(state: ChallanState, kind: str) -> Tuple[int, str]:
    """If selected state docs provide a directly relevant penalty, it is final.

    This does not invent a state penalty. It only returns an amount/range when a
    selected-state document retrieved by RAG contains offence keywords and a fine.
    """
    selected_state = state.get("selected_state", "")
    keywords = {
        "helmet": ["helmet", "headgear", "without helmet", "not wearing helmet", "194d", "129"],
        "parking": ["parking", "obstruction", "carriageway", "passageway", "park"],
        "speed": ["speed", "excessive speed", "over speeding", "183"],
        "dangerous": ["dangerous", "184"],
        "signal": ["signal", "red light", "stop line"],
    }.get(kind, [kind])
    for item in state.get("retrieved_sections", []) or []:
        if not _is_state_db(item, selected_state):
            continue
        text = clean_legal_text(item.get("summary", ""))
        low = text.lower()
        if not any(k in low for k in keywords):
            continue
        nums = _numbers_from_text(text)
        if nums:
            if len(nums) >= 2:
                return nums[0], f"₹{nums[0]}-₹{nums[-1]} (State rule/portal amount; state penalty preferred)"
            return nums[0], f"₹{nums[0]} (State rule/portal amount; state penalty preferred)"
    return 0, ""


def _amount_only_text(text: str, offence: str = "", context: str = "") -> str:
    """Convert verbose legal fine prose into report-friendly amount-only ranges.

    Important: this function is offence-aware. It avoids taking unrelated amounts
    from retrieved chunks such as Section 184 subsequent-offence values when the
    detected offence is helmet.
    """
    src = f"{text} {offence} {context}".lower()
    kind = _offence_kind(offence)
    parts = []

    if kind == "helmet":
        if "194d" in src or "protective headgear" in src or "helmet" in src:
            # Section 194D inserted by the 2019 Amendment: fine of one thousand rupees.
            if "one thousand" in src or "1000" in src:
                return "₹1000"
        nums = [n for n in _numbers_from_text(src) if n <= 2000]
        if nums:
            return f"₹{nums[0]}"
        return "Not conclusively identified"

    if kind == "parking":
        nums = _numbers_from_text(src)
        # Parking/obstruction retrieval often has Section 201 amendment. Prefer exact lower relevant penalty.
        if 500 in nums:
            return "₹500"
        if nums:
            if len(nums) >= 2:
                return f"₹{nums[0]}-₹{nums[-1]}"
            return f"₹{nums[0]}"
        return "Not conclusively identified"

    if kind == "speed":
        if "one thousand" in src and "two thousand" in src:
            return "₹1000-₹2000"
        nums = _numbers_from_text(src)
        if nums:
            return f"₹{nums[0]}-₹{nums[-1]}" if len(nums) >= 2 else f"₹{nums[0]}"
        return "Not conclusively identified"

    if kind == "dangerous" or kind == "signal":
        # Use first-offence range unless the detected offence itself says subsequent/repeat.
        offence_low = (offence or "").lower()
        if "subsequent" in offence_low or "repeat" in offence_low or "second" in offence_low:
            if "ten thousand" in src or "10000" in src:
                return "₹10000 (subsequent offence)"
        if "one thousand" in src and "five thousand" in src:
            return "₹1000-₹5000"
        nums = [n for n in _numbers_from_text(src) if n <= 5000]
        if nums:
            return f"₹{nums[0]}-₹{nums[-1]}" if len(nums) >= 2 else f"₹{nums[0]}"
        return "Not conclusively identified"

    nums = _numbers_from_text(src)
    if len(nums) >= 2:
        return f"₹{nums[0]}-₹{nums[-1]}"
    if len(nums) == 1:
        return f"₹{nums[0]}"
    return clean_legal_text(text or "Not conclusively identified")


def _fine_min(amount_text: str) -> int:
    nums = [int(x) for x in re.findall(r"\d{2,5}", (amount_text or "").replace(",", ""))]
    return min(nums) if nums else 0


def legal_compliance_agent(state: ChallanState) -> ChallanState:
    context = _context_text(state)
    offence_for_kind = state.get("latest_offence") or state.get("offence", "")
    kind = _offence_kind(offence_for_kind)
    fallback = {
        "expected_fine": 0,
        "expected_fine_text": "Not conclusively identified",
        "legal_analysis": "Legal analysis requires review. Retrieved context is available, but Gemini could not extract a definite fine from the context.",
        "offence": offence_for_kind,
    }
    prompt = f"""
You are a legal compliance assistant for Indian traffic challan verification.
Use ONLY the retrieved legal context below. Do not invent.

Selected State: {state.get('selected_state')}
Latest Offence Only: {offence_for_kind}
Latest Fine Amount: {state.get('fine_amount')}
Latest Place: {state.get('place_of_violation')}
Latest Date/Time: {state.get('date_time')}
Vehicle Type: {state.get('vehicle_type')}

Retrieved Legal Context:
{context}

Return only JSON in this schema:
{{
  "offence": "best normalized offence name from legal context or OCR",
  "expected_fine": 0,
  "expected_fine_text": "amount-only fine range or exact fine, for example ₹1000-₹5000",
  "legal_analysis": "short explanation comparing latest challan fine with retrieved law"
}}
Do not mention Source 1, Source 2, Reference IDs, page IDs, chunk IDs, or retrieval IDs in legal_analysis.
Start directly with the offence explanation.
If the selected state-specific rule clearly provides a fine, treat that state fine as final and mention that state penalty is preferred.
If central and state penalties conflict, prefer the selected state rule/portal penalty where it is retrieved.
If exact fine is a range, set expected_fine to the minimum fine amount and expected_fine_text to amount-only range.
If the retrieved legal context does not clearly specify the exact fine for the latest offence, say that the amount requires official portal/manual verification.
"""
    result = extract_json_with_gemini(prompt, fallback)
    state["offence"] = result.get("offence") or state.get("offence", "") or offence_for_kind

    # State-specific fine is final where it is actually retrieved.
    state_fine, state_fine_text = _state_specific_fine(state, kind)
    if state_fine:
        state["expected_fine"] = state_fine
        state["expected_fine_text"] = state_fine_text
    else:
        raw_fine_text = clean_legal_text(result.get("expected_fine_text") or "")
        normalized_fine = _amount_only_text(raw_fine_text, offence_for_kind, context)
        state["expected_fine_text"] = normalized_fine
        state["expected_fine"] = _fine_min(normalized_fine)

    state["legal_analysis"] = _remove_source_references(result.get("legal_analysis") or fallback["legal_analysis"])

    # Correct common inconsistency: legal_analysis says ₹1000 but expected_fine_text says unrelated ₹10000.
    if kind == "helmet" and state.get("expected_fine_text") in {"₹10000 (subsequent offence)", "Rs.10000 (subsequent offence)"}:
        state["expected_fine_text"] = "₹1000"
        state["expected_fine"] = 1000
    if kind == "helmet" and "194d" in context.lower() and state.get("expected_fine", 0) == 0:
        state["expected_fine_text"] = "₹1000"
        state["expected_fine"] = 1000

    # If legal analysis and expected fine conflict, prefer offence-aware normalized expected fine.
    if kind == "helmet" and "one thousand" in context.lower():
        state["expected_fine_text"] = state_fine_text or "₹1000"
        state["expected_fine"] = state_fine or 1000

    # Rebuild legal analysis if Gemini created an inconsistent comparison.
    if kind == "helmet" and state.get("expected_fine") == 1000:
        detected = state.get("fine_amount") or state.get("latest_fine_amount") or 0
        state["legal_analysis"] = (
            "The latest offence relates to riding or driving a motorcycle without protective headgear. "
            "Section 129 requires protective headgear, and Section 194D provides the penalty for contravention. "
            f"The detected challan fine is ₹{detected}. The retrieved legal context indicates an expected penalty of ₹1000 unless a valid state-specific payable amount is separately prescribed."
        )

    # Validation issues
    if state.get("expected_fine", 0) == 0:
        state["validation_issues"].append("Expected fine could not be conclusively identified from the retrieved legal documents for the latest offence.")
    elif state.get("fine_amount", 0) and state["fine_amount"] < state["expected_fine"]:
        state["validation_issues"].append("Detected fine amount is below the minimum expected fine from retrieved legal context.")

    if state.get("expected_fine_text") and "-" in state.get("expected_fine_text", ""):
        state["validation_issues"].append("Expected fine is a statutory range; verify the exact payable/compoundable amount with the official state challan portal or authority.")

    if state_fine:
        state["execution_log"].append("Legal Compliance Agent: Used selected-state penalty as final because a state-specific fine was retrieved.")
    state["execution_log"].append("Legal Compliance Agent: Compared extracted challan details with retrieved legal context using Gemini and offence-aware fine normalization.")
    return state


def legal_question_answer_agent(state: ChallanState) -> ChallanState:
    context = _context_text(state)
    fallback = (
        "Gemini answer generation was not available. Please check that GOOGLE_API_KEY is present in backend/.env "
        "and that the selected Gemini generation model is available. Retrieved legal references are shown below for manual review."
    )
    prompt = f"""
You are a traffic law information assistant.
Answer the user's question using ONLY the retrieved legal context.
Mention the selected state and cite the numbered source file names from the context.
Do not give final legal advice. If context is insufficient, say manual verification is required.
If the selected state document provides a penalty/fine, treat that state amount as final over central/common law.
Provide a direct answer first, then a short explanation.

User Type: {state.get('user_type')}
Selected State: {state.get('selected_state')}
Question: {state.get('legal_question')}

Retrieved Legal Context:
{context}
"""
    state["legal_answer"] = clean_legal_text(generate_text(prompt, fallback=fallback))
    st = gemini_status()
    state["execution_log"].append(
        f"Legal Question Agent: Gemini configured={st.get('configured')} model={st.get('generation_model')}. Generated answer using retrieved legal context."
    )
    return state
