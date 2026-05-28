from typing import List, Optional
from pydantic import BaseModel, Field


class LegalReference(BaseModel):
    document: str
    page: Optional[str] = None
    excerpt: str


class LegalAnswer(BaseModel):
    answer: str
    fine_amount: Optional[str] = None
    legal_references: List[LegalReference] = Field(default_factory=list)
    confidence: str = "Medium"
    disclaimer: str


class GuardrailResult(BaseModel):
    passed: bool
    warnings: List[str] = Field(default_factory=list)
    actions: List[str] = Field(default_factory=list)


class JudgeResult(BaseModel):
    grounding_score: int = 0
    citation_score: int = 0
    state_relevance_score: int = 0
    hallucination_risk_score: int = 0
    clarity_score: int = 0
    safety_score: int = 0
    total_score: int = 0
    verdict: str = "NOT_EVALUATED"
    reason: str = ""
