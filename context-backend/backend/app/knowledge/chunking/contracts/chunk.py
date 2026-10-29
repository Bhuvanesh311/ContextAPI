from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CanonicalChunk:
    document_id: str
    document_version_id: str
    chunk_index: int
    content: str
    content_hash: str
    character_count: int
    token_count: int | None
    metadata: dict[str, Any] = field(default_factory=dict)