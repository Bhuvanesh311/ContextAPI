from __future__ import annotations

import unicodedata

from ..constants import (
    FORBIDDEN_CONTROL_CODEPOINTS,
    MAX_DOCUMENT_CHARACTERS,
    MAX_METADATA_KEYS,
    MAX_METADATA_VALUE_STRING_LENGTH,
    MAX_REFERENCE_LENGTH,
    MAX_REFERENCES,
)
from ..context import PostSecurityContext
from ..findings import (
    FindingSeverity,
    SecurityFinding,
)


PHASE_NAME = "stage_4.phase_c_structure"


def execute(
    context: PostSecurityContext,
) -> PostSecurityContext:

    _validate_document_structure(context)
    _validate_unicode(context)
    _validate_metadata_structure(context)
    _validate_reference_structure(context)

    return context


def _validate_document_structure(
    context: PostSecurityContext,
) -> None:

    document = context.document

    if not isinstance(
        document,
        str,
    ):
        context.invalidate()
        return

    if len(document) > MAX_DOCUMENT_CHARACTERS:

        context.invalidate()

        context.findings.add(
            SecurityFinding(
                code="PSC024",
                title="Document Resource Limit Exceeded",
                message=(
                    "Document content exceeds the "
                    "maximum supported size."
                ),
                severity=FindingSeverity.HIGH,
                phase=PHASE_NAME,
            )
        )

    if "\x00" in document:

        context.invalidate()

        context.findings.add(
            SecurityFinding(
                code="PSC025",
                title="Null Character Detected",
                message=(
                    "Document contains a forbidden "
                    "NUL control character."
                ),
                severity=FindingSeverity.HIGH,
                phase=PHASE_NAME,
            )
        )


def _validate_unicode(
    context: PostSecurityContext,
) -> None:

    document = context.document

    if not isinstance(
        document,
        str,
    ):
        return

    for index, character in enumerate(
        document
    ):

        codepoint = ord(character)

        if codepoint in FORBIDDEN_CONTROL_CODEPOINTS:

            context.invalidate()

            context.findings.add(
                SecurityFinding(
                    code="PSC026",
                    title="Forbidden Control Character",
                    message=(
                        "Document contains a forbidden "
                        "control character."
                    ),
                    severity=FindingSeverity.HIGH,
                    phase=PHASE_NAME,
                    metadata={
                        "codepoint": (
                            f"U+{codepoint:04X}"
                        ),
                        "character_index": str(index),
                    },
                )
            )

            # One finding is enough for this phase.
            break

        # Unicode category inspection.
        category = unicodedata.category(
            character
        )

        # Cc = control characters.
        if category == "Cc" and codepoint not in {
            0x0009,  # TAB
            0x000A,  # LF
            0x000D,  # CR
        }:

            context.invalidate()

            context.findings.add(
                SecurityFinding(
                    code="PSC027",
                    title="Unsupported Unicode Control",
                    message=(
                        "Document contains an unsupported "
                        "Unicode control character."
                    ),
                    severity=FindingSeverity.HIGH,
                    phase=PHASE_NAME,
                    metadata={
                        "codepoint": (
                            f"U+{codepoint:04X}"
                        ),
                        "character_index": str(index),
                    },
                )
            )

            break


def _validate_metadata_structure(
    context: PostSecurityContext,
) -> None:

    metadata = context.metadata

    if not isinstance(
        metadata,
        dict,
    ):
        return

    if len(metadata) > MAX_METADATA_KEYS:

        context.invalidate()

        context.findings.add(
            SecurityFinding(
                code="PSC028",
                title="Metadata Key Limit Exceeded",
                message=(
                    "Parsed metadata contains more keys "
                    "than the supported limit."
                ),
                severity=FindingSeverity.HIGH,
                phase=PHASE_NAME,
            )
        )
        return

    for key, value in metadata.items():

        if not isinstance(
            key,
            str,
        ):

            context.invalidate()

            context.findings.add(
                SecurityFinding(
                    code="PSC029",
                    title="Invalid Metadata Key",
                    message=(
                        "Parsed metadata keys must be strings."
                    ),
                    severity=FindingSeverity.HIGH,
                    phase=PHASE_NAME,
                )
            )

            break

        if (
            isinstance(value, str)
            and len(value)
            > MAX_METADATA_VALUE_STRING_LENGTH
        ):

            context.invalidate()

            context.findings.add(
                SecurityFinding(
                    code="PSC030",
                    title="Metadata Value Too Large",
                    message=(
                        "A metadata string exceeds the "
                        "supported resource limit."
                    ),
                    severity=FindingSeverity.HIGH,
                    phase=PHASE_NAME,
                    metadata={
                        "key": key,
                    },
                )
            )

            break


def _validate_reference_structure(
    context: PostSecurityContext,
) -> None:

    references = context.references

    if not isinstance(
        references,
        list,
    ):
        return

    if len(references) > MAX_REFERENCES:

        context.invalidate()

        context.findings.add(
            SecurityFinding(
                code="PSC031",
                title="Reference Count Limit Exceeded",
                message=(
                    "Parsed artifact contains too many references."
                ),
                severity=FindingSeverity.HIGH,
                phase=PHASE_NAME,
            )
        )
        return

    seen: set[str] = set()

    for index, reference in enumerate(
        references
    ):

        if not isinstance(
            reference,
            str,
        ):
            continue

        if len(reference) > MAX_REFERENCE_LENGTH:

            context.invalidate()

            context.findings.add(
                SecurityFinding(
                    code="PSC032",
                    title="Reference Length Limit Exceeded",
                    message=(
                        "A parsed reference exceeds "
                        "the supported resource limit."
                    ),
                    severity=FindingSeverity.HIGH,
                    phase=PHASE_NAME,
                    metadata={
                        "reference_index": str(index),
                    },
                )
            )

            break

        normalized_reference = (
            reference.strip()
        )

        if normalized_reference in seen:

            context.invalidate()

            context.findings.add(
                SecurityFinding(
                    code="PSC033",
                    title="Duplicate Reference",
                    message=(
                        "Duplicate parsed references "
                        "were detected."
                    ),
                    severity=FindingSeverity.MEDIUM,
                    phase=PHASE_NAME,
                    metadata={
                        "reference_index": str(index),
                    },
                )
            )

            break

        seen.add(
            normalized_reference
        )