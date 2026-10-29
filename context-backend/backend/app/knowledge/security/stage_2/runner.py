from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.knowledge.security.stage_2.context import (
    ArchiveValidationContext,
)
from app.knowledge.security.stage_2.phase_d.context import (
    ChildFileContext,
)
from app.knowledge.security.stage_2.pipeline import (
    run_stage_two,
)


def run_stage_two_for_document(
    *,
    document_id: str,
    upload_id: str,
    project_id: str,
    original_filename: str,
    file_path: Path,
    archive_depth: int = 0,

    persist_callback: Callable[
        [ChildFileContext],
        str,
    ],

    queue_callback: Callable[
        [ChildFileContext],
        None,
    ],

) -> dict[str, Any]:
    
    """
    Application-level entry point for Stage 2.

    The Celery task provides:
      - document information
      - local quarantine file
      - DB registration callback
      - object-storage callback
      - queue callback
    """

    context = ArchiveValidationContext(
        document_id=document_id,
        upload_id=upload_id,
        project_id=project_id,

        original_filename=(
            original_filename
        ),

        file_path=Path(
            file_path
        ),

        archive_depth=archive_depth,
    )

    return run_stage_two(
    context,
    persist_callback=persist_callback,
    queue_callback=queue_callback,
)