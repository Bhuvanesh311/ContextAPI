from dataclasses import dataclass
from pathlib import Path

from app.knowledge.security.stage_2.constants import (
    PHASE_EXTRACTION,
)
from app.knowledge.security.stage_2.context import (
    ArchiveValidationContext,
)


ARCHIVE_EXTENSIONS = {
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".gz",
    ".tgz",
}


@dataclass(slots=True)
class ExtractedFileMetadata:
    relative_path: str
    absolute_path: Path

    filename: str
    size: int

    parent_document_id: str
    archive_depth: int

    is_archive_candidate: bool = False


def _is_archive_candidate(
    path: Path,
) -> bool:

    name = path.name.lower()

    if name.endswith(".tar.gz"):
        return True

    return (
        path.suffix.lower()
        in ARCHIVE_EXTENSIONS
    )


def collect_extracted_metadata(
    context: ArchiveValidationContext,
) -> list[ExtractedFileMetadata]:
    """
    Collect metadata for successfully extracted regular files.

    No DB writes occur here.
    """

    context.current_phase = PHASE_EXTRACTION
    context.current_check = "extracted_metadata_collection"

    workspace = Path(
        context.extraction_workspace
    ).resolve()

    results: list[ExtractedFileMetadata] = []

    for extracted_path in context.extracted_paths:

        path = Path(
            extracted_path
        ).resolve()

        # Defense in depth.
        try:
            relative = path.relative_to(
                workspace
            )

        except ValueError:
            continue

        if not path.is_file():
            continue

        results.append(
            ExtractedFileMetadata(
                relative_path=relative.as_posix(),
                absolute_path=path,
                filename=path.name,
                size=path.stat().st_size,
                parent_document_id=context.document_id,
                archive_depth=(
                    context.archive_depth + 1
                ),
                is_archive_candidate=(
                    _is_archive_candidate(path)
                ),
            )
        )

    context.extracted_files = results

    return results