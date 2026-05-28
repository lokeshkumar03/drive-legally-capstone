import re
from models import ChallanState


def _norm_vehicle(v: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (v or "").upper())


def validation_agent(state: ChallanState) -> ChallanState:
    issues = []
    input_vehicle = _norm_vehicle(state.get("input_vehicle_number", ""))
    challan_vehicle = _norm_vehicle(state.get("vehicle_number", ""))
    front_vehicle = _norm_vehicle(state.get("vehicle_number_from_vehicle_image", ""))

    if not state.get("selected_state"):
        issues.append("State is required for state-wise legal rule retrieval.")
    if not state.get("challan_file_path"):
        issues.append("Challan file is required.")
    if not challan_vehicle:
        issues.append("Vehicle number could not be confidently extracted from challan.")
    if state.get("vehicle_front_file_path") and not front_vehicle:
        issues.append("Vehicle number could not be confidently extracted from vehicle front image.")
    if not state.get("vehicle_type") or state.get("vehicle_type") == "Unknown":
        issues.append("Vehicle type could not be confidently identified from evidence image.")
    if not state.get("place_of_violation") or state.get("place_of_violation") == "Not Extracted":
        issues.append("Place of violation could not be confidently extracted.")
    if not state.get("date_time"):
        issues.append("Date and time could not be confidently extracted.")
    if state.get("multiple_offences"):
        issues.append("Multiple offences/challan rows were detected; the system selected only the latest offence row for verification.")
    if state.get("evidence_timestamp") and state.get("date_time") and not state.get("evidence_matches_latest_timestamp"):
        issues.append("Evidence image timestamp does not clearly match the selected latest offence timestamp; verify the evidence row manually.")
    if not state.get("offence") or state.get("offence") == "Offence not confidently extracted":
        issues.append("Offence could not be confidently extracted from challan.")
    if state.get("fine_amount", 0) <= 0:
        issues.append("Fine amount could not be confidently extracted.")
    if state.get("ocr_confidence", 0) < 55:
        issues.append("Extraction confidence is low. Tesseract may be unavailable or image text may be difficult to read.")
    if state.get("image_quality", "").lower() == "blurry":
        issues.append("Evidence image appears blurry.")

    # Vehicle matching priority: challan vs front image, then user input vs challan.
    if front_vehicle and challan_vehicle:
        if front_vehicle == challan_vehicle:
            state["vehicle_match_status"] = "Vehicle front image number matches challan vehicle number."
        else:
            state["vehicle_match_status"] = "Vehicle front image number does not match challan vehicle number."
            issues.append("Vehicle number mismatch between challan and vehicle front image.")
    elif input_vehicle and challan_vehicle:
        if input_vehicle == challan_vehicle:
            state["vehicle_match_status"] = "User entered vehicle number matches challan vehicle number."
        else:
            state["vehicle_match_status"] = "Mismatch between user entered vehicle number and challan vehicle number."
            issues.append("Vehicle number mismatch between user input and challan.")
    elif input_vehicle:
        state["vehicle_match_status"] = "User vehicle number provided, but challan vehicle could not be verified."
    elif state.get("vehicle_front_file_path"):
        state["vehicle_match_status"] = "Vehicle front image was uploaded, but vehicle number matching could not be completed."
    else:
        state["vehicle_match_status"] = "Not checked."

    state["validation_issues"] = issues
    state["execution_log"].append("Validation Agent: Completed field extraction, evidence, date/place, and vehicle matching checks.")
    return state


def validation_router(state: ChallanState) -> str:
    if not state.get("selected_state"):
        state["execution_log"].append("Router: Sent to human review because state is missing.")
        return "human_review"

    has_core_fields = bool(state.get("vehicle_number")) and bool(state.get("offence")) and state.get("fine_amount", 0) > 0
    if state.get("ocr_confidence", 0) < 35 and not has_core_fields:
        state["execution_log"].append("Router: Sent to human review due to very low extraction confidence and missing core fields.")
        return "human_review"

    state["execution_log"].append("Router: Proceeding to RAG legal retrieval.")
    return "continue"
