from app.core.enums import KnowledgeProcessingStage
from app.knowledge.processing.context import KnowledgeProcessingContext
from app.knowledge.processing.stages.base import BaseKnowledgeProcessingStage


class InitializationStage(BaseKnowledgeProcessingStage):
    @property
    def stage_name(self) -> str:
        return KnowledgeProcessingStage.INITIALIZATION.value

    def execute(
        self,
        context: KnowledgeProcessingContext,
    ) -> KnowledgeProcessingContext:
        if context.current_stage != KnowledgeProcessingStage.INITIALIZATION:
            raise ValueError(
                "Initialization stage cannot execute from "
                f"{context.current_stage.value}"
            )

        context.checkpoint_data["initialization"] = {
            "completed": True,
        }

        return context