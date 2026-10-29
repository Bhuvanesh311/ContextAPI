class L07SufficiencyError(Exception):
    """Base exception for all L07 Sufficiency & Escalation failures."""
    pass


class SufficiencyConfigError(L07SufficiencyError):
    """Raised when the sufficiency configuration is inconsistent."""
    pass
