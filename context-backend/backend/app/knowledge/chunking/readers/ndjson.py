from __future__ import annotations

import json
from typing import Any, BinaryIO

from app.knowledge.chunking.contracts.chunk import CanonicalChunk
from app.knowledge.chunking.validation.chunk import CanonicalChunkValidator


class NDJSONReader:
    """
    Reads persisted NDJSON data and reconstructs CanonicalChunk objects.

    Every reconstructed chunk is validated before being returned.
    """

    def __init__(
        self,
        validator: CanonicalChunkValidator | None = None,
    ) -> None:
        self.validator = validator or CanonicalChunkValidator()

    def read(
        self,
        data: BinaryIO,
    ) -> list[CanonicalChunk]:
        raw = data.read()

        if isinstance(raw, str):
            raw = raw.encode("utf-8")

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(
                "NDJSON data is not valid UTF-8"
            ) from exc

        chunks: list[CanonicalChunk] = []

        for line_number, line in enumerate(
            text.splitlines(),
            start=1,
        ):
            if not line.strip():
                continue

            try:
                record: Any = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid NDJSON at line {line_number}"
                ) from exc

            if not isinstance(record, dict):
                raise ValueError(
                    f"NDJSON line {line_number} must contain an object"
                )

            chunk = self._build_chunk(
                record=record,
                line_number=line_number,
            )

            self.validator.validate(chunk)

            chunks.append(chunk)

        return chunks

    @staticmethod
    def _build_chunk(
        *,
        record: dict[str, Any],
        line_number: int,
    ) -> CanonicalChunk:
        required_fields = (
            "document_id",
            "document_version_id",
            "chunk_index",
            "content",
            "content_hash",
            "character_count",
            "token_count",
            "metadata",
        )

        missing = [
            field
            for field in required_fields
            if field not in record
        ]

        if missing:
            raise ValueError(
                f"NDJSON line {line_number} is missing required "
                f"fields: {', '.join(missing)}"
            )

        return CanonicalChunk(
            document_id=record["document_id"],
            document_version_id=record["document_version_id"],
            chunk_index=record["chunk_index"],
            content=record["content"],
            content_hash=record["content_hash"],
            character_count=record["character_count"],
            token_count=record["token_count"],
            metadata=record["metadata"],
        )