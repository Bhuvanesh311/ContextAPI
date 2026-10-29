

from __future__ import annotations

from enum import Enum

class SecurityDecision(str, Enum):

    ALLOW = "allow"
    REVIEW = "review"
    BLOCK = "block"


class VerificationStatus(str, Enum):

    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"


class CandidateStatus(str, Enum):

    CREATED = "created"
    FILTERED = "filtered"
    SELECTED = "selected"


class PipelineStage(str, Enum):

    STAGE_5 = "stage_5"
    STAGE_6 = "stage_6"
    

class RiskLevel(str, Enum):

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
