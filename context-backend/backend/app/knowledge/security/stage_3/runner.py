from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from app.knowledge.security.stage_3.context import (
    ValidationContext,
)
from app.knowledge.security.stage_3.pipeline import (
    run_stage_three,
)


def run_stage_three_for_document(
    *,
    upload_id: str | None,
    project_id: str,
    document_id: str,
    parent_document_id: str | None,
    file_path: Path,
    original_filename: str,
    extension: str,
    mime_type: str,
    file_size: int,
    sha256: str,
    persist_callback: Callable[..., Any] | None = None,
    queue_callback: Callable[..., Any] | None = None,
) -> ValidationContext:
    """
    Build the Stage 3 validation context and execute the
    format-specific security validation pipeline.
    """

    context = ValidationContext(
    document_id=document_id,
    project_id=project_id,
    upload_id=upload_id,
    parent_document_id=parent_document_id,
    original_filename=original_filename,
    file_path=file_path,
    extension=extension,
    mime_type=mime_type,
    file_size=file_size,
    sha256=sha256,
)

    return run_stage_three(
        context,
        persist_callback=persist_callback,
        queue_callback=queue_callback,
    )