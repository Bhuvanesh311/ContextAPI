from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ChunkingInput:
    document_id: str
    document_version_id: str
    file_name: str
    source_format: str
    content: str
    metadata: dict[str, Any]
    page_count: int
    character_count: int
    word_count: int
    mime_type: str
    permanent_bucket: str
    permanent_object_key: str