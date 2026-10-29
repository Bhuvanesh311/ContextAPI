from __future__ import annotations

import re

from ..constants import (
    MAX_DOCUMENT_SCAN_CHARACTERS,
    MAX_METADATA_VALUE_STRING_LENGTH,
)
from ..context import PostSecurityContext
from ..findings import (
    FindingSeverity,
    SecurityFinding,
)


PHASE_NAME = "stage_5.phase_c_poisoning"


_POISONING_PATTERNS: tuple[
    tuple[str, str, FindingSeverity],
    ...
] = (

    # ------------------------------------------------------------------
    # Explicit attempts to reject trusted source material
    # ------------------------------------------------------------------

    (
        "PSP001",
        r"\bignore\s+(the\s+)?source\s+material\b",
        FindingSeverity.HIGH,
    ),
    (
        "PSP002",
        r"\bignore\s+(the\s+)?verified\s+information\b",
        FindingSeverity.HIGH,
    ),
    (
        "PSP003",
        r"\breplace\s+(the\s+)?original\s+information\b",
        FindingSeverity.HIGH,
    ),
    (
        "PSP004",
        r"\bthis\s+is\s+the\s+only\s+correct\s+information\b",
        FindingSeverity.MEDIUM,
    ),
    (
        "PSP005",
        r"\bdo\s+not\s+trust\s+(the\s+)?source\b",
        FindingSeverity.HIGH,
    ),

    # ------------------------------------------------------------------
    # Attempts to establish fabricated authority
    # ------------------------------------------------------------------

    (
        "PSP006",
        r"\bthis\s+document\s+overrides\s+(all\s+)?other\s+sources\b",
        FindingSeverity.HIGH,
    ),
    (
        "PSP007",
        r"\bthis\s+source\s+is\s+more\s+authoritative\b",
        FindingSeverity.MEDIUM,
    ),
    (
        "PSP008",
        r"\bconsider\s+this\s+source\s+authoritative\b",
        FindingSeverity.MEDIUM,
    ),
    (
        "PSP009",
        r"\bthe\s+information\s+below\s+must\s+be\s+treated\s+as\s+fact\b",
        FindingSeverity.MEDIUM,
    ),

    # ------------------------------------------------------------------
    # Attempts to alter downstream knowledge
    # ------------------------------------------------------------------

    (
        "PSP010",
        r"\bupdate\s+your\s+knowledge\s+base\b",
        FindingSeverity.HIGH,
    ),
    (
        "PSP011",
        r"\bmodify\s+the\s+knowledge\s+base\b",
        FindingSeverity.HIGH,
    ),
    (
        "PSP012",
        r"\badd\s+this\s+as\s+(a\s+)?trusted\s+knowledge\b",
        FindingSeverity.HIGH,
    ),
    (
        "PSP013",
        r"\bstore\s+this\s+as\s+verified\s+information\b",
        FindingSeverity.HIGH,
    ),
    (
        "PSP014",
        r"\bmark\s+this\s+(document|source)\s+as\s+trusted\b",
        FindingSeverity.HIGH,
    ),

    # ------------------------------------------------------------------
    # Retrieval manipulation
    # ------------------------------------------------------------------

    (
        "PSP015",
        r"\bmake\s+this\s+(document|source)\s+appear\s+first\b",
        FindingSeverity.HIGH,
    ),
    (
        "PSP016",
        r"\balways\s+prefer\s+this\s+(document|source)\b",
        FindingSeverity.HIGH,
    ),
    (
        "PSP017",
        r"\balways\s+cite\s+this\s+(document|source)\b",
        FindingSeverity.HIGH,
    ),
    (
        "PSP018",
        r"\bnever\s+cite\s+(the\s+)?other\s+sources\b",
        FindingSeverity.HIGH,
    ),

    # ------------------------------------------------------------------
    # False-authority / verification manipulation
    # ------------------------------------------------------------------

    (
        "PSP019",
        r"\balready\s+verified\s+by\s+(the\s+)?system\b",
        FindingSeverity.MEDIUM,
    ),
    (
        "PSP020",
        r"\bsecurity\s+has\s+already\s+approved\s+this\b",
        FindingSeverity.HIGH,
    ),
    (
        "PSP021",
        r"\bthe\s+system\s+has\s+confirmed\s+this\s+information\b",
        FindingSeverity.MEDIUM,
    ),
)


def execute(
    context: PostSecurityContext,
) -> PostSecurityContext:

    document = context.normalized_document

    if document:

        document = document[
            :MAX_DOCUMENT_SCAN_CHARACTERS
        ]

        _detect_poisoning_indicators(
            context,
            document,
        )

    _scan_metadata(
        context
    )

    return context


def _detect_poisoning_indicators(
    context: PostSecurityContext,
    document: str,
) -> None:

    for code, pattern, severity in _POISONING_PATTERNS:

        if not re.search(
            pattern,
            document,
            flags=re.IGNORECASE | re.MULTILINE,
        ):
            continue

        context.findings.add(
            SecurityFinding(
                code=code,
                title="Knowledge Poisoning Indicator",
                message=(
                    "A knowledge-poisoning or source-authority "
                    "manipulation pattern was detected."
                ),
                severity=severity,
                phase=PHASE_NAME,
            )
        )


def _scan_metadata(
    context: PostSecurityContext,
) -> None:

    metadata = context.metadata

    if not isinstance(
        metadata,
        dict,
    ):
        return

    for key, value in metadata.items():

        if not isinstance(
            value,
            str,
        ):
            continue

        value = value[
            :MAX_METADATA_VALUE_STRING_LENGTH
        ]

        for code, pattern, severity in _POISONING_PATTERNS:

            if not re.search(
                pattern,
                value,
                flags=re.IGNORECASE | re.MULTILINE,
            ):
                continue

            context.findings.add(
                SecurityFinding(
                    code=f"{code}M",
                    title="Metadata Poisoning Indicator",
                    message=(
                        "A knowledge-poisoning indicator was "
                        "detected inside parsed metadata."
                    ),
                    severity=severity,
                    phase=PHASE_NAME,
                    metadata={
                        "metadata_key": key,
                    },
                )
            )