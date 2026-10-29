from app.core.enums import KnowledgeProcessingStage
from app.knowledge.processing.context import KnowledgeProcessingContext
from app.knowledge.processing.exceptions import (
    KnowledgeProcessingValidationError,
)
from app.knowledge.processing.stages.base import (
    BaseKnowledgeProcessingStage,
)


class SourceValidationStage(BaseKnowledgeProcessingStage):
    @property
    def stage_name(self) -> str:
        return KnowledgeProcessingStage.SOURCE_VALIDATION.value

    def execute(
        self,
        context: KnowledgeProcessingContext,
    ) -> KnowledgeProcessingContext:
        if context.current_stage != KnowledgeProcessingStage.SOURCE_VALIDATION:
            raise ValueError(
                "Source validation stage cannot execute from "
                f"{context.current_stage.value}"
            )

        if not context.document_id.strip():
            raise KnowledgeProcessingValidationError(
                "Source validation requires a valid document_id"
            )

        if not context.document_version_id.strip():
            raise KnowledgeProcessingValidationError(
                "Source validation requires a valid document_version_id"
            )

        if not context.permanent_bucket.strip():
            raise KnowledgeProcessingValidationError(
                "Document version has no permanent storage bucket"
            )

        if not context.permanent_object_key.strip():
            raise KnowledgeProcessingValidationError(
                "Document version has no permanent storage object key"
            )

        context.checkpoint_data["source_validation"] = {
            "completed": True,
            "document_id": context.document_id,
            "document_version_id": context.document_version_id,
            "permanent_bucket": context.permanent_bucket,
            "permanent_object_key": context.permanent_object_key,
        }

        return context