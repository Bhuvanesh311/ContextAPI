from abc import ABC, abstractmethod

from app.knowledge.processing.context import KnowledgeProcessingContext


class BaseKnowledgeProcessingStage(ABC):
    @property
    @abstractmethod
    def stage_name(self) -> str:
        """Return the name of the processing stage."""
        raise NotImplementedError

    @abstractmethod
    def execute(
        self,
        context: KnowledgeProcessingContext,
    ) -> KnowledgeProcessingContext:
        """Execute the processing stage and return the updated context."""
        raise NotImplementedError