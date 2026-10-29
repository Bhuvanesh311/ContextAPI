from io import BytesIO

from app.core.enums import KnowledgeProcessingStage
from app.infra.storage.services import ObjectStorageService
from app.knowledge.chunking.readers.ndjson import NDJSONReader
from app.knowledge.processing.context import KnowledgeProcessingContext
from app.knowledge.processing.exceptions import KnowledgeProcessingValidationError
from app.knowledge.processing.stages.base import BaseKnowledgeProcessingStage


class ChunkValidationStage(BaseKnowledgeProcessingStage):
    def __init__(
        self,
        *,
        storage: ObjectStorageService,
        reader: NDJSONReader | None = None,
    ) -> None:
        self.storage = storage
        self.reader = reader or NDJSONReader()

    @property
    def stage_name(self) -> str:
        return KnowledgeProcessingStage.CHUNK_VALIDATION.value

    def execute(
        self,
        context: KnowledgeProcessingContext,
    ) -> KnowledgeProcessingContext:
        if context.current_stage != KnowledgeProcessingStage.CHUNK_VALIDATION:
            raise ValueError(
                f"Chunk validation stage received invalid stage: "
                f"{context.current_stage.value}"
            )
    
        permanent_bucket = context.permanent_bucket
        chunks_object_key = context.chunks_object_key
    
        if not permanent_bucket.strip():
            raise KnowledgeProcessingValidationError(
                "Chunk validation requires a valid permanent bucket"
            )
    
        if not chunks_object_key.strip():
            raise KnowledgeProcessingValidationError(
                "Chunk validation requires a valid chunks object key"
            )
    
        response = None
    
        try:
            response = self.storage.download(
                bucket=permanent_bucket,
                object_key=chunks_object_key,
            )
    
            raw_data = response.read()
    
            chunks = self.reader.read(
                BytesIO(raw_data),
            )
    
        finally:
            if response is not None:
                response.close()
    
        if not chunks:
            raise KnowledgeProcessingValidationError(
                "Chunk validation requires at least one chunk"
            )
    
        for chunk in chunks:
            if chunk.document_id != context.document_id:
                raise KnowledgeProcessingValidationError(
                    "Chunk document_id does not match processing context"
                )
    
            if chunk.document_version_id != context.document_version_id:
                raise KnowledgeProcessingValidationError(
                    "Chunk document_version_id does not match processing context"
                )
    
        context.checkpoint_data["chunk_validation"] = {
            "completed": True,
            "chunk_count": len(chunks),
            "chunks_object_key": chunks_object_key,
        }
    
        return context