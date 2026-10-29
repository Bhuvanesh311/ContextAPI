from __future__ import annotations

from ..constants import MAX_DOCUMENT_CHARACTERS
from ..context import PostSecurityContext
from ..findings import (
    FindingSeverity,
    SecurityFinding,
)


PHASE_NAME = "stage_4.phase_b_completeness"

MIN_DOCUMENT_CHARACTERS = 1
MIN_DOCUMENT_WORDS = 1


def execute(
    context: PostSecurityContext,
) -> PostSecurityContext:

    _check_document_content(context)
    _check_statistics(context)
    _check_parser_metadata(context)

    return context


def _check_document_content(
    context: PostSecurityContext,
) -> None:

    document = context.document

    if not isinstance(
        document,
        str,
    ):
        return

    stripped = document.strip()

    if len(stripped) < MIN_DOCUMENT_CHARACTERS:

        context.invalidate()

        context.findings.add(
            SecurityFinding(
                code="PSC016",
                title="Insufficient Parsed Content",
                message=(
                    "Parsed artifact contains no usable "
                    "document content."
                ),
                severity=FindingSeverity.HIGH,
                phase=PHASE_NAME,
            )
        )
        return

    if len(document) > MAX_DOCUMENT_CHARACTERS:

        context.invalidate()

        context.findings.add(
            SecurityFinding(
                code="PSC017",
                title="Document Size Limit Exceeded",
                message=(
                    "Parsed document content exceeds the "
                    "maximum supported Stage 4 size."
                ),
                severity=FindingSeverity.HIGH,
                phase=PHASE_NAME,
            )
        )
        return

    words = stripped.split()

    if len(words) < MIN_DOCUMENT_WORDS:

        context.invalidate()

        context.findings.add(
            SecurityFinding(
                code="PSC018",
                title="Insufficient Parsed Content",
                message=(
                    "Parsed artifact contains insufficient "
                    "usable document content."
                ),
                severity=FindingSeverity.HIGH,
                phase=PHASE_NAME,
            )
        )


def _check_statistics(
    context: PostSecurityContext,
) -> None:

    character_count = context.get_attribute(
        "character_count"
    )

    word_count = context.get_attribute(
        "word_count"
    )

    if character_count is not None:

        if not isinstance(
            character_count,
            int,
        ) or character_count < 0:

            context.invalidate()

            context.findings.add(
                SecurityFinding(
                    code="PSC019",
                    title="Invalid Character Statistics",
                    message=(
                        "Parsed character_count must be "
                        "a non-negative integer."
                    ),
                    severity=FindingSeverity.HIGH,
                    phase=PHASE_NAME,
                )
            )

        elif character_count != len(
            context.document
        ):

            context.invalidate()

            context.findings.add(
                SecurityFinding(
                    code="PSC020",
                    title="Character Count Mismatch",
                    message=(
                        "Parsed character_count does not "
                        "match the parsed document content."
                    ),
                    severity=FindingSeverity.HIGH,
                    phase=PHASE_NAME,
                )
            )

    if word_count is not None:

        if not isinstance(
            word_count,
            int,
        ) or word_count < 0:

            context.invalidate()

            context.findings.add(
                SecurityFinding(
                    code="PSC021",
                    title="Invalid Word Statistics",
                    message=(
                        "Parsed word_count must be "
                        "a non-negative integer."
                    ),
                    severity=FindingSeverity.HIGH,
                    phase=PHASE_NAME,
                )
            )

        elif word_count != len(
            context.document.strip().split()
        ):

            context.invalidate()

            context.findings.add(
                SecurityFinding(
                    code="PSC022",
                    title="Word Count Mismatch",
                    message=(
                        "Parsed word_count does not match "
                        "the parsed document content."
                    ),
                    severity=FindingSeverity.HIGH,
                    phase=PHASE_NAME,
                )
            )


def _check_parser_metadata(
    context: PostSecurityContext,
) -> None:

    parser_name = context.get_attribute(
        "parser_name"
    )

    if parser_name is not None:

        if not isinstance(
            parser_name,
            str,
        ) or not parser_name.strip():

            context.invalidate()

            context.findings.add(
                SecurityFinding(
                    code="PSC023",
                    title="Invalid Parser Identity",
                    message=(
                        "Parser identity must be a "
                        "non-empty string."
                    ),
                    severity=FindingSeverity.HIGH,
                    phase=PHASE_NAME,
                )
            )