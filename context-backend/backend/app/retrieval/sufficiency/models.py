from typing import Any, Dict, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import QueryComplexity, QueryIntent, RetrievalRequirementType
from app.retrieval.sufficiency.enums import (
    EscalationAction,
    GapSeverity,
    GapType,
    SignalName,
    StopReason,
    SufficiencyVerdict,
)
from app.retrieval.sufficiency.text import significant_terms


class SufficiencyQuery(BaseModel):
    """What L07 needs to know about the question. Built once per request."""
    model_config = ConfigDict(frozen=True)
    query_text: str
    intent: QueryIntent = QueryIntent.UNKNOWN
    complexity: QueryComplexity = QueryComplexity.LOW
    subqueries: Tuple[str, ...] = Field(default_factory=tuple)
    available_documents: Optional[int] = None
    # Topic words in order, surface form only (used to build escalation queries).
    terms: Tuple[str, ...] = Field(default_factory=tuple)

    @classmethod
    def create(
        cls,
        query_text: str,
        intent: QueryIntent = QueryIntent.UNKNOWN,
        complexity: QueryComplexity = QueryComplexity.LOW,
        subqueries: Tuple[str, ...] = (),
        available_documents: Optional[int] = None,
    ) -> "SufficiencyQuery":
        subs = tuple(s for s in subqueries if s and s.strip())
        # One sub-question is just the question itself.
        if len(subs) < 2:
            subs = ()
        return cls(
            query_text=query_text or "",
            intent=intent,
            complexity=complexity,
            subqueries=subs,
            available_documents=available_documents,
            terms=tuple(surface for surface, _ in significant_terms(query_text or "")),
        )


class SufficiencySignal(BaseModel):
    """
    One measurement about the evidence. Like an L06 trace, a signal never
    decides anything by itself. The policy turns signals into gaps and a verdict.
    """
    model_config = ConfigDict(frozen=True)
    signal_name: SignalName
    applicable: bool = True
    value: float = 0.0          # 0..1, 1 = fully satisfied
    target: float = 1.0         # value must reach this to pass
    reason: str = ""
    details: Dict[str, Any] = Field(default_factory=dict)
    latency_ms: int = 0


class SufficiencyGap(BaseModel):
    model_config = ConfigDict(frozen=True)
    gap_type: GapType
    severity: GapSeverity
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class SufficiencyAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)
    round_index: int
    verdict: SufficiencyVerdict
    score: float
    accepted_count: int
    gaps: Tuple[SufficiencyGap, ...] = Field(default_factory=tuple)
    signals: Tuple[SufficiencySignal, ...] = Field(default_factory=tuple)


class EscalationStepSpec(BaseModel):
    model_config = ConfigDict(frozen=True)
    capability_type: RetrievalRequirementType
    query_text: str
    subquery_id: Optional[str] = None


class EscalationDecision(BaseModel):
    model_config = ConfigDict(frozen=True)
    action: EscalationAction
    reason: str
    top_k: int
    steps: Tuple[EscalationStepSpec, ...] = Field(default_factory=tuple)


class RoundRecord(BaseModel):
    """What happened in one round. Stored so a result can always be explained."""
    model_config = ConfigDict(frozen=True)
    round_index: int
    action: Optional[EscalationAction] = None
    reason: Optional[str] = None
    queries: Tuple[str, ...] = Field(default_factory=tuple)
    top_k: int = 0
    execution_status: str = ""
    new_candidates: int = 0
    accepted_total: int = 0
    new_accepted: int = 0
    verdict: SufficiencyVerdict = SufficiencyVerdict.INSUFFICIENT
    score: float = 0.0
    gap_types: Tuple[GapType, ...] = Field(default_factory=tuple)
    latency_ms: int = 0


class SufficiencyReport(BaseModel):
    """The persisted L07 result (retrieval_requests.sufficiency)."""
    model_config = ConfigDict(frozen=True)
    verdict: SufficiencyVerdict
    score: float = 0.0
    stop_reason: StopReason
    rounds_executed: int = 0
    max_rounds: int = 0
    escalated: bool = False
    result_limit: int = 0
    total_latency_ms: int = 0
    gaps: Tuple[SufficiencyGap, ...] = Field(default_factory=tuple)
    signals: Tuple[SufficiencySignal, ...] = Field(default_factory=tuple)
    rounds: Tuple[RoundRecord, ...] = Field(default_factory=tuple)

    @classmethod
    def empty(cls, stop_reason: StopReason, message: str) -> "SufficiencyReport":
        """For requests that end before any retrieval could run."""
        return cls(
            verdict=SufficiencyVerdict.INSUFFICIENT,
            score=0.0,
            stop_reason=stop_reason,
            gaps=(
                SufficiencyGap(
                    gap_type=GapType.NO_EVIDENCE,
                    severity=GapSeverity.HARD,
                    message=message,
                ),
            ),
        )
