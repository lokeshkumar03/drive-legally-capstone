import json
import os
from typing import Any, Dict, Tuple

from dotenv import load_dotenv

load_dotenv()

try:
    import google.generativeai as genai
except Exception:  # pragma: no cover
    genai = None


def _api_key() -> str:
    # Support both names so user setup is flexible.
    return os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or ""


def gemini_status() -> Dict[str, Any]:
    key = _api_key()
    return {
        "configured": bool(key) and genai is not None,
        "api_key_present": bool(key),
        "google_generativeai_imported": genai is not None,
        "generation_model": os.getenv("GOOGLE_GENERATION_MODEL", "gemini-2.5-flash"),
    }


def is_gemini_available() -> bool:
    status = gemini_status()
    return bool(status["configured"])


def _candidate_generation_models():
    configured = os.getenv("GOOGLE_GENERATION_MODEL")
    models = []
    if configured:
        models.append(configured)
    # Current Gemini API docs list gemini-2.5-flash as a supported text-output model.
    models.extend(["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"] )
    # de-duplicate preserving order
    seen = set()
    return [m for m in models if not (m in seen or seen.add(m))]


def generate_text(prompt: str, fallback: str = "") -> str:
    if not is_gemini_available():
        return fallback or "Gemini is not configured. Please check GOOGLE_API_KEY in backend/.env."

    genai.configure(api_key=_api_key())
    errors = []
    for model_name in _candidate_generation_models():
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            text = getattr(response, "text", "") or ""
            if text.strip():
                return text.strip()
        except Exception as exc:
            errors.append(f"{model_name}: {exc}")
    return fallback or "Gemini generation failed. " + " | ".join(errors[-2:])


def extract_json_with_gemini(prompt: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    if not is_gemini_available():
        return fallback

    genai.configure(api_key=_api_key())
    for model_name in _candidate_generation_models():
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            text = (getattr(response, "text", "") or "").strip()
            text = text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        except Exception:
            continue
    return fallback
