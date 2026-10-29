from __future__ import annotations

from typing import Any, Callable

from app.knowledge.security.stage_3.runner import (
    run_stage_three_for_document,
)


def execute_stage_three(
    *,
    upload_id: str | None,
    project_id: str,
    document_id: str,
    parent_document_id: str | None,
    file_path,
    original_filename: str,
    extension: str,
    mime_type: str,
    file_size: int,
    sha256: str,
    persist_callback: Callable[..., Any] | None = None,
    queue_callback: Callable[..., Any] | None = None,
):
    """
    Execute Stage 3 - Format Specific Security Validation.

    This service is responsible only for orchestrating the
    Stage 3 pipeline. It does not perform validation itself.
    """

    return run_stage_three_for_document(
    upload_id=upload_id,
    project_id=project_id,
    document_id=document_id,
    parent_document_id=parent_document_id,
    file_path=file_path,
    original_filename=original_filename,
    extension=extension,
    mime_type=mime_type,
    file_size=file_size,
    sha256=sha256,
    persist_callback=persist_callback,
    queue_callback=queue_callback,
)