from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import EmbeddingStatus
from app.knowledge.uploads.utils import (
    generate_chunk_embedding_id,
    get_next_chunk_embedding_sequence,
)
from app.knowledge.embedding.contract.result import EmbeddingResult
from app.knowledge.uploads.models import ChunkEmbedding, DocumentChunk


class EmbeddingPersistenceService:
    """
    Persists embedding metadata for DocumentChunk records.

    This service does not:
    - generate embeddings
    - call the embedding model
    - write to Chroma
    - commit the database transaction

    It only maps an EmbeddingResult to ChunkEmbedding.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def persist(
        self,
        *,
        chunk: DocumentChunk,
        embedding: EmbeddingResult,
        vector_database: str,
        collection_name: str,
        vector_id: str,
    ) -> ChunkEmbedding:
        """
        Persist one embedding for one DocumentChunk.

        Existing embeddings are reused when the same chunk,
        provider, model, and content hash already exist.
        """

        if not vector_database.strip():
            raise ValueError(
                "vector_database must not be empty"
            )

        if not collection_name.strip():
            raise ValueError(
                "collection_name must not be empty"
            )

        if not vector_id.strip():
            raise ValueError(
                "vector_id must not be empty"
            )

        existing = self._find_existing(
            chunk_id=chunk.chunk_id,
            embedding=embedding,
            content_hash=chunk.content_hash,
        )

        if existing is not None:
            self._validate_existing(
                existing=existing,
                chunk=chunk,
                embedding=embedding,
                vector_database=vector_database,
                collection_name=collection_name,
                vector_id=vector_id,
            )

            return existing

        sequence = get_next_chunk_embedding_sequence(
            self._db
        )

        embedding_id = generate_chunk_embedding_id(
            sequence
        )

        record = ChunkEmbedding(
            embedding_id=embedding_id,
            chunk_id=chunk.chunk_id,
            embedding_provider=embedding.provider,
            embedding_model=embedding.model,
            embedding_model_version=embedding.model_version,
            embedding_dimension=embedding.dimension,
            vector_database=vector_database,
            collection_name=collection_name,
            vector_id=vector_id,
            content_hash=chunk.content_hash,
            status=EmbeddingStatus.PENDING,
            indexed_at=None,
        )

        self._db.add(record)
        self._db.flush()

        return record

    def _find_existing(
        self,
        *,
        chunk_id: str,
        embedding: EmbeddingResult,
        content_hash: str,
    ) -> ChunkEmbedding | None:

        statement = (
            select(ChunkEmbedding)
            .where(
                ChunkEmbedding.chunk_id == chunk_id,
                ChunkEmbedding.embedding_provider
                == embedding.provider,
                ChunkEmbedding.embedding_model
                == embedding.model,
                ChunkEmbedding.content_hash
                == content_hash,
            )
        )

        return self._db.execute(
            statement
        ).scalar_one_or_none()

    @staticmethod
    def _validate_existing(
        *,
        existing: ChunkEmbedding,
        chunk: DocumentChunk,
        embedding: EmbeddingResult,
        vector_database: str,
        collection_name: str,
        vector_id: str,
    ) -> None:

        if existing.chunk_id != chunk.chunk_id:
            raise ValueError(
                "existing embedding belongs to a different chunk"
            )

        if existing.content_hash != chunk.content_hash:
            raise ValueError(
                "existing embedding content_hash does not "
                "match DocumentChunk"
            )

        if existing.embedding_dimension != embedding.dimension:
            raise ValueError(
                "existing embedding dimension does not match "
                "current embedding"
            )

        if existing.vector_database != vector_database:
            raise ValueError(
                "existing embedding vector database does not match"
            )

        if existing.collection_name != collection_name:
            raise ValueError(
                "existing embedding collection does not match"
            )

        if existing.vector_id != vector_id:
            raise ValueError(
                "existing embedding vector_id does not match"
            )