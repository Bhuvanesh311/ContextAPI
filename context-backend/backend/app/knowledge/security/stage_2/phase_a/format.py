import tarfile
import zipfile

from app.knowledge.security.stage_2.constants import (
    ArchiveType,
    PHASE_IDENTITY_METADATA,
)
from app.knowledge.security.stage_2.context import (
    ArchiveValidationContext,
)
from app.knowledge.security.stage_2.exceptions import (
    ArchiveFormatError,
    UnsupportedArchiveError,
)


def validate_archive_format(context: ArchiveValidationContext,) -> None:
    """
    Confirm that the file can actually be recognized as the
    archive type selected during archive type detection.

    This does not perform the full integrity/security checks.
    """

    context.current_phase = PHASE_IDENTITY_METADATA
    context.current_check = "archive_format_validation"

    archive_type = context.archive_type

    if archive_type is None:
        raise ArchiveFormatError(
            "Archive type must be detected before format validation.",
            phase=PHASE_IDENTITY_METADATA,
            check="archive_format_validation",
            code="ARCHIVE_TYPE_MISSING",
        )

    file_path = context.file_path

    if not file_path.is_file():
        raise ArchiveFormatError(
            f"Archive file does not exist: '{file_path}'.",
            phase=PHASE_IDENTITY_METADATA,
            check="archive_format_validation",
            code="ARCHIVE_FILE_MISSING",
        )

    try:
        if archive_type == ArchiveType.ZIP:
            valid = zipfile.is_zipfile(file_path)

        elif archive_type in {
            ArchiveType.TAR,
            ArchiveType.TAR_GZ,
        }:
            valid = tarfile.is_tarfile(file_path)

        else:
            raise UnsupportedArchiveError(
                (
                    f"Archive handler for "
                    f"'{archive_type.value}' is not implemented yet."
                ),
                phase=PHASE_IDENTITY_METADATA,
                check="archive_format_validation",
                code="ARCHIVE_HANDLER_NOT_IMPLEMENTED",
                details={
                    "archive_type": archive_type.value,
                },
            )

    except OSError as exc:
        raise ArchiveFormatError(
            (
                f"Unable to inspect archive "
                f"'{context.original_filename}'."
            ),
            phase=PHASE_IDENTITY_METADATA,
            check="archive_format_validation",
            code="ARCHIVE_FORMAT_INSPECTION_FAILED",
        ) from exc

    if not valid:
        context.format_valid = False

        raise ArchiveFormatError(
            (
                f"'{context.original_filename}' is not a valid "
                f"{archive_type.value} archive."
            ),
            phase=PHASE_IDENTITY_METADATA,
            check="archive_format_validation",
            code="INVALID_ARCHIVE_FORMAT",
            details={
                "archive_type": archive_type.value,
            },
        )

    context.format_valid = True