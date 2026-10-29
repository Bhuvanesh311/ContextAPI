from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import (
    ChunkLevel,
    ChunkType,
    DocumentChunkStatus,
)
from app.knowledge.uploads.utils import (
    generate_document_chunk_id,
    get_next_document_chunk_sequence,
)
from app.knowledge.chunking.contracts.chunk import CanonicalChunk
from app.knowledge.uploads.models import DocumentChunk


class ChunkPersistenceService:
    """
    Persists canonical chunks into DocumentChunk records.

    Responsibilities:
    - persist CanonicalChunk records
    - preserve chunk ordering
    - enforce document-version ownership
    - provide idempotent persistence
    - avoid creating duplicate chunks

    This service does not:
    - generate embeddings
    - write to Chroma
    - manage KnowledgeProcessingRun state
    - write chunk vectors
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def persist(
        self,
        *,
        document_version_id: str,
        chunks: Sequence[CanonicalChunk],
    ) -> list[DocumentChunk]:
        """
        Persist canonical chunks for one document version.

        Existing chunks are reused based on:
            (document_version_id, chunk_index)

        Returns all persisted/reused DocumentChunk records in
        chunk_index order.
        """

        if not document_version_id.strip():
            raise ValueError(
                "document_version_id must not be empty"
            )

        if not chunks:
            raise ValueError(
                "chunks must not be empty"
            )

        self._validate_chunks(
            document_version_id=document_version_id,
            chunks=chunks,
        )

        persisted_chunks: list[DocumentChunk] = []

        for canonical_chunk in chunks:
            existing = self._get_existing_chunk(
                document_version_id=document_version_id,
                chunk_index=canonical_chunk.chunk_index,
            )

            if existing is not None:
                self._validate_existing_chunk(
                    existing=existing,
                    canonical_chunk=canonical_chunk,
                )

                persisted_chunks.append(existing)
                continue

            chunk = self._create_chunk(
                document_version_id=document_version_id,
                canonical_chunk=canonical_chunk,
            )

            self._db.add(chunk)
            persisted_chunks.append(chunk)

        self._db.flush()

        persisted_chunks.sort(
            key=lambda chunk: chunk.chunk_index
        )

        return persisted_chunks

    def _get_existing_chunk(
        self,
        *,
        document_version_id: str,
        chunk_index: int,
    ) -> DocumentChunk | None:

        statement = (
            select(DocumentChunk)
            .where(
                DocumentChunk.document_version_id
                == document_version_id,
                DocumentChunk.chunk_index
                == chunk_index,
            )
        )

        return self._db.execute(statement).scalar_one_or_none()

    def _create_chunk(
        self,
        *,
        document_version_id: str,
        canonical_chunk: CanonicalChunk,
    ) -> DocumentChunk:

        sequence = get_next_document_chunk_sequence(
            self._db
        )

        chunk_id = generate_document_chunk_id(
            sequence
        )

        metadata = dict(canonical_chunk.metadata)

        chunk_type = self._resolve_chunk_type(
            metadata
        )

        chunking_strategy = self._resolve_chunking_strategy(
            metadata
        )

        source_locator = self._resolve_source_locator(
            metadata
        )

        return DocumentChunk(
            chunk_id=chunk_id,
            document_version_id=document_version_id,
            parent_chunk_id=None,
            chunk_index=canonical_chunk.chunk_index,
            chunk_level=ChunkLevel.CHUNK,
            status=DocumentChunkStatus.CREATED,
            content=canonical_chunk.content,
            content_hash=canonical_chunk.content_hash,
            token_count=canonical_chunk.token_count or 0,
            source_locator=source_locator,
            chunk_type=chunk_type,
            chunking_strategy=chunking_strategy,
            chunk_metadata=metadata,
        )

    @staticmethod
    def _validate_chunks(
        *,
        document_version_id: str,
        chunks: Sequence[CanonicalChunk],
    ) -> None:

        seen_indices: set[int] = set()

        for chunk in chunks:

            if chunk.document_version_id != document_version_id:
                raise ValueError(
                    "canonical chunk document_version_id does not "
                    "match persistence document_version_id"
                )

            if chunk.chunk_index in seen_indices:
                raise ValueError(
                    f"duplicate chunk_index: "
                    f"{chunk.chunk_index}"
                )

            seen_indices.add(chunk.chunk_index)

    @staticmethod
    def _validate_existing_chunk(
        *,
        existing: DocumentChunk,
        canonical_chunk: CanonicalChunk,
    ) -> None:

        if existing.content_hash != canonical_chunk.content_hash:
            raise ValueError(
                "existing DocumentChunk content_hash does not "
                "match canonical chunk"
            )

        if existing.content != canonical_chunk.content:
            raise ValueError(
                "existing DocumentChunk content does not "
                "match canonical chunk"
            )

        if existing.document_version_id != (
            canonical_chunk.document_version_id
        ):
            raise ValueError(
                "existing DocumentChunk belongs to a different "
                "document version"
            )

    @staticmethod
    def _resolve_chunk_type(
        metadata: dict,
    ) -> str:

        value = metadata.get("chunk_type")

        if value is None:
            return ChunkType.RECURSIVE.value

        if isinstance(value, ChunkType):
            return value.value

        if not isinstance(value, str):
            raise ValueError(
                "chunk_type metadata must be a string"
            )

        if not value.strip():
            raise ValueError(
                "chunk_type metadata must not be empty"
            )

        return value

    @staticmethod
    def _resolve_chunking_strategy(
        metadata: dict,
    ) -> str:

        value = metadata.get("chunking_strategy")

        if value is None:
            return "framework"

        if not isinstance(value, str):
            raise ValueError(
                "chunking_strategy metadata must be a string"
            )

        if not value.strip():
            raise ValueError(
                "chunking_strategy metadata must not be empty"
            )

        return value

    @staticmethod
    def _resolve_source_locator(
        metadata: dict,
    ) -> dict | None:

        value = metadata.get("source_locator")

        if value is None:
            return None

        if not isinstance(value, dict):
            raise ValueError(
                "source_locator metadata must be a dictionary"
            )

        return value