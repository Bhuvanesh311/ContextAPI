from pathlib import Path

from app.knowledge.security.stage_2.constants import (
    ARCHIVE_EXTENSION_MAP,
    ARCHIVE_MIME_MAP,
    ArchiveType,
    PHASE_IDENTITY_METADATA,
)
from app.knowledge.security.stage_2.context import (
    ArchiveValidationContext,
)
from app.knowledge.security.stage_2.exceptions import (
    ArchiveTypeDetectionError,
    UnsupportedArchiveError,
)


def _get_archive_extension(filename: str) -> str:
    """
    Return the normalized archive extension.

    Multi-part extensions such as .tar.gz must be checked
    before Path.suffix, which would return only '.gz'.
    """

    filename_lower = filename.lower()

    if filename_lower.endswith(".tar.gz"):
        return ".tar.gz"

    return Path(filename_lower).suffix


def detect_archive_type(context: ArchiveValidationContext,) -> ArchiveType:
    """
    Determine archive type using both filename extension and
    MIME evidence inherited from Stage 1.

    Phase A identifies the expected archive handler. Actual
    archive readability is confirmed separately by format.py.
    """

    context.current_phase = PHASE_IDENTITY_METADATA
    context.current_check = "archive_type_detection"

    extension = _get_archive_extension(
        context.original_filename
    )

    extension_type = ARCHIVE_EXTENSION_MAP.get(extension)

    mime = (
        context.detected_mime.lower().strip()
        if context.detected_mime
        else None
    )

    mime_type = (
        ARCHIVE_MIME_MAP.get(mime)
        if mime
        else None
    )

    if extension_type is None:
        raise UnsupportedArchiveError(
            (
                f"Unsupported archive extension '{extension}' "
                f"for '{context.original_filename}'."
            ),
            phase=PHASE_IDENTITY_METADATA,
            check="archive_type_detection",
            code="UNSUPPORTED_ARCHIVE_EXTENSION",
            details={
                "filename": context.original_filename,
                "extension": extension,
                "detected_mime": mime,
            },
        )

    # MIME evidence exists and directly contradicts extension.
    if mime_type is not None and mime_type != extension_type:
        raise ArchiveTypeDetectionError(
            (
                f"Archive extension '{extension}' indicates "
                f"'{extension_type.value}', but detected MIME "
                f"'{mime}' indicates '{mime_type.value}'."
            ),
            phase=PHASE_IDENTITY_METADATA,
            check="archive_type_detection",
            code="ARCHIVE_TYPE_MISMATCH",
            details={
                "filename": context.original_filename,
                "extension": extension,
                "extension_type": extension_type.value,
                "detected_mime": mime,
                "mime_type": mime_type.value,
            },
        )

    context.archive_type = extension_type

    return extension_type