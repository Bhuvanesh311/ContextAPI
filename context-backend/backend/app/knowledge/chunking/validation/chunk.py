from __future__ import annotations

import hashlib

from app.knowledge.chunking.contracts.chunk import CanonicalChunk


class CanonicalChunkValidator:
    """
    Validates the invariants of a CanonicalChunk.

    This validator does not mutate the chunk.
    It only verifies that the canonical representation is valid.
    """

    def validate(self, chunk: CanonicalChunk) -> None:
        if not isinstance(chunk, CanonicalChunk):
            raise TypeError(
                "chunk must be an instance of CanonicalChunk"
            )

        if not isinstance(chunk.document_id, str) or not chunk.document_id.strip():
            raise ValueError(
                "document_id must be a non-empty string"
            )

        if (
            not isinstance(chunk.document_version_id, str)
            or not chunk.document_version_id.strip()
        ):
            raise ValueError(
                "document_version_id must be a non-empty string"
            )

        if not isinstance(chunk.chunk_index, int):
            raise TypeError(
                "chunk_index must be an integer"
            )

        if chunk.chunk_index < 0:
            raise ValueError(
                "chunk_index cannot be negative"
            )

        if not isinstance(chunk.content, str):
            raise TypeError(
                "content must be a string"
            )

        if not chunk.content.strip():
            raise ValueError(
                "content cannot be empty"
            )

        if not isinstance(chunk.content_hash, str):
            raise TypeError(
                "content_hash must be a string"
            )

        expected_hash = hashlib.sha256(
            chunk.content.encode("utf-8")
        ).hexdigest()

        if chunk.content_hash != expected_hash:
            raise ValueError(
                "content_hash does not match content"
            )

        if not isinstance(chunk.character_count, int):
            raise TypeError(
                "character_count must be an integer"
            )

        if chunk.character_count < 0:
            raise ValueError(
                "character_count cannot be negative"
            )

        if chunk.character_count != len(chunk.content):
            raise ValueError(
                "character_count does not match content"
            )

        if chunk.token_count is not None:
            if not isinstance(chunk.token_count, int):
                raise TypeError(
                    "token_count must be an integer or None"
                )

            if chunk.token_count < 0:
                raise ValueError(
                    "token_count cannot be negative"
                )

        if not isinstance(chunk.metadata, dict):
            raise TypeError(
                "metadata must be a dictionary"
            )