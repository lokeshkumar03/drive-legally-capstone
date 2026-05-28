import re
from typing import Any, Dict, List

INTERNAL_DB_NAMES = ["Common_db", "AP_db", "TS_db", "KA_db"]
DISCLAIMER = (
    "Disclaimer: This answer is for legal awareness and capstone demonstration only. "
    "Please verify with the official traffic department, applicable state rules, or a legal professional."
)


def normalize_legal_text(text: str) -> str:
    text = text or ""
    replacements = {
        ":—": ":",
        "namely:—": "namely:",
        ".—": ".",
        ":-": ":",
        " — ": " - ",
        "–": "-",
        "\u2026": "",
        "...": "",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def remove_internal_db_names(text: str) -> str:
    text = text or ""
    for name in INTERNAL_DB_NAMES:
        text = text.replace(f"({name}, ", "(")
        text = text.replace(f"({name} ", "(")
        text = text.replace(f"{name}, ", "")
        text = text.replace(name, "")
    return re.sub(r"\s+", " ", text).strip()


def clean_text_for_output(text: str) -> str:
    return remove_internal_db_names(normalize_legal_text(text))


def ensure_disclaimer(text: str) -> str:
    text = text or ""
    if "Disclaimer:" not in text and "disclaimer" not in text.lower():
        text = f"{text}\n\n{DISCLAIMER}".strip()
    return text


def clean_references(references: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cleaned = []
    for idx, ref in enumerate(references or [], start=1):
        cleaned.append({
            **ref,
            "number": idx,
            "section": clean_text_for_output(str(ref.get("section", "Legal Document"))),
            "summary": clean_text_for_output(str(ref.get("summary", ""))),
            # keep state_db internally but UI/report does not display it
            "state_db": ref.get("state_db", ""),
        })
    return cleaned


def validate_state_relevance(state: Dict[str, Any]) -> List[str]:
    warnings = []
    selected_state = (state.get("selected_state") or "").upper()
    allowed = {"COMMON", "Common_db", ""}
    if selected_state == "TS":
        allowed.update({"TS_db", "TS"})
    elif selected_state == "AP":
        allowed.update({"AP_db", "AP"})
    elif selected_state == "KA":
        allowed.update({"KA_db", "KA"})

    for ref in state.get("retrieved_sections", []) or []:
        state_db = ref.get("state_db", "")
        if state_db and state_db not in allowed:
            warnings.append(f"Retrieved source may not match selected state: {state_db}")
    return warnings


def apply_output_guardrails(state: Dict[str, Any]) -> Dict[str, Any]:
    warnings: List[str] = []
    actions: List[str] = []

    state["retrieved_sections"] = clean_references(state.get("retrieved_sections", []))

    for key in ["legal_answer", "legal_analysis", "final_report"]:
        if state.get(key):
            before = state.get(key, "")
            after = clean_text_for_output(before)
            if after != before:
                actions.append(f"Normalized punctuation/internal DB markers in {key}.")
            state[key] = after

    if state.get("legal_answer"):
        original = state["legal_answer"]
        state["legal_answer"] = ensure_disclaimer(state["legal_answer"])
        if state["legal_answer"] != original:
            actions.append("Added legal-awareness disclaimer to answer.")

    if state.get("final_report"):
        state["final_report"] = ensure_disclaimer(state["final_report"])

    combined = "\n".join([
        state.get("legal_answer", ""),
        state.get("legal_analysis", ""),
        state.get("final_report", ""),
    ])
    if "..." in combined or "…" in combined:
        warnings.append("Output still contains incomplete text marker (...).")

    if not state.get("retrieved_sections"):
        warnings.append("No retrieved legal references found. Answer should be treated as low confidence.")

    if state.get("mode") == "legal_question" and not state.get("legal_answer"):
        warnings.append("Legal question answer is empty.")

    warnings.extend(validate_state_relevance(state))

    passed = len(warnings) == 0
    state["guardrail_result"] = {
        "passed": passed,
        "warnings": warnings,
        "actions": actions,
    }

    if warnings:
        state.setdefault("validation_issues", [])
        for warning in warnings:
            marker = f"Guardrail warning: {warning}"
            if marker not in state["validation_issues"]:
                state["validation_issues"].append(marker)

    state.setdefault("execution_log", []).append(
        f"Guardrails Agent: passed={passed}; warnings={len(warnings)}; actions={len(actions)}."
    )
    return state
