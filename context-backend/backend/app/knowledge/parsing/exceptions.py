class ParsingError(Exception):
    """Base exception for the parsing subsystem."""


class SandboxError(ParsingError):
    """Base exception for sandbox-related failures."""


class SandboxInitializationError(SandboxError):
    """Raised when the sandbox cannot be initialized."""


class SandboxExecutionError(SandboxError):
    """Raised when execution inside the sandbox fails."""


class SandboxUnavailableError(SandboxError):
    """Raised when no sandbox worker is available."""


class ParserException(ParsingError):
    """
    Base exception for all parser-related errors.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class UnsupportedFileTypeError(ParserException):
    """
    Raised when the file format is not supported.
    """


class ParserNotFoundError(ParserException):
    """
    Raised when no parser is registered for the format.
    """


class FileParsingError(ParserException):
    """
    Raised when file content extraction fails.
    """


class SourceFileNotFoundError(ParserException):
    """
    Raised when the source file is not found.
    """


class ParserConfigurationError(ParserException):
    """
    Raised when parser configuration is invalid.
    """


class OutputValidationError(ParserException):
    """
    Raised when parsed output validation fails.
    """