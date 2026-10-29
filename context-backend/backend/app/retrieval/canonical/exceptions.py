from typing import Optional


class CanonicalizationError(Exception):
    """
    Raised when L01 cannot establish a valid canonical contract.
    This corresponds to validation and canonicalization failures
    in the L01 Failure Model.
    """
    def __init__(self, message: str, field: Optional[str] = None, error_code: str = "CONTRACT_VIOLATION"):
        super().__init__(message)
        self.field = field
        self.error_code = error_code