from typing import Any

from app.knowledge.security.stage_2.context import (
    ArchiveValidationContext,
)
from app.knowledge.security.stage_2.phase_d.context import (
    ChildFileContext,
)


def build_orchestration_summary(
    context: ArchiveValidationContext,
    children: list[ChildFileContext],
) -> dict[str, Any]:

    registered = sum(
        1
        for child in children
        if child.registered
    )

    stored = sum(
        1
        for child in children
        if child.stored
    )

    queued = sum(
        1
        for child in children
        if child.queued
    )

    archive_candidates = sum(
        1
        for child in children
        if child.is_archive_candidate
    )

    failed = sum(
        1
        for child in children
        if child.error is not None
    )

    summary = {
        "parent_document_id": (
            context.document_id
        ),
        "upload_id": (
            context.upload_id
        ),
        "project_id": (
            context.project_id
        ),
        "archive_depth": (
            context.archive_depth
        ),

        "children": len(children),

        "registered": registered,
        "stored": stored,
        "queued": queued,
        "failed": failed,
        "skipped": len(context.skipped_entries),

        "archive_candidates": (
            archive_candidates
        ),

        "items": [
            {
                "document_id": (
                    child.document_id
                ),
                "parent_document_id": (
                    child.parent_document_id
                ),
                "filename": (
                    child.original_filename
                ),
                "relative_path": (
                    child.relative_path
                ),
                "size": (
                    child.size
                ),
                "archive_depth": (
                    child.archive_depth
                ),
                "storage_key": (
                    child.storage_key
                ),
                "next_stage": (
                    child.next_stage
                ),
                "registered": (
                    child.registered
                ),
                "stored": (
                    child.stored
                ),
                "queued": (
                    child.queued
                ),
                "archive_candidate": (
                    child.is_archive_candidate
                ),
                "error": (
                    child.error
                ),
            }
            for child in children
        ],
    }

    return summary