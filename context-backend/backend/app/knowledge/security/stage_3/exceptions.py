from __future__ import annotations


class StageThreeValidationError(Exception):
    """
    Base exception for all Stage 3 validation failures.
    """

    def __init__(
        self,
        message: str,
        *,
        phase: str,
        check: str,
        code: str,
    ) -> None:
        super().__init__(message)

        self.phase = phase
        self.check = check
        self.code = code


class FormatIdentificationError(StageThreeValidationError):
    """
    Raised when format identification fails.
    """


class FormatSecurityError(StageThreeValidationError):
    """
    Raised when a format-specific security validation fails.
    """


class ParserAdmissionError(StageThreeValidationError):
    """
    Raised when the document cannot safely proceed to sandbox parsing.
    """