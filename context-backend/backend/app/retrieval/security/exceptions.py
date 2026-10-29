
class SecurityResolutionError(Exception):
    """
    Raised when L02 encounters a condition that prevents safe authorization evaluation.
    This corresponds to SECURITY_BLOCKED.
    """
    def __init__(self, message: str, error_code: str = "SECURITY_BLOCKED"):
        super().__init__(message)
        self.error_code = error_code