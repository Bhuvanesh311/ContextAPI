from __future__ import annotations

from app.knowledge.security.stage_3.constants import (
    MAX_SOURCE_LINE_LENGTH,
    MAX_SOURCE_TOKEN_LENGTH,
)
from app.knowledge.security.stage_3.context import ValidationContext
from app.knowledge.security.stage_3.exceptions import (
    FormatSecurityError,
)


def validate(
    context: ValidationContext,
) -> None:
    """
    Validate source-code files before sandbox parsing.

    Supported:

        - Python
        - JavaScript
        - TypeScript
        - Java
        - Go
        - C#
        - PHP
        - C
        - C++
        - Rust
    """

    _validate_utf8(context)
    _validate_null_bytes(context)
    _validate_line_length(context)
    _validate_token_length(context)

    context.security_validated = True


def _validate_utf8(
    context: ValidationContext,
) -> None:

    try:
        context.file_path.read_text(
            encoding="utf-8",
            errors="strict",
        )

    except UnicodeDecodeError as exc:
        raise FormatSecurityError(
            "Source file is not valid UTF-8.",
            phase="format_validation",
            check="encoding",
            code="INVALID_ENCODING",
        ) from exc


def _validate_null_bytes(
    context: ValidationContext,
) -> None:

    try:
        data = context.file_path.read_bytes()

    except OSError as exc:
        raise FormatSecurityError(
            "Unable to read source file.",
            phase="format_validation",
            check="null_bytes",
            code="READ_FAILED",
        ) from exc

    if b"\x00" in data:
        raise FormatSecurityError(
            "Null bytes detected.",
            phase="format_validation",
            check="null_bytes",
            code="NULL_BYTES_DETECTED",
        )


def _validate_line_length(
    context: ValidationContext,
) -> None:

    try:
        with context.file_path.open(
            "r",
            encoding="utf-8",
            errors="strict",
        ) as file:

            for number, line in enumerate(file, start=1):

                if len(line) > MAX_SOURCE_LINE_LENGTH:

                    raise FormatSecurityError(
                        f"Line {number} exceeds the maximum allowed length.",
                        phase="format_validation",
                        check="line_length",
                        code="LINE_TOO_LONG",
                    )

    except OSError as exc:
        raise FormatSecurityError(
            "Unable to read source file.",
            phase="format_validation",
            check="line_length",
            code="READ_FAILED",
        ) from exc


def _validate_token_length(
    context: ValidationContext,
) -> None:

    try:
        with context.file_path.open(
            "r",
            encoding="utf-8",
            errors="strict",
        ) as file:

            for number, line in enumerate(file, start=1):

                for token in line.split():

                    if len(token) > MAX_SOURCE_TOKEN_LENGTH:

                        raise FormatSecurityError(
                            f"Line {number} contains an excessively long token.",
                            phase="format_validation",
                            check="token_length",
                            code="TOKEN_TOO_LONG",
                        )

    except OSError as exc:
        raise FormatSecurityError(
            "Unable to read source file.",
            phase="format_validation",
            check="token_length",
            code="READ_FAILED",
        ) from exc