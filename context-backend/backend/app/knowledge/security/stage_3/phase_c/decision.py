from __future__ import annotations

from app.knowledge.security.stage_3.context import ValidationContext
from app.knowledge.security.stage_3.exceptions import (
    ParserAdmissionError,
)


def approve_for_parsing(
    context: ValidationContext,
) -> None:
    """
    Final Stage 3 admission decision.

    The document is admitted only if
    format identification and
    format-specific validation
    completed successfully.
    """

    if not context.format_identified:
        raise ParserAdmissionError(
            "Document format was not identified.",
            phase="parser_admission",
            check="format_identification",
            code="FORMAT_NOT_IDENTIFIED",
        )

    if not context.validator_selected:
        raise ParserAdmissionError(
            "No validator was selected.",
            phase="parser_admission",
            check="validator_selection",
            code="VALIDATOR_NOT_SELECTED",
        )

    if not context.security_validated:
        raise ParserAdmissionError(
            "Document failed format security validation.",
            phase="parser_admission",
            check="format_validation",
            code="FORMAT_SECURITY_FAILED",
        )

    context.ready_for_sandbox = True