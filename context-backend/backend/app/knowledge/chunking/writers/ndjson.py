import io
import json

from app.infra.storage.services import ObjectStorageService
from app.knowledge.chunking.contracts.chunk import CanonicalChunk


class NDJSONWriter:
    """Serializes canonical chunks and stores them as NDJSON."""

    CONTENT_TYPE = "application/x-ndjson"

    def __init__(self, storage: ObjectStorageService) -> None:
        self.storage = storage

    def write(
        self,
        *,
        chunks: list[CanonicalChunk],
        bucket: str,
        object_key: str,
    ) -> None:
        buffer = io.BytesIO()

        for chunk in chunks:
            record = {
                "document_id": chunk.document_id,
                "document_version_id": chunk.document_version_id,
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
                "content_hash": chunk.content_hash,
                "character_count": chunk.character_count,
                "token_count": chunk.token_count,
                "metadata": chunk.metadata,
            }

            line = json.dumps(
                record,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")

            buffer.write(line)
            buffer.write(b"\n")

        data = buffer.getvalue()

        self.storage.upload(
            bucket=bucket,
            object_key=object_key,
            data=io.BytesIO(data),
            size=len(data),
            content_type=self.CONTENT_TYPE,
        )