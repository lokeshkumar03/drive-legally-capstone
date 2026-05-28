from models import ChallanState
from guardrails.output_guardrails import apply_output_guardrails


def guardrails_agent(state: ChallanState) -> ChallanState:
    return apply_output_guardrails(state)
