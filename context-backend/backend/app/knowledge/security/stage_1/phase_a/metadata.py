from datetime import datetime, timezone

from app.knowledge.security.stage_1.context import ValidationContext
from app.knowledge.security.stage_1.exceptions import FileMetadataError


def collect_file_metadata(context: ValidationContext) -> None:
    try:
        file_path = context.file_path

        stat = file_path.stat()

        context.extension = file_path.suffix.lower()
        context.file_size = stat.st_size

        context.created_at = datetime.fromtimestamp(
            stat.st_ctime,
            tz=timezone.utc,
        )

        context.modified_at = datetime.fromtimestamp(
            stat.st_mtime,
            tz=timezone.utc,
        )

        context.metadata["filename"] = file_path.name
        context.metadata["suffixes"] = [
            suffix.lower()
            for suffix in file_path.suffixes
        ]

    except OSError as exc:
        raise FileMetadataError(
            f"Unable to collect metadata for '{context.original_filename}'.",
            phase="identity_metadata",
            check="metadata_collection",
            code="METADATA_COLLECTION_FAILED",
        ) from exc