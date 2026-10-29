from enum import Enum

class EvidenceState(str, Enum):
    ACCEPTED = "ACCEPTED"
    UNCERTAIN = "UNCERTAIN"
    REJECTED = "REJECTED"
    DUPLICATE = "DUPLICATE"
    CONFLICTING = "CONFLICTING"
    INVALID = "INVALID"
