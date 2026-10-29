from app.knowledge.security.stage_1.constants import (
    CONTENT_SAMPLE_SIZE,
    FILE_TYPE_BINARY,
    FILE_TYPE_TEXT,
    FILE_TYPE_UNKNOWN,
    NULL_BYTE,
)

from app.knowledge.security.stage_1.context import ValidationContext
from app.knowledge.security.stage_1.exceptions import ContentDetectionError



# MIME Classification



# MIME types whose payload is fundamentally textual.
TEXTUAL_APPLICATION_MIME_TYPES = {
    "application/json",
    "application/xml",
    "application/javascript",
    "application/sql",
    "application/yaml",
    "application/x-yaml",
    "application/toml",
}


# MIME types where MIME detection did not give us enough
# information to classify the content.
INCONCLUSIVE_MIME_TYPES = {
    "application/octet-stream",
    "binary/octet-stream",
    "application/x-binary",
}


def _is_textual_mime(detected_mime: str,) -> bool:
    """
    Return True when the detected MIME type represents textual
    content.
    """

    if detected_mime.startswith("text/"):
        return True

    if detected_mime in TEXTUAL_APPLICATION_MIME_TYPES:
        return True

    if detected_mime.endswith("+json"):
        return True

    if detected_mime.endswith("+xml"):
        return True

    return False


def detect_content_type(context: ValidationContext,) -> None:
    """
    Classify the file as text, binary, or unknown.

    Stage 1 MIME detection has already happened before this check,
    so MIME evidence is preferred over byte heuristics.

    Byte inspection is only used when MIME detection was
    inconclusive.
    """

    detected_mime = (context.detected_mime or "").lower().strip()

    
    # 1. Known textual MIME
    

    if detected_mime and _is_textual_mime(
        detected_mime
    ):
        context.content_type = FILE_TYPE_TEXT
        return

    
    # 2. Known non-text MIME
    
    #
    # Examples:
    #
    # application/pdf
    # application/zip
    # application/vnd.openxmlformats-...
    #
    # These are binary/container formats.
    #
    # Do NOT try to determine whether their raw bytes happen
    # to decode as UTF-8.

    if (
        detected_mime
        and detected_mime not in INCONCLUSIVE_MIME_TYPES
    ):
        context.content_type = FILE_TYPE_BINARY
        return

    
    # 3. MIME unavailable/inconclusive
    

    try:
        with context.file_path.open("rb") as file:
            sample = file.read(
                CONTENT_SAMPLE_SIZE
            )

    except OSError as exc:
        raise ContentDetectionError(
            f"Unable to inspect content of "
            f"'{context.original_filename}'.",
            phase="security",
            check="binary_text_detection",
            code="CONTENT_READ_FAILED",
        ) from exc

    
    # 4. Empty content
    

    if not sample:
        context.content_type = FILE_TYPE_UNKNOWN
        return

    
    # 5. Null byte strongly indicates binary content
    

    if NULL_BYTE in sample:
        context.content_type = FILE_TYPE_BINARY
        return

    
    # 6. UTF-8 fallback
    
    #
    # Only used because MIME detection was inconclusive.
    #
    # This MUST NOT override a known application/pdf,
    # application/zip, etc.

    try:
        sample.decode("utf-8")

    except UnicodeDecodeError:
        context.content_type = FILE_TYPE_BINARY
        return

    context.content_type = FILE_TYPE_TEXT