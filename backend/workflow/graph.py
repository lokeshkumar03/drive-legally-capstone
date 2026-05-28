from langgraph.graph import StateGraph, START, END

from models import ChallanState
from agents.evidence_agent import evidence_agent
from agents.validation_agent import validation_agent, validation_router
from agents.rag_agent import rag_retrieval_agent, legal_question_rag
from agents.legal_agent import legal_compliance_agent, legal_question_answer_agent
from agents.guardrails_agent import guardrails_agent
from agents.judge_agent import llm_judge_agent
from agents.report_agent import report_agent, legal_question_report_agent
from agents.human_review_agent import human_review_agent


def build_verification_workflow():
    workflow = StateGraph(ChallanState)
    workflow.add_node("evidence_agent", evidence_agent)
    workflow.add_node("validation_agent", validation_agent)
    workflow.add_node("rag_retrieval_agent", rag_retrieval_agent)
    workflow.add_node("legal_compliance_agent", legal_compliance_agent)
    workflow.add_node("human_review_agent", human_review_agent)
    workflow.add_node("guardrails_agent", guardrails_agent)
    workflow.add_node("llm_judge_agent", llm_judge_agent)
    workflow.add_node("report_agent", report_agent)

    workflow.add_edge(START, "evidence_agent")
    workflow.add_edge("evidence_agent", "validation_agent")
    workflow.add_conditional_edges(
        "validation_agent",
        validation_router,
        {"continue": "rag_retrieval_agent", "human_review": "human_review_agent"},
    )
    workflow.add_edge("rag_retrieval_agent", "legal_compliance_agent")
    workflow.add_edge("legal_compliance_agent", "guardrails_agent")
    workflow.add_edge("human_review_agent", "guardrails_agent")
    workflow.add_edge("guardrails_agent", "llm_judge_agent")
    workflow.add_edge("llm_judge_agent", "report_agent")
    workflow.add_edge("report_agent", END)
    return workflow.compile()


def build_legal_question_workflow():
    workflow = StateGraph(ChallanState)
    workflow.add_node("legal_question_rag", legal_question_rag)
    workflow.add_node("legal_question_answer_agent", legal_question_answer_agent)
    workflow.add_node("guardrails_agent", guardrails_agent)
    workflow.add_node("llm_judge_agent", llm_judge_agent)
    workflow.add_node("legal_question_report_agent", legal_question_report_agent)

    workflow.add_edge(START, "legal_question_rag")
    workflow.add_edge("legal_question_rag", "legal_question_answer_agent")
    workflow.add_edge("legal_question_answer_agent", "guardrails_agent")
    workflow.add_edge("guardrails_agent", "llm_judge_agent")
    workflow.add_edge("llm_judge_agent", "legal_question_report_agent")
    workflow.add_edge("legal_question_report_agent", END)
    return workflow.compile()
