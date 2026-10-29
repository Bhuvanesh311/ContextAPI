from dataclasses import dataclass

from app.core.config import settings
from app.infra.ollama.constants import DEFAULT_BASE_URL, DEFAULT_MODEL, DEFAULT_TIMEOUT_SECONDS


@dataclass(frozen=True)
class OllamaConfig:
    base_url: str
    model: str
    timeout_seconds: int
    num_ctx: int = 4096
    num_predict: int = 1024
    temperature: float = 0.1
    num_gpu: int | None = None
    keep_alive: str = "24h"

    def load_options(self) -> dict:
        """
        Options that decide how the model is loaded. Every caller must send
        the same values: Ollama reloads the model (~20 s on a CPU) whenever
        a request asks for a different context window or GPU split.
        """
        options: dict = {"num_ctx": self.num_ctx}
        if self.num_gpu is not None:
            options["num_gpu"] = self.num_gpu
        return options


ollama_config = OllamaConfig(
    base_url=getattr(settings, "OLLAMA_BASE_URL", DEFAULT_BASE_URL),
    model=getattr(settings, "OLLAMA_MODEL", DEFAULT_MODEL),
    timeout_seconds=getattr(settings, "OLLAMA_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS),
    num_ctx=getattr(settings, "OLLAMA_NUM_CTX", 4096),
    num_predict=getattr(settings, "OLLAMA_NUM_PREDICT", 1024),
    temperature=getattr(settings, "OLLAMA_TEMPERATURE", 0.1),
    num_gpu=getattr(settings, "OLLAMA_NUM_GPU", None),
    keep_alive=getattr(settings, "OLLAMA_KEEP_ALIVE", "24h"),
)
