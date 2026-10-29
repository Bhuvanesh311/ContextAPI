from __future__ import annotations

import csv
import string
import unicodedata

from app.knowledge.security.stage_3.context import (
    ValidationContext,
)
from app.knowledge.security.stage_3.exceptions import (
    FormatSecurityError,
)


# ============================================================
# Common Text Validation
# ============================================================

TEXT_ENCODING = "utf-8"

MAX_TEXT_FILE_SIZE = 50 * 1024 * 1024          # 50 MB

MAX_TEXT_LINE_LENGTH = 100_000

MAX_CONTROL_CHARACTER_RATIO = 0.01

ALLOWED_CONTROL_CHARACTERS = {
    "\n",
    "\r",
    "\t",
    "\f",   # page break (common in text exported from PDFs)
    "\v",
}

# ============================================================
# Binary Detection
# ============================================================

BINARY_SAMPLE_SIZE = 8192

MAX_NULL_BYTES = 0

# ============================================================
# Markdown Security
# ============================================================

DANGEROUS_HTML_TAGS = {
    "script",
    "iframe",
    "object",
    "embed",
}

DANGEROUS_HTML_ATTRIBUTES = {
    "onclick",
    "onload",
    "onerror",
    "onmouseover",
    "onfocus",
    "onmouseenter",
}

DANGEROUS_URI_SCHEMES = (
    "javascript:",
    "vbscript:",
    "data:",
    "file:",
)

# ============================================================
# CSV Security
# ============================================================

CSV_FORMULA_PREFIXES = (
    "=",
    "+",
    "-",
    "@",
)

MAX_CSV_CELL_LENGTH = 100_000

# ============================================================
# SQL Security
# ============================================================

MAX_SQL_STATEMENT_LENGTH = 1_000_000

SQL_DELIMITERS = {
    ";",
}


def validate(
    context: ValidationContext,
) -> None:
    """
    Perform security validation for text-based documents.

    Supported:
        - TXT
        - Markdown
        - LOG
        - CSV
        - SQL
    """

    # ========================================================
    # Common Text Validation
    # ========================================================

    _validate_common(
        context,
    )

    context.security_validated = True


def _validate_common(
    context: ValidationContext,
) -> None:
    """
    Validate common text security checks.
    """

    _validate_encoding(
        context,
    )

    _validate_binary_content(
        context,
    )

    _validate_null_bytes(
        context,
    )

    _validate_control_characters(
        context,
    )

def _validate_encoding(
    context: ValidationContext,
) -> None:
    """
    Validate UTF-8 encoding.
    """

    try:

        context.file_path.read_text(
            encoding=TEXT_ENCODING,
            errors="strict",
        )

    except UnicodeDecodeError as exc:

        raise FormatSecurityError(
            "Document is not valid UTF-8.",
            phase="common_validation",
            check="encoding",
            code="INVALID_ENCODING",
        ) from exc

def _validate_binary_content(
    context: ValidationContext,
) -> None:
    """
    Reject binary data in text documents.
    """

    try:

        data = context.file_path.read_bytes()

    except OSError as exc:

        raise FormatSecurityError(
            "Unable to read document.",
            phase="common_validation",
            check="binary_content",
            code="READ_FAILED",
        ) from exc

    sample = data[:BINARY_SAMPLE_SIZE]

    if sample.count(b"\x00") > MAX_NULL_BYTES:

        raise FormatSecurityError(
            "Binary content detected.",
            phase="common_validation",
            check="binary_content",
            code="BINARY_CONTENT_DETECTED",
        )

def _validate_null_bytes(
    context: ValidationContext,
) -> None:
    """
    Reject documents containing null bytes.
    """

    data = context.file_path.read_bytes()

    if b"\x00" in data:

        raise FormatSecurityError(
            "Null bytes detected.",
            phase="common_validation",
            check="null_bytes",
            code="NULL_BYTES_DETECTED",
        )

def _validate_control_characters(
    context: ValidationContext,
) -> None:
    """
    Reject unexpected control characters.
    """

    text = context.file_path.read_text(
        encoding=TEXT_ENCODING,
        errors="strict",
    )

    for character in text:

        # Only C0/C1 control characters. Unicode format/space characters
        # (NBSP, zero-width space, BOM) are ordinary in real documents.
        if (
            unicodedata.category(character) == "Cc"
            and character
            not in ALLOWED_CONTROL_CHARACTERS
        ):

            raise FormatSecurityError(
                "Unexpected control character detected.",
                phase="common_validation",
                check="control_characters",
                code="CONTROL_CHARACTER_DETECTED",
            )

