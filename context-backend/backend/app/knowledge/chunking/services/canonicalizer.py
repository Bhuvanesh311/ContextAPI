import hashlib

from langchain_core.documents import Document

from app.knowledge.chunking.contracts.chunk import CanonicalChunk
from app.knowledge.chunking.contracts.input import ChunkingInput
from app.knowledge.chunking.validation.chunk import CanonicalChunkValidator


class ChunkCanonicalizer:
    def __init__(
        self,
        validator: CanonicalChunkValidator | None = None,
    ) -> None:
        self.validator = validator or CanonicalChunkValidator()

    def canonicalize(
        self,
        *,
        documents: list[Document],
        chunking_input: ChunkingInput,
    ) -> list[CanonicalChunk]:
        chunks: list[CanonicalChunk] = []

        for document in documents:
            content = document.page_content

            if not isinstance(content, str):
                raise ValueError(
                    "Chunk content must be a string"
                )

            if not content.strip():
                continue

            content_hash = hashlib.sha256(
                content.encode("utf-8")
            ).hexdigest()

            chunk = CanonicalChunk(
                document_id=chunking_input.document_id,
                document_version_id=chunking_input.document_version_id,
                chunk_index=len(chunks),
                content=content,
                content_hash=content_hash,
                character_count=len(content),
                token_count=None,
                metadata=dict(document.metadata),
            )

            self.validator.validate(chunk)

            chunks.append(chunk)

        return chunks