from typing import Any

from app.core.enums import KnowledgeProcessingStage
from app.infra.storage import ObjectStorageService
from app.knowledge.processing.context import KnowledgeProcessingContext
from app.knowledge.processing.exceptions import KnowledgeProcessingStageError
from app.knowledge.processing.stages.base import BaseKnowledgeProcessingStage
import json


class IndexValidationStage(BaseKnowledgeProcessingStage):
    def __init__(
        self,
        *,
        storage: ObjectStorageService,
        chroma_client: Any,
        collection_name: str = "knowledge",
    ) -> None:
        self._storage = storage
        self._chroma_client = chroma_client
        self._collection_name = collection_name

    @property
    def stage_name(self) -> KnowledgeProcessingStage:
        return KnowledgeProcessingStage.INDEX_VALIDATION

    def execute(
        self,
        context: KnowledgeProcessingContext,
    ) -> KnowledgeProcessingContext:
        self._validate_context(context)

        embeddings_payload = self._storage.download(
            bucket=context.permanent_bucket,
            object_key=context.embeddings_object_key,
        )
        
        try:
            embeddings_data = embeddings_payload.read()
            if isinstance(embeddings_data, bytes):
                embeddings_data = embeddings_data.decode("utf-8")
        finally:
            embeddings_payload.close()

        expected_ids = []
        for line in embeddings_data.splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            expected_ids.append(record["vector_id"])

        if not expected_ids:
            raise KnowledgeProcessingStageError("No embeddings found to validate")

        collection = self._chroma_client.get_collection(self._collection_name)
        result = collection.get(ids=expected_ids, include=[])
        
        returned_ids = result.get("ids", [])
        
        if len(expected_ids) != len(returned_ids):
            raise KnowledgeProcessingStageError(
                f"Index validation failed. Expected {len(expected_ids)} vectors, found {len(returned_ids)}."
            )
            
        if set(expected_ids) != set(returned_ids):
            raise KnowledgeProcessingStageError(
                "Index validation failed. The sets of expected and returned vector IDs do not match exactly."
            )

        checkpoint_data = dict(context.checkpoint_data)
        checkpoint_data["index_validation"] = {
            "completed": True,
        }

        return KnowledgeProcessingContext(
            knowledge_processing_run_id=context.knowledge_processing_run_id,
            document_id=context.document_id,
            document_version_id=context.document_version_id,
            permanent_bucket=context.permanent_bucket,
            permanent_object_key=context.permanent_object_key,
            chunks_object_key=context.chunks_object_key,
            embeddings_object_key=context.embeddings_object_key,
            current_stage=context.current_stage,
            checkpoint_data=checkpoint_data,
        )

    @staticmethod
    def _validate_context(context: KnowledgeProcessingContext) -> None:
        if context.current_stage != KnowledgeProcessingStage.INDEX_VALIDATION:
            raise KnowledgeProcessingStageError(
                f"IndexValidationStage cannot execute while current stage is {context.current_stage}"
            )
        if not getattr(context, "embeddings_object_key", None):
            raise KnowledgeProcessingStageError("embeddings_object_key is required")
