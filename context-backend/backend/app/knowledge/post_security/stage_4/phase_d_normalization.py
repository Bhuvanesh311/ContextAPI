from __future__ import annotations

import re
import unicodedata

from ..constants import (
    MAX_NORMALIZED_DOCUMENT_CHARACTERS,
)
from ..context import PostSecurityContext
from ..findings import (
    FindingSeverity,
    SecurityFinding,
)


PHASE_NAME = "stage_4.phase_d_normalization"


def execute(
    context: PostSecurityContext,
) -> PostSecurityContext:

    try:

        normalized = _normalize_document(
            context.document
        )

    except Exception as exc:

        context.invalidate()

        context.findings.add(
            SecurityFinding(
                code="PSC034",
                title="Normalization Failure",
                message=(
                    "Parsed document could not be "
                    "normalized safely."
                ),
                severity=FindingSeverity.HIGH,
                phase=PHASE_NAME,
            )
        )

        return context

    if not normalized:

        context.invalidate()

        context.findings.add(
            SecurityFinding(
                code="PSC035",
                title="Empty Normalized Document",
                message=(
                    "Document became empty after "
                    "safe normalization."
                ),
                severity=FindingSeverity.HIGH,
                phase=PHASE_NAME,
            )
        )

        return context

    if (
        len(normalized)
        > MAX_NORMALIZED_DOCUMENT_CHARACTERS
    ):

        context.invalidate()

        context.findings.add(
            SecurityFinding(
                code="PSC036",
                title="Normalized Document Too Large",
                message=(
                    "Normalized document exceeds the "
                    "maximum supported size."
                ),
                severity=FindingSeverity.HIGH,
                phase=PHASE_NAME,
            )
        )

        return context

    context.normalized_document = normalized

    return context


def _normalize_document(
    document: str,
) -> str:

    if not isinstance(
        document,
        str,
    ):
        raise TypeError(
            "Document must be a string."
        )

    # NFC preserves semantic meaning better than aggressive compatibility
    # normalization.
    document = unicodedata.normalize(
        "NFC",
        document,
    )

    # Normalize line endings.
    document = document.replace(
        "\r\n",
        "\n",
    )

    document = document.replace(
        "\r",
        "\n",
    )

    # Normalize NBSP to a normal space.
    document = document.replace(
        "\u00A0",
        " ",
    )

    # Remove zero-width formatting characters that have no textual meaning.
    document = document.replace(
        "\u200B",
        "",
    )
    document = document.replace(
        "\u200C",
        "",
    )
    document = document.replace(
        "\u200D",
        "",
    )
    document = document.replace(
        "\uFEFF",
        "",
    )

    # Trim each line without destroying line structure.
    lines = [
        line.strip()
        for line in document.split("\n")
    ]

    # Collapse horizontal whitespace only.
    lines = [
        re.sub(
            r"[ \t]+",
            " ",
            line,
        )
        for line in lines
    ]

    # Remove excessive blank lines.
    normalized_lines: list[str] = []

    blank_count = 0

    for line in lines:

        if not line:

            blank_count += 1

            if blank_count <= 2:
                normalized_lines.append("")

            continue

        blank_count = 0

        normalized_lines.append(
            line
        )

    return "\n".join(
        normalized_lines
    ).strip()