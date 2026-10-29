from typing import Any
from pathlib import Path
from typing import Any

from app.knowledge.security.stage_2.constants import (
    PHASE_EXTRACTION,
)
from app.knowledge.security.stage_2.context import (
    ArchiveValidationContext,
)


def build_extraction_report(
    context: ArchiveValidationContext,
) -> dict[str, Any]:

    context.current_phase = PHASE_EXTRACTION
    context.current_check = "extraction_report_generation"

    files = context.extracted_files

    total_bytes = sum(
        item.size
        for item in files
    )

    nested_candidates = [
        item.relative_path
        for item in files
        if item.is_archive_candidate
    ]

    report = {
        "document_id": context.document_id,
        "upload_id": context.upload_id,
        "project_id": context.project_id,

        "archive": context.original_filename,

        "archive_depth": context.archive_depth,

        "extracted_file_count": len(files),
        "extracted_bytes": total_bytes,
        "skipped_entry_count": len(context.skipped_entries),

        "nested_archive_candidates": (
            nested_candidates
        ),

        "files": [
            {
                "relative_path": item.relative_path,
                "filename": item.filename,
                "size": item.size,
                "archive_depth": item.archive_depth,
                "is_archive_candidate": (
                    item.is_archive_candidate
                ),
            }
            for item in files
        ],
    }

    context.extraction_report = report

    return report