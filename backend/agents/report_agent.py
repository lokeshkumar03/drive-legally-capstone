import re
from models import ChallanState
from services.report_pdf import create_pdf_report
from services.rag_service import clean_legal_text


def _no_source_refs(text: str) -> str:
    text = clean_legal_text(text or "")
    text = re.sub(r"\bSource\s*\d+\s*,?\s*", "", text, flags=re.I)
    text = re.sub(r"\bReference\s*\d+\s*,?\s*", "", text, flags=re.I)
    text = re.sub(r"\bchunk\s*id\s*[:#]?\s*\w+", "", text, flags=re.I)
    text = text.replace("Text from source:", "").replace("Text from source", "")
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r"–\s*,\s*", "– ", text)
    text = re.sub(r"-\s*,\s*", "- ", text)
    return clean_legal_text(text).strip(" ,;:-")


def calculate_confidence_score(state: ChallanState) -> int:
    score = 100
    if state.get("ocr_confidence", 0) < 55:
        score -= 20
    if state.get("image_quality", "").lower() == "blurry":
        score -= 20
    issues = state.get("validation_issues") or []
    review_issues = [i for i in issues if "multiple offences" not in i.lower()]
    if review_issues:
        score -= min(45, 10 * len(review_issues))
    if state.get("multiple_offences"):
        score -= 10
    if state.get("expected_fine", 0) and state.get("fine_amount", 0) < state.get("expected_fine", 0):
        score -= 20
    if not state.get("retrieved_sections"):
        score -= 20
    judge = state.get("judge_result") or {}
    if judge:
        if judge.get("verdict") == "FAIL":
            score -= 25
        elif judge.get("verdict") == "CAUTION":
            score -= 10
    guardrail = state.get("guardrail_result") or {}
    if guardrail and not guardrail.get("passed", True):
        score -= 10
    return max(0, min(100, score))


def determine_final_status(state: ChallanState) -> str:
    if state.get("final_status") == "Requires Human / Legal Review":
        return state["final_status"]
    judge = state.get("judge_result") or {}
    if judge.get("verdict") == "FAIL" or int(judge.get("total_score", 30) or 0) < 18:
        return "Requires Human / Legal Review"
    score = state.get("confidence_score", 0)
    if score >= 85 and not state.get("validation_issues"):
        return "Likely Valid Challan"
    if score >= 55:
        return "Requires Human / Legal Review"
    return "Potentially Invalid Challan"


def generate_recommendation(state: ChallanState):
    recs = []
    if state.get("image_quality", "").lower() == "blurry":
        recs.append("Request or upload clearer evidence before relying on this challan.")
    if state.get("expected_fine", 0) and state.get("fine_amount", 0) < state.get("expected_fine", 0):
        recs.append("Verify the fine amount with the official traffic department/state portal.")
    if state.get("multiple_offences"):
        recs.append("Because multiple challan rows/offences are visible, verify that the latest offence row matches the uploaded vehicle evidence.")
    if state.get("expected_fine", 0) == 0:
        recs.append("Verify the payable/compoundable fine amount on the official state challan portal.")
    judge = state.get("judge_result") or {}
    if judge.get("verdict") in {"CAUTION", "FAIL"}:
        recs.append("Treat this response cautiously because the LLM-as-a-Judge found grounding or safety concerns.")
    if state.get("validation_issues"):
        recs.append("Manual review by a legal professional or traffic authority is recommended.")
    if not recs:
        recs.append("The challan appears procedurally acceptable based on the available data and retrieved legal context.")
    return list(dict.fromkeys(recs))


def _offence_kind(state: ChallanState) -> str:
    low = f"{state.get('latest_offence') or state.get('offence') or ''}".lower()
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


