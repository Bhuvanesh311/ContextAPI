# app/knowledge/security/stage1/phase_c/encoding.py

from charset_normalizer import from_bytes
import chardet

from app.knowledge.security.stage_1.constants import (
    ENCODING_SAMPLE_SIZE,
    FILE_TYPE_TEXT,
    MIN_ENCODING_CONFIDENCE,
)
from app.knowledge.security.stage_1.context import ValidationContext
from app.knowledge.security.stage_1.exceptions import EncodingDetectionError


def detect_encoding(context: ValidationContext) -> None:
    
    if context.content_type != FILE_TYPE_TEXT:
        return

    try:
        with context.file_path.open("rb") as file:
            sample = file.read(ENCODING_SAMPLE_SIZE)

    except OSError as exc:
        raise EncodingDetectionError(
            f"Unable to read '{context.original_filename}' "
            f"for encoding detection.",
            phase="security",
            check="encoding_detection",
            code="ENCODING_READ_FAILED",
        ) from exc

    if not sample:
        raise EncodingDetectionError(
            f"No content available for encoding detection in "
            f"'{context.original_filename}'.",
            phase="security",
            check="encoding_detection",
            code="ENCODING_SAMPLE_EMPTY",
        )

    result = from_bytes(sample).best()

    if result is not None and result.encoding:
        context.encoding = result.encoding

        # charset-normalizer exposes chaos rather than the same
        # confidence model used by chardet.
        context.encoding_confidence = max(
            0.0,
            min(1.0, 1.0 - float(result.chaos)),
        )

        return

    fallback = chardet.detect(sample)

    encoding = fallback.get("encoding")
    confidence = fallback.get("confidence") or 0.0

    if not encoding or confidence < MIN_ENCODING_CONFIDENCE:
        raise EncodingDetectionError(
            f"Unable to reliably determine encoding for "
            f"'{context.original_filename}'.",
            phase="security",
            check="encoding_detection",
            code="ENCODING_NOT_DETECTED",
        )

    context.encoding = encoding
    context.encoding_confidence = float(confidence)