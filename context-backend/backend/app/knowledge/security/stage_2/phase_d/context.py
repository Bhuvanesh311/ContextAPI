from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ChildFileContext:
    """
    Runtime state for one file extracted from an archive.

    This is NOT a SQLAlchemy model.
    """

    parent_document_id: str

    upload_id: str
    project_id: str

    relative_path: str
    source_path: Path

    original_filename: str
    size: int

    archive_depth: int

    is_archive_candidate: bool = False

    # Filled during Phase D
    document_id: str | None = None
    storage_key: str | None = None

    registered: bool = False
    stored: bool = False
    queued: bool = False

    next_stage: str | None = None

    error: str | None = None

    metadata: dict[str, Any] | None = None