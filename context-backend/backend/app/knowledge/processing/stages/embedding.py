from __future__ import annotations

import hashlib
import io
import json

from app.core.enums import KnowledgeProcessingStage
from app.infra.storage import ObjectStorageService
from app.knowledge.chunking.readers.ndjson import NDJSONReader
from app.knowledge.embedding.services.embedding_service import (
    EmbeddingService,
)
from app.knowledge.cancellation import raise_if_cancelled
from app.knowledge.processing.context import KnowledgeProcessingContext
from app.knowledge.processing.exceptions import (
    KnowledgeProcessingStageError,
)
from app.knowledge.processing.services.chunk_persistence import (
    ChunkPersistenceService,
)
from app.knowledge.processing.services.embedding_persistence import (
    EmbeddingPersistenceService,
)
from app.knowledge.processing.stages.base import (
    BaseKnowledgeProcessingStage,
)


class EmbeddingStage(BaseKnowledgeProcessingStage):
    """
    Generates embeddings for validated canonical chunks
    and persists their embedding metadata.

    Responsibilities:
    - read chunks.ndjson
    - validate chunk ownership
    - persist DocumentChunk records
    - generate embeddings
    - persist ChunkEmbedding records
    - update embedding checkpoint

    Does not:
    - write vectors to Chroma
    - advance the processing run
    - commit the SQLAlchemy transaction
    """

    def __init__(
        self,
        *,
        storage: ObjectStorageService,
        reader: NDJSONReader,
        chunk_persistence: ChunkPersistenceService,
        embedding_service: EmbeddingService,
        embedding_persistence: EmbeddingPersistenceService,
        vector_database: str = "chromadb",
        collection_name: str = "knowledge",
    ) -> None:
        self._storage = storage
        self._reader = reader
        self._chunk_persistence = chunk_persistence
        self._embedding_service = embedding_service
        self._embedding_persistence = embedding_persistence
        self._vector_database = vector_database
        self._collection_name = collection_name

    @property
    def stage_name(self) -> KnowledgeProcessingStage:
        return KnowledgeProcessingStage.EMBEDDING

    def execute(
        self,
        context: KnowledgeProcessingContext,
    ) -> KnowledgeProcessingContext:

        self._validate_context(context)

        chunks_payload = self._storage.download(
            bucket=context.permanent_bucket,
            object_key=context.chunks_object_key,
        )

        try:
            chunks = self._reader.read(chunks_payload)
        finally:
            if chunks_payload is not None:
                chunks_payload.close()

        if not chunks:
            raise KnowledgeProcessingStageError(
                "No canonical chunks found for embedding"
            )

        self._validate_chunks(
            context=context,
            chunks=chunks,
        )

        document_chunks = self._chunk_persistence.persist(
            document_version_id=context.document_version_id,
            chunks=chunks,
        )

        if len(document_chunks) != len(chunks):
            raise KnowledgeProcessingStageError(
                "Persisted DocumentChunk count does not match "
                "canonical chunk count"
            )

        persisted_embeddings = []
        ndjson_buffer = io.BytesIO()

        for document_chunk, canonical_chunk in zip(
            document_chunks,
            chunks,
            strict=True,
        ):
            # Embedding is the long part of indexing: stop between chunks.
            raise_if_cancelled(context.document_version_id)

            embedding = self._embedding_service.embed(
                canonical_chunk.content
            )

            vector_id = self._build_vector_id(
                document_version_id=(
                    context.document_version_id
                ),
                chunk_index=canonical_chunk.chunk_index,
                content_hash=canonical_chunk.content_hash,
                provider=embedding.provider,
                model=embedding.model,
            )

            record = {
                "document_id": context.document_id,
                "document_version_id": context.document_version_id,
                "chunk_index": canonical_chunk.chunk_index,
                "vector_id": vector_id,
                "content_hash": canonical_chunk.content_hash,
                "dimension": embedding.dimension,
                "provider": embedding.provider,
                "model": embedding.model,
                "vector": list(embedding.vector),
            }

            line = json.dumps(
                record, separators=(",", ":")
            ).encode("utf-8") + b"\n"
            ndjson_buffer.write(line)

            persisted_embedding = (
                self._embedding_persistence.persist(
                    chunk=document_chunk,
                    embedding=embedding,
                    vector_database=self._vector_database,
                    collection_name=self._collection_name,
                    vector_id=vector_id,
                )
            )

            persisted_embeddings.append(
                persisted_embedding
            )

        upload_data = ndjson_buffer.getvalue()

        self._storage.upload(
            bucket=context.permanent_bucket,
            object_key=context.embeddings_object_key,
            data=io.BytesIO(upload_data),
            size=len(upload_data),
            content_type="application/x-ndjson",
        )

        checkpoint_data = dict(
            context.checkpoint_data
        )

        checkpoint_data["embedding"] = {
            "completed": True,
            "chunk_count": len(chunks),
            "embedding_count": len(
                persisted_embeddings
            ),
            "embedding_dimension": (
                self._embedding_service.provider.dimension
            ),
            "provider": (
                self._embedding_service.provider.provider_name
            ),
            "model": (
                self._embedding_service.provider.model_name
            ),
            "vector_database": self._vector_database,
            "collection_name": self._collection_name,
            "embeddings_object_key": context.embeddings_object_key,
        }

        return KnowledgeProcessingContext(
            knowledge_processing_run_id=(
                context.knowledge_processing_run_id
            ),
            document_id=context.document_id,
            document_version_id=(
                context.document_version_id
            ),
            permanent_bucket=context.permanent_bucket,
            permanent_object_key=(
                context.permanent_object_key
            ),
            chunks_object_key=context.chunks_object_key,
            embeddings_object_key=context.embeddings_object_key,
            current_stage=context.current_stage,
            checkpoint_data=checkpoint_data,
        )

    @staticmethod
    def _validate_context(
        context: KnowledgeProcessingContext,
    ) -> None:

        if context.current_stage != (
            KnowledgeProcessingStage.EMBEDDING
        ):
            raise KnowledgeProcessingStageError(
                "EmbeddingStage cannot execute while current "
                f"stage is {context.current_stage}"
            )

        if not context.document_id.strip():
            raise KnowledgeProcessingStageError(
                "document_id is required for embedding"
            )

        if not context.document_version_id.strip():
            raise KnowledgeProcessingStageError(
                "document_version_id is required for embedding"
            )

        if not context.permanent_bucket:
            raise KnowledgeProcessingStageError(
                "Permanent storage bucket is required "
                "for embedding"
            )

        if not context.chunks_object_key:
            raise KnowledgeProcessingStageError(
                "Chunks object key is required for embedding"
            )

        if not getattr(context, "embeddings_object_key", None):
            raise KnowledgeProcessingStageError(
                "Embeddings object key is required for embedding"
            )

    @staticmethod
    def _validate_chunks(
        *,
        context: KnowledgeProcessingContext,
        chunks,
    ) -> None:

        seen_indices: set[int] = set()

        for chunk in chunks:

            if chunk.document_id != context.document_id:
                raise KnowledgeProcessingStageError(
                    "Chunk document_id does not match "
                    "processing context"
                )

            if chunk.document_version_id != (
                context.document_version_id
            ):
                raise KnowledgeProcessingStageError(
                    "Chunk document_version_id does not "
                    "match processing context"
                )

            if chunk.chunk_index in seen_indices:
                raise KnowledgeProcessingStageError(
                    "Duplicate chunk_index detected: "
                    f"{chunk.chunk_index}"
                )

            seen_indices.add(chunk.chunk_index)

    @staticmethod
    def _build_vector_id(
        *,
        document_version_id: str,
        chunk_index: int,
        content_hash: str,
        provider: str,
        model: str,
    ) -> str:
        """
        Build a deterministic vector identifier.

        The same document version, chunk, content,
        provider, and model always produce the same ID.
        """

        identity = (
            f"{document_version_id}:"
            f"{chunk_index}:"
            f"{content_hash}:"
            f"{provider}:"
            f"{model}"
        )

        return hashlib.sha256(
            identity.encode("utf-8")
        ).hexdigest()