def _act_name_from_item(item) -> str:
    source_file = (item.get("section") or "").lower()
    db = (item.get("state_db") or "").lower()
    if "ts_db" in db or "ts_challan" in source_file:
        return "Telangana State Traffic Enforcement Rules"
    if "ap_db" in db or "ap_challan" in source_file:
        return "Andhra Pradesh State Traffic Enforcement Rules"
    if "ka_db" in db or "ka_challan" in source_file:
        return "Karnataka State Traffic Enforcement Rules"
    if "amendment" in source_file or "mvehicles_20" in source_file:
        return "Motor Vehicles (Amendment) Act, 2019"
    if "rules of" in source_file or "road regulations" in source_file:
        return "Rules of the Road Regulations, 1989"
    if "mvact" in source_file or "motor" in source_file:
        return "Motor Vehicles Act, 1988"
    return "Retrieved Legal Material"


def _keywords_for_kind(kind: str):
    if kind == "parking":
        return ["parking", "park", "obstruction", "passageway", "carriageway", "free flow", "towing", "127", "201", "122"]
    if kind == "speed":
        return ["183", "speed", "excessive speed", "one thousand", "two thousand"]
    if kind == "dangerous":
        return ["184", "dangerous", "one thousand", "five thousand", "red light"]
    if kind == "helmet":
        return ["129", "194d", "helmet", "headgear", "protective"]
    if kind == "signal":
        return ["184", "signal", "red light", "stop sign", "stop line"]
    return ["fine", "penalty", "offence", "traffic"]


def _detect_section(summary: str, source_file: str, kind: str) -> str:
    text = (summary or "").lower()
    if kind == "parking":
        if re.search(r"\b122\s*\(?2\)?\b", text): return "Section 122(2)"
        if re.search(r"\b127\b", text): return "Section 127"
        if re.search(r"\b201\b", text): return "Section 201"
        if "parking" in text or "park" in text: return "Parking / Obstruction Rule"
    if kind == "speed" and re.search(r"\b183\b", text): return "Section 183"
    if kind == "dangerous" and re.search(r"\b184\b", text): return "Section 184"
    if kind == "helmet":
        if re.search(r"\b194d\b", text): return "Section 194D"
        if re.search(r"\b129\b", text): return "Section 129"
    if kind == "signal" and re.search(r"\b184\b", text): return "Section 184"
    m = re.search(r"\bsection\s+(\d+[a-z]?)\b", summary or "", re.I)
    if m:
        return f"Section {m.group(1).upper()}"
    return "Relevant Provision"


def _section_definition(section: str, act: str, summary: str, kind: str, keywords) -> str:
    text = _no_source_refs(summary or "")
    low = text.lower()
    # Controlled report-friendly definitions that reflect the retrieved legal context.
    if section == "Section 194D":
        return "Whoever drives a motorcycle or causes/allows it to be driven in contravention of Section 129 or rules made thereunder is punishable with a fine of ₹1,000 and disqualification from holding licence for three months."
    if section == "Section 129":
        return "Every person above four years of age driving, riding, or being carried on a motorcycle in a public place must wear protective headgear conforming to prescribed standards, subject to statutory exceptions."
    if section == "Section 183":
        return "Driving a motor vehicle in contravention of speed limits is punishable; for a light motor vehicle, the amended fine is ₹1,000 to ₹2,000."
    if section == "Section 184":
        return "Driving in a manner dangerous to the public is punishable; for a first offence, the amended fine is ₹1,000 to ₹5,000."
    if section == "Section 201":
        if "five hundred" in low or "amendment" in act.lower() or "disabled" in low:
            return "A vehicle kept in a public place so as to impede free flow of traffic may attract a penalty up to ₹500 per hour, subject to applicable enforcement and towing rules."
        return "Applies where a vehicle causes impediment to free flow of traffic in a public place."
    if section == "Section 127":
        return "A motor vehicle abandoned or left in a legally prohibited/obstructive place may be removed, towed, or immobilised by an authorised police officer, besides other applicable penalties."
    if section == "Section 122(2)":
        return "Relates to restrictions on leaving or parking a vehicle in a manner that causes danger, obstruction, or undue inconvenience to other road users."

    # For state rules / road regulations, use the shortest directly relevant sentence.
    chunks = re.split(r"(?<=[.;:])\s+", text)
    low_keywords = [k.lower() for k in keywords]
    for chunk in chunks:
        if any(k in chunk.lower() for k in low_keywords) and len(chunk.strip()) > 15:
            return _no_source_refs(chunk[:420].rsplit(" ", 1)[0] if len(chunk) > 420 else chunk)
    return "Relevant provision retrieved for the detected challan offence."


