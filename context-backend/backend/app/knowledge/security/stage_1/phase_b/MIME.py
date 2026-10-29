import zipfile

import magic

from app.knowledge.security.stage_1.context import ValidationContext
from app.knowledge.security.stage_1.exceptions import MimeDetectionError



# MIME constants


DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument."
    "wordprocessingml.document"
)

GENERIC_BINARY_MIMES = frozenset(
    {
        "application/octet-stream",
        "application/zip",
        "application/x-zip",
        "application/x-zip-compressed",
    }
)



# Helpers


def _normalize_mime_type(mime_type: str) -> str:
    """
    Normalize a MIME type returned by libmagic.

    Examples:
        "Application/ZIP" -> "application/zip"
        "application/gzip; charset=binary" -> "application/gzip"

    MIME detection only identifies the physical representation.
    Format-specific validation belongs to later validation stages.
    """

    return mime_type.lower().strip().split(";", 1)[0].strip()


def _is_docx_package(context: ValidationContext) -> bool:
    """
    Determine whether a ZIP-based file has the minimum structural
    evidence required to identify it as a DOCX package.

    This is identification only.

    Deep OOXML structural and security validation belongs to
    Stage 3 format-specific validation.
    """

    try:
        if not zipfile.is_zipfile(context.file_path):
            return False

        with zipfile.ZipFile(context.file_path, "r") as archive:
            names = set(archive.namelist())

            required_entries = {
                "[Content_Types].xml",
                "word/document.xml",
            }

            return required_entries.issubset(names)

    except (OSError, zipfile.BadZipFile):
        return False



# MIME detection


def detect_mime_type(context: ValidationContext) -> None:
    """
    Detect and record the physical MIME type of an uploaded file.

    libmagic is the primary MIME detector.

    Some container-based formats, such as DOCX, may be reported by
    libmagic as generic ZIP/binary content. In those cases, minimal
    package inspection may refine the MIME identity.

    Archive formats are NOT structurally inspected here.

    Examples:
        .tar
            -> application/x-tar

        .tar.gz / .tgz
            -> application/gzip

        .zip
            -> application/zip

    Stage 2 is responsible for verifying archive structure and safely
    handling archive contents.
    """

    try:
        detected_mime = magic.from_file(
            str(context.file_path),
            mime=True,
        )

        if not detected_mime:
            raise MimeDetectionError(
                (
                    "Unable to determine MIME type for "
                    f"'{context.original_filename}'."
                ),
                phase="integrity_trust",
                check="mime_detection",
                code="MIME_NOT_DETECTED",
            )

        detected_mime = _normalize_mime_type(detected_mime)

        
        # DOCX / OOXML identification fallback
        

        if (
            context.extension.lower() == ".docx"
            and detected_mime in GENERIC_BINARY_MIMES
            and _is_docx_package(context)
        ):
            detected_mime = DOCX_MIME

        context.detected_mime = detected_mime

    except MimeDetectionError:
        raise

    except (OSError, magic.MagicException) as exc:
        raise MimeDetectionError(
            (
                "MIME detection failed for "
                f"'{context.original_filename}'."
            ),
            phase="integrity_trust",
            check="mime_detection",
            code="MIME_DETECTION_FAILED",
        ) from exc