from __future__ import annotations

import re
from urllib.parse import urlparse

from ..constants import (
    MAX_REFERENCE_LENGTH,
    MAX_REFERENCES,
)
from ..context import PostSecurityContext
from ..findings import (
    FindingSeverity,
    SecurityFinding,
)


PHASE_NAME = "stage_5.phase_b_references"


# Explicitly dangerous schemes for a knowledge reference.
_DANGEROUS_SCHEMES = {
    "javascript",
    "vbscript",
    "data",
    "file",
}


# Characters that should never occur in a reference.
_FORBIDDEN_REFERENCE_CONTROLS = {
    "\x00",
    "\x01",
    "\x02",
    "\x03",
    "\x04",
    "\x05",
    "\x06",
    "\x07",
    "\x08",
    "\x0b",
    "\x0c",
    "\x0e",
    "\x0f",
    "\x10",
    "\x11",
    "\x12",
    "\x13",
    "\x14",
    "\x15",
    "\x16",
    "\x17",
    "\x18",
    "\x19",
    "\x1a",
    "\x1b",
    "\x1c",
    "\x1d",
    "\x1e",
    "\x1f",
    "\x7f",
}


def execute(
    context: PostSecurityContext,
) -> PostSecurityContext:

    _validate_references(context)

    return context


def _validate_references(
    context: PostSecurityContext,
) -> None:

    references = context.references

    if not isinstance(
        references,
        list,
    ):
        context.invalidate()

        context.findings.add(
            SecurityFinding(
                code="PSR001",
                title="Invalid Source References",
                message=(
                    "Parsed source references must be a list."
                ),
                severity=FindingSeverity.HIGH,
                phase=PHASE_NAME,
            )
        )

        return

    if len(references) > MAX_REFERENCES:

        context.invalidate()

        context.findings.add(
            SecurityFinding(
                code="PSR002",
                title="Reference Count Limit Exceeded",
                message=(
                    "The number of source references exceeds "
                    "the supported security boundary."
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

        _validate_reference(
            context,
            reference,
            index,
            seen,
        )


def _validate_reference(
    context: PostSecurityContext,
    reference: object,
    index: int,
    seen: set[str],
) -> None:

    if not isinstance(
        reference,
        str,
    ):

        context.invalidate()

        context.findings.add(
            SecurityFinding(
                code="PSR003",
                title="Invalid Source Reference",
                message=(
                    "Every source reference must be a string."
                ),
                severity=FindingSeverity.HIGH,
                phase=PHASE_NAME,
                metadata={
                    "reference_index": str(index),
                },
            )
        )

        return

    value = reference.strip()

    if not value:

        context.invalidate()

        context.findings.add(
            SecurityFinding(
                code="PSR004",
                title="Empty Source Reference",
                message=(
                    "A source reference contains no usable content."
                ),
                severity=FindingSeverity.MEDIUM,
                phase=PHASE_NAME,
                metadata={
                    "reference_index": str(index),
                },
            )
        )

        return

    if len(value) > MAX_REFERENCE_LENGTH:

        context.invalidate()

        context.findings.add(
            SecurityFinding(
                code="PSR005",
                title="Source Reference Too Large",
                message=(
                    "A source reference exceeds the supported "
                    "maximum length."
                ),
                severity=FindingSeverity.HIGH,
                phase=PHASE_NAME,
                metadata={
                    "reference_index": str(index),
                },
            )
        )

        return

    if any(
        character in value
        for character in _FORBIDDEN_REFERENCE_CONTROLS
    ):

        context.invalidate()

        context.findings.add(
            SecurityFinding(
                code="PSR006",
                title="Invalid Reference Control Character",
                message=(
                    "A source reference contains forbidden "
                    "control characters."
                ),
                severity=FindingSeverity.HIGH,
                phase=PHASE_NAME,
                metadata={
                    "reference_index": str(index),
                },
            )
        )

        return

    normalized = value.casefold()

    if normalized in seen:

        context.findings.add(
            SecurityFinding(
                code="PSR007",
                title="Duplicate Source Reference",
                message=(
                    "The same source reference occurs more than once."
                ),
                severity=FindingSeverity.MEDIUM,
                phase=PHASE_NAME,
                metadata={
                    "reference_index": str(index),
                },
            )
        )

    else:
        seen.add(normalized)

    _validate_reference_scheme(
        context,
        value,
        index,
    )

    _validate_reference_structure(
        context,
        value,
        index,
    )


def _validate_reference_scheme(
    context: PostSecurityContext,
    reference: str,
    index: int,
) -> None:

    # Only interpret the string as a URL if it has a URL-like scheme.
    parsed = urlparse(reference)

    if not parsed.scheme:
        return

    scheme = parsed.scheme.casefold()

    if scheme in _DANGEROUS_SCHEMES:

        context.findings.add(
            SecurityFinding(
                code="PSR008",
                title="Dangerous Reference Scheme",
                message=(
                    "A source reference uses a scheme that "
                    "must not be trusted as a knowledge source."
                ),
                severity=FindingSeverity.HIGH,
                phase=PHASE_NAME,
                metadata={
                    "reference_index": str(index),
                    "scheme": scheme,
                },
            )
        )

        return

    # A normal network reference should have a network location.
    if scheme in {"http", "https"} and not parsed.netloc:

        context.findings.add(
            SecurityFinding(
                code="PSR009",
                title="Malformed Network Reference",
                message=(
                    "A network source reference does not "
                    "contain a valid network location."
                ),
                severity=FindingSeverity.MEDIUM,
                phase=PHASE_NAME,
                metadata={
                    "reference_index": str(index),
                },
            )
        )


def _validate_reference_structure(
    context: PostSecurityContext,
    reference: str,
    index: int,
) -> None:

    # Detect obvious credential-bearing HTTP(S) references.
    parsed = urlparse(reference)

    if parsed.scheme.casefold() in {
        "http",
        "https",
    } and parsed.username is not None:

        context.findings.add(
            SecurityFinding(
                code="PSR010",
                title="Credential-Bearing Source Reference",
                message=(
                    "A source reference contains embedded "
                    "user information and should not be trusted "
                    "as a normal knowledge reference."
                ),
                severity=FindingSeverity.HIGH,
                phase=PHASE_NAME,
                metadata={
                    "reference_index": str(index),
                },
            )
        )

    # Detect obvious shell / command-like reference payloads.
    if re.search(
        r"(?:^|[\s:=])(?:cmd|powershell|bash|sh|exec)\s",
        reference,
        flags=re.IGNORECASE,
    ):

        context.findings.add(
            SecurityFinding(
                code="PSR011",
                title="Command-Like Source Reference",
                message=(
                    "A source reference contains command-like "
                    "content and requires security review."
                ),
                severity=FindingSeverity.MEDIUM,
                phase=PHASE_NAME,
                metadata={
                    "reference_index": str(index),
                },
            )
        )