def _reference_relevance(section: str, kind: str) -> str:
    if kind == "helmet":
        return "Relevant to helmet/headgear compliance and fine verification for the detected challan."
    if kind == "parking":
        return "Relevant to wrong parking, obstruction, carriageway blockage, towing, or free-flow restrictions."
    if kind == "speed":
        return "Relevant to excessive speed and comparison of challan fine with prescribed penalty."
    if kind == "dangerous":
        return "Relevant to dangerous driving and comparison of challan fine with prescribed penalty."
    if kind == "signal":
        return "Relevant to signal/stop-line violations and associated traffic enforcement provisions."
    return "Relevant to the detected challan offence and fine verification."


def _is_relevant(summary: str, kind: str, keywords) -> bool:
    low = (summary or "").lower()
    if not low:
        return False
    if kind == "helmet":
        return any(k in low for k in ["194d", "section 129", "protective headgear", "helmet"])
    if kind == "parking":
        return any(k in low for k in ["parking", "park", "obstruction", "carriageway", "free flow", "towing", "section 127", "section 201", "section 122"])
    return any(k.lower() in low for k in keywords)


def build_grouped_legal_references(state: ChallanState):
    """Return grouped legal references used by both PDF report and React Legal tab.

    V12 behavior:
    - one entry per Act + Section,
    - no duplicate Section 194D/129 entries,
    - no labels such as "Text from source",
    - state-specific references are grouped separately where retrieved,
    - central/common law is still shown when state docs do not specify a penalty.
    """
    kind = _offence_kind(state)
    keywords = _keywords_for_kind(kind)
    candidates = []

    for item in state.get("retrieved_sections", []) or []:
        summary = item.get("summary", "") or ""
        if kind != "general" and not _is_relevant(summary, kind, keywords):
            continue
        act = _act_name_from_item(item)
        section = _detect_section(summary, item.get("section", ""), kind)
        definition = _section_definition(section, act, summary, kind, keywords)
        relevance = _reference_relevance(section, kind)
        is_state = "State Traffic" in act or "Telangana" in act or "Andhra" in act or "Karnataka" in act
        # Priority: state rules, amendment act, core act, road rules.
        priority = 0 if is_state else 1 if "Amendment" in act else 2 if "Motor Vehicles Act" in act else 3
        candidates.append((priority, act, section, definition, relevance))

    # Controlled fallback for common cases if retrieval is noisy.
    if not candidates:
        if kind == "helmet":
            candidates.extend([
                (1, "Motor Vehicles (Amendment) Act, 2019", "Section 194D", _section_definition("Section 194D", "", "", kind, keywords), _reference_relevance("Section 194D", kind)),
                (2, "Motor Vehicles Act, 1988", "Section 129", _section_definition("Section 129", "", "", kind, keywords), _reference_relevance("Section 129", kind)),
            ])
        elif kind == "parking":
            candidates.extend([
                (2, "Motor Vehicles Act, 1988", "Section 127", _section_definition("Section 127", "", "", kind, keywords), _reference_relevance("Section 127", kind)),
                (1, "Motor Vehicles (Amendment) Act, 2019", "Section 201", _section_definition("Section 201", "Motor Vehicles (Amendment) Act, 2019", "five hundred", kind, keywords), _reference_relevance("Section 201", kind)),
            ])

    # Deduplicate by Act + Section. If duplicate occurs, keep the longer useful definition.
    best = {}
    for priority, act, section, definition, relevance in sorted(candidates, key=lambda x: x[0]):
        definition = _no_source_refs(definition)
        if not definition or definition in {",", "."}:
            continue
        key = (act, section)
        line = f"{section} – {definition} Relevance: {relevance}"
        line = _no_source_refs(line)
        if key not in best or len(line) > len(best[key][1]):
            best[key] = (priority, line)

    groups = {}
    total = 0
    for (act, _section), (priority, line) in sorted(best.items(), key=lambda x: (x[1][0], x[0][0], x[0][1])):
        if total >= 5:
            break
        groups.setdefault(act, []).append(line)
        total += 1
    return groups


