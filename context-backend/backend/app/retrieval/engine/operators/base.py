
from abc import ABC, abstractmethod
from typing import List, Mapping, Any
from app.retrieval.planning.schemas import RetrievalStep
from app.retrieval.engine.schemas import RawRetrievalResult

class BaseOperator(ABC):
    
    @abstractmethod
    def execute(self, step: RetrievalStep, context_data: Mapping[str, Any]) -> List[RawRetrievalResult]:
        """
        Executes a single step and returns raw hits (e.g. vector IDs, graph node IDs).
        The framework must NOT return canonical content directly unless it's a pure content lookup operator.
        """
        pass

    @property
    @abstractmethod
    def capability_id(self) -> str:
        """The specific capability this operator fulfills (e.g. 'cap_semantic')"""
        pass
