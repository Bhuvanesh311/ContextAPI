"""
Tier B provider — delegates to app.infra.ollama.OllamaClient.

Converts OllamaError subclasses into RuntimeError so the router's
generic exception handling stays unchanged.
"""

from typing import Any, Callable, Dict, Optional

from app.retrieval.intelligence.providers.base import AbstractModelProvider
from app.infra.ollama.client import OllamaClient
from app.infra.ollama.exceptions import OllamaError


class OllamaProvider(AbstractModelProvider):
    def __init__(self, base_url: str, model: str, timeout: int = 60) -> None:
        self._client = OllamaClient(base_url=base_url, model=model, timeout=timeout)

    def generate_structured(
        self,
        prompt: str,
        schema: Dict[str, Any],
        timeout: int = 60,
        system: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            return self._client.generate_structured(prompt, schema, timeout=timeout, system=system)
        except OllamaError as exc:
            raise RuntimeError(str(exc)) from exc

    def generate_text(
        self,
        prompt: str,
        timeout: int = 60,
        system: Optional[str] = None,
        on_text: Optional[Callable[[str, Optional[str]], None]] = None,
    ) -> str:
        try:
            return self._client.generate(prompt, timeout=timeout, system=system, on_text=on_text)
        except OllamaError as exc:
            raise RuntimeError(str(exc)) from exc
