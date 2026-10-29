from app.core.enums import KnowledgeProcessingStage
from app.knowledge.processing.exceptions import KnowledgeProcessingStateError
from app.knowledge.processing.stages.base import (
    BaseKnowledgeProcessingStage,
)


class KnowledgeProcessingStageRegistry:
    def __init__(
        self,
        stages: tuple[BaseKnowledgeProcessingStage, ...],
    ) -> None:
        self._stages: dict[
            KnowledgeProcessingStage,
            BaseKnowledgeProcessingStage,
        ] = {}

        for stage in stages:
            self._register(stage)

    def get(
        self,
        stage: KnowledgeProcessingStage,
    ) -> BaseKnowledgeProcessingStage:
        handler = self._stages.get(stage)

        if handler is None:
            raise KnowledgeProcessingStateError(
                "No handler registered for knowledge processing stage "
                f"{stage.value}"
            )

        return handler

    def _register(
        self,
        stage: BaseKnowledgeProcessingStage,
    ) -> None:
        try:
            stage_enum = KnowledgeProcessingStage(stage.stage_name)
        except ValueError as exc:
            raise KnowledgeProcessingStateError(
                "Stage handler declares an unsupported knowledge "
                f"processing stage: {stage.stage_name}"
            ) from exc

        if stage_enum in self._stages:
            raise KnowledgeProcessingStateError(
                "Duplicate knowledge processing stage handler: "
                f"{stage_enum.value}"
            )

        self._stages[stage_enum] = stage

    def as_dict(
        self,
    ) -> dict[
        KnowledgeProcessingStage,
        BaseKnowledgeProcessingStage,
    ]:
        return dict(self._stages)