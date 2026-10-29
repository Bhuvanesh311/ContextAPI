from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Tuple

from app.retrieval.engine.schemas import CandidateEvidenceSet
from app.retrieval.evidence.models import ValidatedEvidence
from app.retrieval.sufficiency.config import SufficiencyConfig
from app.retrieval.sufficiency.enums import SignalName
from app.retrieval.sufficiency.models import SufficiencyQuery, SufficiencySignal


@dataclass(frozen=True)
class AssessmentInput:
    query: SufficiencyQuery
    accepted: Tuple[ValidatedEvidence, ...]        # L06 state == ACCEPTED, all rounds so far
    all_validated: Tuple[ValidatedEvidence, ...]   # everything L06 returned
    latest_round: CandidateEvidenceSet             # raw result of the round just executed
    round_index: int
    top_k: int                                     # depth used in the round just executed


class BaseSufficiencyEvaluator(ABC):
    def __init__(self, config: SufficiencyConfig):
        self.config = config

    @property
    @abstractmethod
    def name(self) -> SignalName:
        pass

    @abstractmethod
    def evaluate(self, inp: AssessmentInput) -> SufficiencySignal:
        """
        Measure one property of the evidence and return a signal.
        The evaluator must NEVER return a verdict or a gap.
        """
        pass
