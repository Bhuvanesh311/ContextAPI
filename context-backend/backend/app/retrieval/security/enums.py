
from enum import Enum

class AuthorizationDecision(str, Enum):
    ALLOW = "ALLOW"
    ALLOW_RESTRICTED = "ALLOW_RESTRICTED"
    DENY = "DENY"
    SECURITY_BLOCKED = "SECURITY_BLOCKED"
 