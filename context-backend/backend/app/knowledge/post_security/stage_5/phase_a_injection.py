from __future__ import annotations

import re

from ..constants import (
    MAX_DOCUMENT_SCAN_CHARACTERS,
)
from ..context import PostSecurityContext
from ..findings import (
    FindingSeverity,
    SecurityFinding,
)


PHASE_NAME = "stage_5.phase_a_injection"


# ---------------------------------------------------------------------------
# Direct prompt-injection indicators
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS: tuple[tuple[str, str, FindingSeverity], ...] = (
    (
        "PSI001",
        r"\bignore\s+(all\s+)?previous\s+instructions\b",
        FindingSeverity.HIGH,
    ),
    (
        "PSI002",
        r"\bignore\s+(all\s+)?prior\s+instructions\b",
        FindingSeverity.HIGH,
    ),
    (
        "PSI003",
        r"\bdisregard\s+(all\s+)?previous\s+instructions\b",
        FindingSeverity.HIGH,
    ),
    (
        "PSI004",
        r"\bdisregard\s+(all\s+)?prior\s+instructions\b",
        FindingSeverity.HIGH,
    ),
    (
        "PSI005",
        r"\boverride\s+(the\s+)?system\s+instructions\b",
        FindingSeverity.HIGH,
    ),
    (
        "PSI006",
        r"\bforget\s+(all\s+)?previous\s+instructions\b",
        FindingSeverity.HIGH,
    ),
    (
        "PSI007",
        r"\breveal\s+(the\s+)?system\s+prompt\b",
        FindingSeverity.HIGH,
    ),
    (
        "PSI008",
        r"\breveal\s+(the\s+)?hidden\s+instructions\b",
        FindingSeverity.HIGH,
    ),
    (
        "PSI009",
        r"\bshow\s+(me\s+)?the\s+system\s+prompt\b",
        FindingSeverity.HIGH,
    ),
    (
        "PSI010",
        r"\bdeveloper\s+mode\b",
        FindingSeverity.MEDIUM,
    ),
    (
        "PSI011",
        r"\bact\s+as\s+(a\s+)?system\b",
        FindingSeverity.MEDIUM,
    ),
    (
        "PSI012",
        r"\byou\s+are\s+now\s+(an?\s+)?(ai|assistant|system)\b",
        FindingSeverity.MEDIUM,
    ),
    (
        "PSI013",
        r"\bdo\s+not\s+follow\s+(the\s+)?user\b",
        FindingSeverity.HIGH,
    ),
    (
        "PSI014",
        r"\bfollow\s+these\s+instructions\s+instead\b",
        FindingSeverity.HIGH,
    ),
    (
        "PSI015",
        r"\bnew\s+system\s+message\b",
        FindingSeverity.HIGH,
    ),
    (
        "PSI016",
        r"\bsystem\s+message\s*:",
        FindingSeverity.MEDIUM,
    ),
    (
        "PSI017",
        r"\bdeveloper\s+message\s*:",
        FindingSeverity.MEDIUM,
    ),
    (
        "PSI018",
        r"\bdo\s+not\s+mention\s+this\s+instruction\b",
        FindingSeverity.HIGH,
    ),
    (
        "PSI019",
        r"\bdo\s+not\s+tell\s+the\s+user\b",
        FindingSeverity.MEDIUM,
    ),
    (
        "PSI020",
        r"\bhidden\s+prompt\b",
        FindingSeverity.MEDIUM,
    ),
)


# ---------------------------------------------------------------------------
# Attempts to manipulate downstream RAG / retrieval behavior
# ---------------------------------------------------------------------------

_RETRIEVAL_MANIPULATION_PATTERNS: tuple[
    tuple[str, str, FindingSeverity],
    ...
] = (
    (
        "PSI021",
        r"\brank\s+this\s+(document|source)\s+(first|highest)\b",
        FindingSeverity.HIGH,
    ),
    (
        "PSI022",
        r"\balways\s+return\s+this\s+(document|source)\b",
        FindingSeverity.HIGH,
    ),
    (
        "PSI023",
        r"\bprioritize\s+this\s+(document|source)\b",
        FindingSeverity.HIGH,
    ),
    (
        "PSI024",
        r"\bignore\s+other\s+(documents|sources)\b",
        FindingSeverity.HIGH,
    ),
    (
        "PSI025",
        r"\bdo\s+not\s+retrieve\s+other\s+(documents|sources)\b",
        FindingSeverity.HIGH,
    ),
)


def execute(
    context: PostSecurityContext,
) -> PostSecurityContext:

    document = context.normalized_document

    if not document:
        return context

    # Never scan more than the Stage 4 resource boundary.
    document = document[
        :MAX_DOCUMENT_SCAN_CHARACTERS
    ]

    _detect_patterns(
        context,
        document,
        _INJECTION_PATTERNS,
    )

    _detect_patterns(
        context,
        document,
        _RETRIEVAL_MANIPULATION_PATTERNS,
    )

    return context


def _detect_patterns(
    context: PostSecurityContext,
    document: str,
    patterns: tuple[
        tuple[str, str, FindingSeverity],
        ...
    ],
) -> None:

    for code, pattern, severity in patterns:

        match = re.search(
            pattern,
            document,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        if not match:
            continue

        # Quote the matched words so the uploader can see what was flagged.
        matched = " ".join(match.group(0).split())[:80]
        context.findings.add(
            SecurityFinding(
                code=code,
                title="Prompt Injection Indicator",
                message=(
                    "A prompt-injection or downstream "
                    "instruction-manipulation pattern was "
                    f"detected in the normalized document: \"{matched}\"."
                ),
                severity=severity,
                phase=PHASE_NAME,
                metadata={"matched_text": matched},
            )
        )