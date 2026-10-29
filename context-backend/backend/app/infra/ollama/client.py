"""
Ollama HTTP client — offline LLM generation (Tier B).

Wraps the Ollama /api/generate endpoint with typed exceptions,
structured-output support (JSON schema via `format`), and a
health-check helper.
"""

import json
import logging
import re
import time
from typing import Any, Callable, Dict, Optional
from urllib import error, request as urllib_request

from app.infra.ollama.config import ollama_config
from app.infra.ollama.constants import GENERATE_PATH, TAGS_PATH
from app.infra.ollama.exceptions import (
    OllamaConnectionError,
    OllamaGenerationError,
    OllamaModelNotFoundError,
    OllamaTimeoutError,
)

logger = logging.getLogger(__name__)


class OllamaClient:
    """
    Thin HTTP client for a locally running Ollama server.

    All methods raise subclasses of OllamaError on failure — never
    return None for mandatory fields.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> None:
        self._base_url = (base_url or ollama_config.base_url).rstrip("/")
        self._model    = model   or ollama_config.model
        self._timeout  = timeout or ollama_config.timeout_seconds

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        timeout: Optional[int] = None,
        system: Optional[str] = None,
        on_text: Optional[Callable[[str, Optional[str]], None]] = None,
    ) -> str:
        """
        Send a plain-text prompt; return the generated text string.

        With `on_text`, the answer is streamed: the callback gets the text so
        far after every chunk, and once more at the end with Ollama's
        done_reason ("stop", or "length" when num_predict cut the answer).
        """
        if on_text is not None:
            return self._stream_generate(prompt, timeout or self._timeout, system, on_text)
        raw = self._post_generate(prompt, schema=None, timeout=timeout, system=system)
        response = raw.get("response", "")
        if not isinstance(response, str):
            raise OllamaGenerationError("Ollama response field is not a string.")
        return response

    def generate_structured(
        self,
        prompt: str,
        schema: Dict[str, Any],
        timeout: Optional[int] = None,
        system: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a prompt with a JSON schema constraint; return parsed dict.

        Ollama places the generated text in `response`; when `format` is
        a JSON schema the text itself is valid JSON — this method parses
        and returns it.
        """
        budget = timeout or self._timeout
        started = time.monotonic()
        try:
            raw = self._post_generate(prompt, schema=schema, timeout=budget, system=system)
            response_text = raw.get("response", "")
            if not isinstance(response_text, str):
                raise OllamaGenerationError("Ollama response field is not a string.")
            return json.loads(response_text)
        except (OllamaGenerationError, json.JSONDecodeError) as exc:
            # Some Ollama/model combinations crash in the JSON-grammar sampler
            # ("Unexpected empty grammar stack") and return one token. Fall back
            # once to an unconstrained call and parse the JSON from the text,
            # within whatever time is left.
            remaining = int(budget - (time.monotonic() - started))
            if remaining < 2:
                raise OllamaGenerationError(f"Structured generation failed: {exc}") from exc
            logger.warning("Ollama structured output failed (%s); retrying without grammar", exc)
            text = self.generate(
                prompt + "\n\nRespond with ONLY a JSON object matching this schema, no other text:\n"
                + json.dumps(schema),
                timeout=remaining,
                system=system,
            )
            return _extract_json(text)

    def warm_up(self, timeout: int = 300) -> None:
        """Load the model into memory (a request with no prompt only loads it)."""
        payload = {
            "model": self._model,
            "keep_alive": ollama_config.keep_alive,
            "options": ollama_config.load_options(),
        }
        req = urllib_request.Request(
            url=f"{self._base_url}{GENERATE_PATH}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        self._send(req, timeout)

    def is_model_available(self, model: Optional[str] = None) -> bool:
        """Return True when the model is present in the local model list."""
        target = model or self._model
        try:
            tags = self._get_tags()
            models = [m.get("name", "") for m in tags.get("models", [])]
            return any(target in name for name in models)
        except OllamaError:
            return False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _post_generate(
        self,
        prompt: str,
        schema: Optional[Dict[str, Any]],
        timeout: Optional[int],
        system: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model":  self._model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": ollama_config.keep_alive,
            # Explicit window: never let Ollama truncate the prompt's start.
            "options": {
                **ollama_config.load_options(),
                "num_predict": ollama_config.num_predict,
                "temperature": ollama_config.temperature,
            },
        }
        if system:
            # Sent as the model's system message, not mixed into the prompt.
            payload["system"] = system
        if schema is not None:
            payload["format"] = schema

        body = json.dumps(payload).encode("utf-8")
        req  = urllib_request.Request(
            url=f"{self._base_url}{GENERATE_PATH}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        result = self._send(req, timeout or self._timeout)
        if result.get("done") is False:
            # stream=False always ends with done=true; done=false means the
            # server aborted mid-generation (see the Ollama server log).
            raise OllamaGenerationError(
                f"Ollama aborted generation after {len(result.get('response', ''))} chars."
            )
        return result

    def _stream_generate(
        self,
        prompt: str,
        timeout: int,
        system: Optional[str],
        on_text: Callable[[str, Optional[str]], None],
    ) -> str:
        payload: Dict[str, Any] = {
            "model": self._model,
            "prompt": prompt,
            "stream": True,
            "keep_alive": ollama_config.keep_alive,
            "options": {
                **ollama_config.load_options(),
                "num_predict": ollama_config.num_predict,
                "temperature": ollama_config.temperature,
            },
        }
        if system:
            payload["system"] = system
        req = urllib_request.Request(
            url=f"{self._base_url}{GENERATE_PATH}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        # The socket timeout only bounds each read; the deadline bounds the whole answer.
        deadline = time.monotonic() + timeout
        parts: list[str] = []
        try:
            with urllib_request.urlopen(req, timeout=timeout) as resp:
                for line in resp:
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if chunk.get("error"):
                        raise OllamaGenerationError(f"Ollama error: {chunk['error']}")
                    piece = chunk.get("response") or ""
                    if piece:
                        parts.append(piece)
                    if chunk.get("done"):
                        text = "".join(parts)
                        on_text(text, chunk.get("done_reason") or "stop")
                        return text
                    if piece:
                        on_text("".join(parts), None)
                    if time.monotonic() > deadline:
                        raise OllamaTimeoutError(f"Ollama request timed out after {timeout}s.")
        except TimeoutError as exc:
            raise OllamaTimeoutError(f"Ollama request timed out after {timeout}s.") from exc
        except json.JSONDecodeError as exc:
            raise OllamaGenerationError(f"Ollama returned invalid stream data: {exc}") from exc
        except error.HTTPError as exc:
            body = exc.read().decode() if hasattr(exc, "read") else str(exc)
            if exc.code == 404 and "model" in body.lower():
                raise OllamaModelNotFoundError(f"Model '{self._model}' not found on Ollama server.") from exc
            raise OllamaGenerationError(f"Ollama HTTP {exc.code}: {body}") from exc
        except error.URLError as exc:
            raise OllamaConnectionError(f"Cannot reach Ollama at {self._base_url}: {exc.reason}") from exc
        # The stream ended without done=true: the server aborted mid-answer.
        raise OllamaGenerationError(f"Ollama aborted generation after {len(''.join(parts))} chars.")

    def _get_tags(self) -> Dict[str, Any]:
        req = urllib_request.Request(
            url=f"{self._base_url}{TAGS_PATH}",
            method="GET",
        )
        return self._send(req, timeout=10)

    def _send(self, req: urllib_request.Request, timeout: int) -> Dict[str, Any]:
        try:
            with urllib_request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
        except TimeoutError as exc:
            raise OllamaTimeoutError(f"Ollama request timed out after {timeout}s.") from exc
        except error.HTTPError as exc:
            body = exc.read().decode() if hasattr(exc, "read") else str(exc)
            if exc.code == 404 and "model" in body.lower():
                raise OllamaModelNotFoundError(
                    f"Model '{self._model}' not found on Ollama server."
                ) from exc
            raise OllamaGenerationError(f"Ollama HTTP {exc.code}: {body}") from exc
        except error.URLError as exc:
            raise OllamaConnectionError(
                f"Cannot reach Ollama at {self._base_url}: {exc.reason}"
            ) from exc

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OllamaGenerationError(f"Ollama returned invalid JSON: {raw[:200]}") from exc


_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> Dict[str, Any]:
    match = _JSON_OBJECT.search(text or "")
    if not match:
        raise OllamaGenerationError(f"No JSON object in Ollama response: {(text or '')[:200]}")
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise OllamaGenerationError(f"Ollama response is not valid JSON: {match.group(0)[:200]}") from exc
    if not isinstance(parsed, dict):
        raise OllamaGenerationError("Ollama JSON response is not an object.")
    return parsed


# Singleton — reused across the process lifetime
from app.infra.ollama.exceptions import OllamaError  # noqa: E402 (after class def to avoid circular)

ollama_client = OllamaClient()
