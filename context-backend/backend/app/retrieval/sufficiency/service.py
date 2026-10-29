import time
from typing import List, Optional, Sequence

from app.retrieval.sufficiency.config import SufficiencyConfig
from app.retrieval.sufficiency.evaluators.base import AssessmentInput, BaseSufficiencyEvaluator
from app.retrieval.sufficiency.evaluators.coverage import (
    SubqueryCoverageEvaluator,
    TermCoverageEvaluator,
)
from app.retrieval.sufficiency.evaluators.support import (
    ContentAdequacyEvaluator,
    EvidenceConflictEvaluator,
    EvidenceQuantityEvaluator,
    ExecutionHealthEvaluator,
    RetrievalConsensusEvaluator,
    SourceDiversityEvaluator,
)
from app.retrieval.sufficiency.models import SufficiencyAssessment, SufficiencySignal
from app.retrieval.sufficiency.policy import SufficiencyPolicy


def default_evaluators(config: SufficiencyConfig) -> List[BaseSufficiencyEvaluator]:
    return [
        TermCoverageEvaluator(config),
        SubqueryCoverageEvaluator(config),
        EvidenceQuantityEvaluator(config),
        SourceDiversityEvaluator(config),
        ContentAdequacyEvaluator(config),
        RetrievalConsensusEvaluator(config),
        ExecutionHealthEvaluator(config),
        EvidenceConflictEvaluator(config),
    ]


class SufficiencyService:
    """
    L07 assessment: run every evaluator, hand the signals to the policy.
    Same shape as EvidenceIntelligenceService in L06.
    """

    def __init__(
        self,
        config: Optional[SufficiencyConfig] = None,
        evaluators: Optional[Sequence[BaseSufficiencyEvaluator]] = None,
        policy: Optional[SufficiencyPolicy] = None,
    ):
        self.config = config or SufficiencyConfig()
        self.evaluators = list(evaluators) if evaluators is not None else default_evaluators(self.config)
        self.policy = policy or SufficiencyPolicy(self.config)

    def assess(self, inp: AssessmentInput) -> SufficiencyAssessment:
        signals: List[SufficiencySignal] = []
        for evaluator in self.evaluators:
            try:
                signals.append(evaluator.evaluate(inp))
            except Exception as exc:
                # A broken evaluator must never fail the request. It is left
                # out of the score; the policy caps the verdict if it was a
                # hard-gap check, so a crash can't produce SUFFICIENT.
                signals.append(
                    SufficiencySignal(
                        signal_name=evaluator.name,
                        applicable=False,
                        reason=f"Evaluator error: {str(exc)[:200]}",
                        details={"evaluator_error": True},
                        latency_ms=0,
                    )
                )
        return self.policy.assess(signals, inp)
