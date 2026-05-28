from models import ChallanState
from evaluators.llm_judge import judge_legal_answer


def llm_judge_agent(state: ChallanState) -> ChallanState:
    state = judge_legal_answer(state)
    judge = state.get("judge_result", {})
    verdict = judge.get("verdict", "NOT_EVALUATED")
    total = judge.get("total_score", 0)
    if verdict == "FAIL" or total < 18:
        state["final_status"] = "Requires Human / Legal Review"
        state.setdefault("validation_issues", [])
        msg = "LLM-as-a-Judge found low grounding or high hallucination risk."
        if msg not in state["validation_issues"]:
            state["validation_issues"].append(msg)
    state.setdefault("execution_log", []).append(
        f"LLM-as-a-Judge Agent: verdict={verdict}; score={total}/30."
    )
    return state