def _sources(state: ChallanState) -> str:
    groups = state.get("legal_reference_groups") or build_grouped_legal_references(state)
    state["legal_reference_groups"] = groups
    if not groups:
        return "No legal source retrieved."
    out = []
    for act, refs in groups.items():
        out.append(f"{act}")
        for ref in refs:
            out.append(f"- {_no_source_refs(ref)}")
    return "\n".join(out)


def _guardrail_section(state: ChallanState) -> str:
    result = state.get("guardrail_result") or {}
    if not result:
        return "Guardrails were not evaluated."
    lines = [f"- Guardrails Passed: {result.get('passed')}"]
    actions = result.get("actions") or []
    warnings = result.get("warnings") or []
    if actions:
        lines.append("- Actions Applied:")
        lines.extend([f"  {idx}. {_no_source_refs(action)}" for idx, action in enumerate(actions, start=1)])
    if warnings:
        lines.append("- Warnings:")
        lines.extend([f"  {idx}. {_no_source_refs(warning)}" for idx, warning in enumerate(warnings, start=1)])
    if not actions and not warnings:
        lines.append("- No guardrail warning detected.")
    return "\n".join(lines)


def _judge_section(state: ChallanState) -> str:
    judge = state.get("judge_result") or {}
    if not judge:
        return "LLM-as-a-Judge was not evaluated."
    return "\n".join([
        f"- Verdict: {judge.get('verdict', 'NOT_EVALUATED')}",
        f"- Total Score: {judge.get('total_score', 0)}/30",
        f"- Grounding Score: {judge.get('grounding_score', 0)}/5",
        f"- Citation Score: {judge.get('citation_score', 0)}/5",
        f"- State Relevance Score: {judge.get('state_relevance_score', 0)}/5",
        f"- Hallucination Risk Score: {judge.get('hallucination_risk_score', 0)}/5",
        f"- Clarity Score: {judge.get('clarity_score', 0)}/5",
        f"- Safety Score: {judge.get('safety_score', 0)}/5",
        f"- Reason: {_no_source_refs(judge.get('reason', ''))}",
    ])


def _expected_fine_display(state: ChallanState) -> str:
    text = state.get("expected_fine_text") or ""
    if text and text not in {"Not conclusively identified", "Rs.0", "₹0"}:
        return text.replace("Rs.", "₹")
    if state.get("expected_fine", 0):
        return f"₹{state.get('expected_fine'):,}"
    return "Not conclusively specified in retrieved legal context"


