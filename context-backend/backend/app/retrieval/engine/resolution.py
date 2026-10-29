
from abc import ABC, abstractmethod
from typing import List, Dict, Set
from app.retrieval.engine.schemas import RawRetrievalResult, CandidateEvidence, ProvenanceMetadata
from app.retrieval.engine.enums import OperatorType

class BaseContentResolver(ABC):
    @abstractmethod
    def resolve(self, raw_results: List[RawRetrievalResult]) -> List[CandidateEvidence]:
        """
        Maps raw results (e.g. vector IDs) to canonical CandidateEvidence objects.
        """
        pass
