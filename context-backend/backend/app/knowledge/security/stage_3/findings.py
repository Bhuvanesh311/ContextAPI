from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ValidationFinding:
    """
    Represents a single Stage 3 validation finding.
    """

    phase: str

    check: str

    code: str

    message: str

    metadata: dict[str, Any] = field(default_factory=dict)