class OllamaError(Exception):
    """Base exception for Ollama infra."""


class OllamaConnectionError(OllamaError):
    """Raised when the Ollama server cannot be reached."""


class OllamaTimeoutError(OllamaError):
    """Raised when a generation request exceeds its timeout."""


class OllamaGenerationError(OllamaError):
    """Raised when Ollama returns an HTTP error or malformed response."""


class OllamaModelNotFoundError(OllamaError):
    """Raised when the requested model is not available locally."""
