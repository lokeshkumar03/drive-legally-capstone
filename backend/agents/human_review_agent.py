from models import ChallanState


def human_review_agent(state: ChallanState) -> ChallanState:
    state["final_status"] = "Requires Human / Legal Review"
    if "Automated verification could not conclusively complete due to insufficient input quality." not in state.get("validation_issues", []):
        state["validation_issues"].append("Automated verification could not conclusively complete due to insufficient input quality.")
    state["legal_analysis"] = "The matter should be reviewed manually because the OCR/evidence/state information was insufficient for reliable automated verification."
    state["execution_log"].append("Human Review Agent: Case escalated for manual review.")
    return state
