from models import ChallanState
from services.rag_service import retrieve_legal_context


def _offence_kind(offence: str) -> str:
    text = (offence or "").lower()
    if any(k in text for k in ["helmet", "headgear", "194d", "129"]):
        return "helmet"
    if any(k in text for k in ["parking", "obstruction", "carriageway", "no parking", "unauthor", "unauthoriz"]):
        return "parking"
    if any(k in text for k in ["dangerous", "184"]):
        return "dangerous"
    if any(k in text for k in ["speed", "over speed", "overspeed", "183"]):
        return "speed"
    if any(k in text for k in ["signal", "red light", "stop line"]):
        return "signal"
    return "general"


def _section_hint(kind: str) -> str:
    if kind == "helmet":
        return "Section 129 Section 194D protective headgear helmet fine Motor Vehicles Amendment Act 2019"
    if kind == "parking":
        return "unauthorized parking no parking obstruction carriageway parking prohibited towing penalty state challan rules Motor Vehicles Act"
    if kind == "dangerous":
        return "Section 184 dangerous driving first offence fine one thousand five thousand Motor Vehicles Amendment Act 2019"
    if kind == "speed":
        return "Section 183 excessive speed light motor vehicle fine one thousand two thousand Motor Vehicles Amendment Act 2019"
    if kind == "signal":
        return "traffic signal red light stop line dangerous driving Section 184 fine Motor Vehicles Act state challan rules"
    return "traffic challan fine penalty offence Motor Vehicles Act state challan rules"


def rag_retrieval_agent(state: ChallanState) -> ChallanState:
    state_code = state.get("selected_state", "")
    offence = state.get("latest_offence") or state.get("offence", "")
    kind = _offence_kind(offence)
    query_parts = [
        _section_hint(kind),
        f"Detected offence: {offence}",
        f"Vehicle type: {state.get('vehicle_type', '')}",
        f"Fine amount: {state.get('fine_amount', '')}",
        f"Place: {state.get('place_of_violation', '')}",
    ]
    # Do not include full OCR text here. It may contain older challan rows and can pull unrelated provisions.
    query = " ".join([p for p in query_parts if p]).strip()
    k = 5 if kind in {"parking", "helmet", "signal"} else 6
    state["retrieved_sections"] = retrieve_legal_context(state_code, query, k=k)
    state["retrieval_query"] = query
    state["offence_kind"] = kind
    state["execution_log"].append(
        f"RAG Agent: Retrieved legal context for latest offence only ({kind}) using FAISS vector search."
    )
    return state


def legal_question_rag(state: ChallanState) -> ChallanState:
    question = state.get("legal_question", "") or "traffic offence fine"
    state["retrieved_sections"] = retrieve_legal_context(state.get("selected_state", ""), question, k=6)
    state["execution_log"].append("RAG Agent: Retrieved legal context for user legal question using FAISS vector search.")
    return state
