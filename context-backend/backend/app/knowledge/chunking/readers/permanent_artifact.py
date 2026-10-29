import json
from typing import Any

from app.infra.storage.services import ObjectStorageService
from app.knowledge.chunking.contracts.input import ChunkingInput


class PermanentArtifactReader:
    """Reads a security-approved parsed artifact from permanent storage."""

    def __init__(self, storage: ObjectStorageService) -> None:
        self.storage = storage

    def read(
        self,
        *,
        document_id: str,
        document_version_id: str,
        permanent_bucket: str,
        permanent_object_key: str,
    ) -> ChunkingInput:
        response = self.storage.download(
            bucket=permanent_bucket,
            object_key=permanent_object_key,
        )

        try:
            raw = response.read()
        finally:
            response.close()
            response.release_conn()

        try:
            artifact: dict[str, Any] = json.loads(
                raw.decode("utf-8")
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(
                "Permanent parsed artifact is not valid UTF-8 JSON"
            ) from exc

        return self._build_input(
            artifact=artifact,
            document_id=document_id,
            document_version_id=document_version_id,
            permanent_bucket=permanent_bucket,
            permanent_object_key=permanent_object_key,
        )

    @staticmethod
    def _build_input(
        *,
        artifact: dict[str, Any],
        document_id: str,
        document_version_id: str,
        permanent_bucket: str,
        permanent_object_key: str,
    ) -> ChunkingInput:
        required_fields = (
            "document_id",
            "file_name",
            "source_format",
            "content",
            "metadata",
            "page_count",
            "character_count",
            "word_count",
            "mime_type",
        )

        missing = [
            field
            for field in required_fields
            if field not in artifact
        ]

        if missing:
            raise ValueError(
                "Permanent parsed artifact is missing required fields: "
                + ", ".join(missing)
            )

        if not isinstance(artifact["metadata"], dict):
            raise ValueError(
                "Permanent parsed artifact metadata must be an object"
            )

        if not isinstance(artifact["content"], str):
            raise ValueError(
                "Permanent parsed artifact content must be a string"
            )

        if artifact["document_id"] != document_id:
            raise ValueError(
                "Permanent parsed artifact document_id does not match "
                "the requested document"
            )

        return ChunkingInput(
            document_id=document_id,
            document_version_id=document_version_id,
            file_name=artifact["file_name"],
            source_format=artifact["source_format"],
            content=artifact["content"],
            metadata=artifact["metadata"],
            page_count=artifact["page_count"],
            character_count=artifact["character_count"],
            word_count=artifact["word_count"],
            mime_type=artifact["mime_type"],
            permanent_bucket=permanent_bucket,
            permanent_object_key=permanent_object_key,
        )