def report_agent(state: ChallanState) -> ChallanState:
    # Build legal reference groups before judge/report display so React/PDF are consistent.
    state["legal_reference_groups"] = build_grouped_legal_references(state)
    state["confidence_score"] = calculate_confidence_score(state)
    state["final_status"] = determine_final_status(state)
    state["recommendation"] = generate_recommendation(state)

    offence = state.get("latest_offence") or state.get("offence")
    place = state.get("latest_offence_location") or state.get("place_of_violation") or "Not Extracted"
    dt = state.get("latest_offence_datetime") or state.get("date_time") or "Not Extracted"
    fine = state.get("latest_fine_amount") or state.get("fine_amount") or 0

    base_report = f"""
# Drive Legally Verification Report

## 1. User and Vehicle Details
- User Type: {state.get('user_type')}
- User Name: {state.get('user_name') or 'Not Provided'}
- Input Vehicle Number: {state.get('input_vehicle_number') or 'Not Provided'}
- Selected State: {state.get('selected_state')}
- Vehicle Number from Challan: {state.get('vehicle_number') or 'Not Extracted'}
- Vehicle Number from Front Image: {state.get('vehicle_number_from_vehicle_image') or 'Not Provided/Not Extracted'}
- Vehicle Type: {state.get('vehicle_type') or 'Unknown'}
- Vehicle Validation Result: **{state.get('vehicle_match_status') or 'Not checked'}**

## 2. Challan Information
- Latest Offence: {offence}
- Latest Offence Location: {place}
- Latest Offence Date & Time: {dt}
- Latest Fine Amount: ₹{fine}
- Expected Fine Amount from Retrieved Context: {_expected_fine_display(state)}
- Evidence Timestamp: {state.get('evidence_timestamp') or 'Not Extracted'}
- Multiple Offences Detected: {'Yes' if state.get('multiple_offences') else 'No'}

## 3. Evidence and OCR / Vision Analysis
- Extraction Confidence: {state.get('ocr_confidence')}%
- Evidence Quality: {state.get('image_quality')}

## 4. Legal Analysis
{_no_source_refs(state.get('legal_analysis', ''))}

## 5. Legal References Retrieved
{_sources(state)}

## 6. Issues Detected
"""
    if state.get("validation_issues"):
        base_report += "\n".join([f"- {_no_source_refs(issue)}" for issue in state["validation_issues"]])
    else:
        base_report += "- No major validation issue detected."

    base_report += f"""

## 7. Final Verification Status
{state.get('final_status')}

## 8. Confidence Score
{state.get('confidence_score')}/100

## 9. Recommendation
"""
    base_report += "\n".join([f"- {_no_source_refs(rec)}" for rec in state.get("recommendation", [])])
    base_report += f"""

## 10. Guardrails Validation
{_guardrail_section(state)}

## 11. LLM-as-a-Judge Evaluation
{_judge_section(state)}

## 12. Disclaimer
This AI system provides assistive verification only. It does not constitute official legal advice or a final judicial/traffic authority decision.
"""
    state["final_report"] = base_report
    state["report_pdf_path"] = create_pdf_report(state["request_id"], base_report)
    state["execution_log"].append("Report Agent: Generated final report with state-priority fines, deduplicated grouped legal references, guardrails, and LLM judge evaluation.")
    return state


def legal_question_report_agent(state: ChallanState) -> ChallanState:
    state["legal_reference_groups"] = build_grouped_legal_references(state)
    judge = state.get("judge_result") or {}
    if judge.get("verdict") == "FAIL" or int(judge.get("total_score", 30) or 0) < 18:
        state["final_status"] = "Requires Human / Legal Review"
    else:
        state["final_status"] = "Legal Information Provided"
    state["confidence_score"] = min(100, max(0, int((int(judge.get("total_score", 0) or 0) / 30) * 100))) if judge else (85 if state.get("retrieved_sections") else 40)

    report = f"""
# Traffic Law Question Report

## 1. User Details
- User Type: {state.get('user_type')}
- User Name: {state.get('user_name') or 'Not Provided'}
- Selected State: {state.get('selected_state')}

## 2. Question
{clean_legal_text(state.get('legal_question', ''))}

## 3. Answer
{_no_source_refs(state.get('legal_answer', ''))}

## 4. Legal References Retrieved
{_sources(state)}

## 5. Guardrails Validation
{_guardrail_section(state)}

## 6. LLM-as-a-Judge Evaluation
{_judge_section(state)}

## 7. Disclaimer
This answer is for legal awareness and capstone demonstration only. Please verify with official traffic department/state rules before relying on it.
"""
    state["final_report"] = report
    state["report_pdf_path"] = create_pdf_report(state["request_id"], report)
    state["execution_log"].append("Report Agent: Generated legal question report and PDF with state-priority, grouped legal references, guardrails, and LLM judge evaluation.")
    return state
