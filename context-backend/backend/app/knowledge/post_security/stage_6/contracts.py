from __future__ import annotations

from dataclasses import dataclass

from ..enums import VerificationStatus
from .phase_a_candidates import Candidate


@dataclass(slots=True, frozen=True)
class VerificationResult:

    candidate: Candidate
    status: VerificationStatus
    confidence: float
    reason: str