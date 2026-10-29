from app.core.enums import KnowledgeProcessingStage
from app.knowledge.chunking.services.chunking_service import ChunkingService
from app.knowledge.processing.context import KnowledgeProcessingContext
from app.knowledge.processing.exceptions import KnowledgeProcessingStageError
from app.knowledge.processing.stages.base import BaseKnowledgeProcessingStage


class ChunkingStage(BaseKnowledgeProcessingStage):
    def __init__(self, chunking_service: ChunkingService) -> None:
        self.chunking_service = chunking_service

    @property
    def stage_name(self) -> str:
        return KnowledgeProcessingStage.CHUNKING.value

    def execute(
        self,
        context: KnowledgeProcessingContext,
    ) -> KnowledgeProcessingContext:
        if context.current_stage != KnowledgeProcessingStage.CHUNKING:
            raise ValueError(
                "Chunking stage cannot execute from "
                f"{context.current_stage.value}"
            )

        try:
            chunks = self.chunking_service.process(
                document_id=context.document_id,
                document_version_id=context.document_version_id,
                permanent_bucket=context.permanent_bucket,
                permanent_object_key=context.permanent_object_key,
                chunks_object_key=context.chunks_object_key,
            )
        except Exception as exc:
            raise KnowledgeProcessingStageError(
                "Chunking stage failed"
            ) from exc

        context.checkpoint_data["chunking"] = {
            "completed": True,
            "chunk_count": len(chunks),
            "chunks_object_key": context.chunks_object_key,
        }

        return context