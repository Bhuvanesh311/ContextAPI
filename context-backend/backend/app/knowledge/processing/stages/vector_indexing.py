import json
from typing import Any

from app.core.enums import KnowledgeProcessingStage
from app.infra.storage import ObjectStorageService
from app.knowledge.chunking.readers.ndjson import NDJSONReader
from app.knowledge.processing.context import KnowledgeProcessingContext
from app.knowledge.processing.exceptions import KnowledgeProcessingStageError
from app.knowledge.processing.services.indexing_persistence import IndexingPersistenceService
from app.knowledge.processing.stages.base import BaseKnowledgeProcessingStage


class VectorIndexingStage(BaseKnowledgeProcessingStage):
    def __init__(
        self,
        *,
        storage: ObjectStorageService,
        reader: NDJSONReader,
        chroma_client: Any,
        indexing_persistence: IndexingPersistenceService,
        collection_name: str = "knowledge",
    ) -> None:
        self._storage = storage
        self._reader = reader
        self._chroma_client = chroma_client
        self._indexing_persistence = indexing_persistence
        self._collection_name = collection_name

    @property
    def stage_name(self) -> KnowledgeProcessingStage:
        return KnowledgeProcessingStage.VECTOR_INDEXING

    def execute(
        self,
        context: KnowledgeProcessingContext,
    ) -> KnowledgeProcessingContext:
        self._validate_context(context)

        embeddings_payload = self._storage.download(
            bucket=context.permanent_bucket,
            object_key=context.embeddings_object_key,
        )
        embeddings_data = embeddings_payload.read()
        if isinstance(embeddings_data, bytes):
            embeddings_data = embeddings_data.decode("utf-8")

        chunks_payload = self._storage.download(
            bucket=context.permanent_bucket,
            object_key=context.chunks_object_key,
        )
        chunks = self._reader.read(chunks_payload)
        chunks_by_index = {chunk.chunk_index: chunk for chunk in chunks}

        ids = []
        embeddings = []
        metadatas = []
        documents = []

        for line_number, line in enumerate(embeddings_data.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise KnowledgeProcessingStageError(
                    f"Invalid NDJSON at line {line_number}"
                ) from exc

            self._validate_record(context, record, line_number)
            
            chunk_index = record["chunk_index"]
            if chunk_index not in chunks_by_index:
                raise KnowledgeProcessingStageError(
                    f"Chunk index {chunk_index} from embeddings not found in chunks.ndjson"
                )
            
            chunk = chunks_by_index[chunk_index]
            if chunk.content_hash != record["content_hash"]:
                raise KnowledgeProcessingStageError(
                    f"Content hash mismatch for chunk_index {chunk_index}"
                )

            ids.append(record["vector_id"])
            embeddings.append(record["vector"])
            documents.append(chunk.content)
            metadatas.append({
                "document_id": context.document_id,
                "document_version_id": context.document_version_id,
                "chunk_index": chunk_index,
                "content_hash": chunk.content_hash,
                "provider": record["provider"],
                "model": record["model"],
                "dimension": record["dimension"],
            })

        if not ids:
            raise KnowledgeProcessingStageError("No embeddings found to index")

        collection = self._chroma_client.get_or_create_collection(self._collection_name)
        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents,
        )

        self._indexing_persistence.mark_indexed(ids)

        checkpoint_data = dict(context.checkpoint_data)
        checkpoint_data["vector_indexing"] = {
            "completed": True,
            "vector_count": len(ids),
            "indexed_count": len(ids),
            "vector_database": "chromadb",
            "collection_name": self._collection_name,
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
        if context.current_stage != KnowledgeProcessingStage.VECTOR_INDEXING:
            raise KnowledgeProcessingStageError(
                f"VectorIndexingStage cannot execute while current stage is {context.current_stage}"
            )
        if not getattr(context, "embeddings_object_key", None):
            raise KnowledgeProcessingStageError("embeddings_object_key is required")
        if not context.chunks_object_key:
            raise KnowledgeProcessingStageError("chunks_object_key is required")

    @staticmethod
    def _validate_record(context: KnowledgeProcessingContext, record: dict[str, Any], line_number: int) -> None:
        required = ("document_id", "document_version_id", "chunk_index", "vector_id", "content_hash", "dimension", "provider", "model", "vector")
        for field in required:
            if field not in record:
                raise KnowledgeProcessingStageError(f"Missing {field} in embeddings record at line {line_number}")
        if record["document_id"] != context.document_id:
            raise KnowledgeProcessingStageError(f"Document ID mismatch at line {line_number}")
        if record["document_version_id"] != context.document_version_id:
            raise KnowledgeProcessingStageError(f"Document Version ID mismatch at line {line_number}")
        if len(record["vector"]) != record["dimension"]:
            raise KnowledgeProcessingStageError(f"Vector length does not match dimension at line {line_number}")
