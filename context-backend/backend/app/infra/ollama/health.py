from app.infra.ollama.client import ollama_client
from app.infra.ollama.exceptions import OllamaConnectionError, OllamaError


def check_ollama_health() -> bool:
    """
    Verify that the Ollama server is reachable and the configured model is present.
    Raises OllamaConnectionError on failure.
    """
    try:
        available = ollama_client.is_model_available()
        if not available:
            from app.infra.ollama.config import ollama_config
            raise OllamaConnectionError(
                f"Ollama is reachable but model '{ollama_config.model}' is not loaded."
            )
        return True
    except OllamaConnectionError:
        raise
    except OllamaError as exc:
        raise OllamaConnectionError(
            f"Ollama health check failed: {exc}"
        ) from exc
