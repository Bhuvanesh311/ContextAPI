import time
from typing import Any, Callable, Dict, Optional

from app.retrieval.intelligence.providers.base import AbstractModelProvider
from app.retrieval.intelligence.providers.ollama import OllamaProvider
from app.retrieval.intelligence.providers.external import (
    GeminiProvider, GroqProvider, DeepSeekProvider,
    OpenRouterProvider, KimiProvider,
)
from app.infra.ollama.config import ollama_config
import os


class ModelProviderRouter:
    def __init__(self):
        self.tier_b_provider = OllamaProvider(
            base_url=ollama_config.base_url,
            model=ollama_config.model,
            timeout=ollama_config.timeout_seconds,
        )

        self.tier_c_providers = {
            "gemini":      GeminiProvider(api_key=os.getenv("GEMINI_API_KEY",      "MOCK_GEMINI_KEY")),
            "groq":        GroqProvider(api_key=os.getenv("GROQ_API_KEY",          "MOCK_GROQ_KEY")),
            "deepseek":    DeepSeekProvider(api_key=os.getenv("DEEPSEEK_API_KEY",  "MOCK_DEEPSEEK_KEY")),
            "openrouter":  OpenRouterProvider(api_key=os.getenv("OPENROUTER_API_KEY", "MOCK_OPENROUTER_KEY")),
            "kimi":        KimiProvider(api_key=os.getenv("KIMI_API_KEY",          "MOCK_KIMI_KEY")),
        }

        self._provider_order = ["gemini", "groq", "deepseek", "openrouter", "kimi"]
        self._cooldowns: Dict[str, float] = {}
        self.COOLDOWN_SECONDS = 60

    def execute_tier_b(
        self,
        prompt: str,
        schema: Dict[str, Any],
        timeout: int = 60,
        system: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute the local Ollama SLM (offline, Tier B)."""
        if system is None:
            return self.tier_b_provider.generate_structured(prompt, schema, timeout)
        return self.tier_b_provider.generate_structured(prompt, schema, timeout, system=system)

    def execute_tier_b_text(
        self,
        prompt: str,
        timeout: int = 60,
        system: Optional[str] = None,
        on_text: Optional[Callable[[str, Optional[str]], None]] = None,
    ) -> str:
        """Free-text generation on the local model (no JSON grammar involved); streamed with `on_text`."""
        return self.tier_b_provider.generate_text(prompt, timeout=timeout, system=system, on_text=on_text)

    def has_tier_c(self) -> bool:
        """True when at least one external provider has a real API key."""
        for provider in self.tier_c_providers.values():
            key = str(getattr(provider, "_api_key", "") or "")
            if key and not key.startswith("MOCK_"):
                return True
        return False

    def execute_tier_c(
        self,
        prompt: str,
        schema: Dict[str, Any],
        timeout: int = 60,
        deadline: Optional[float] = None,
        system: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute an external LLM (Tier C) with bounded fallback and cooldown.
        `deadline` (time.monotonic()) bounds ALL providers together, so trying
        several in a row can never exceed the caller's budget.
        Raises RuntimeError when all providers are exhausted.
        """
        errors = []
        now = time.time()

        for p_name in self._provider_order:
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining < 1:
                    errors.append("time budget exhausted")
                    break
                timeout = min(timeout, int(remaining))
            if p_name in self._cooldowns:
                if now < self._cooldowns[p_name]:
                    errors.append(f"{p_name} skipped (in cooldown)")
                    continue
                del self._cooldowns[p_name]

            provider = self.tier_c_providers[p_name]
            try:
                if system is None:
                    return provider.generate_structured(prompt, schema, timeout)
                return provider.generate_structured(prompt, schema, timeout, system=system)
            except RuntimeError as exc:
                msg = str(exc).lower()
                if "429" in msg or "rate limit" in msg or "quota" in msg:
                    self._cooldowns[p_name] = now + self.COOLDOWN_SECONDS
                errors.append(f"{p_name} failed: {exc}")
            except Exception as exc:
                errors.append(f"{p_name} unexpected failure: {exc}")

        raise RuntimeError(
            f"All Tier C providers failed or exhausted. Errors: {'; '.join(errors)}"
        )
