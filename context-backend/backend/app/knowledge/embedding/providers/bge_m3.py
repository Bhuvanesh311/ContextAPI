from __future__ import annotations

from typing import Sequence

from app.knowledge.embedding.contract.result import (
    EmbeddingBatchResult,
    EmbeddingResult,
)
from app.knowledge.embedding.providers.base import EmbeddingProvider

import threading

# One copy of each model per process (BGE-M3 is ~2.3 GB). Ingestion and
# retrieval create their own provider objects; they share the weights.
_models: dict[tuple[str, str], object] = {}
_models_lock = threading.Lock()


def _shared_model(model_name: str, device: str):
    key = (model_name, device)
    with _models_lock:
        if key not in _models:
            from sentence_transformers import SentenceTransformer

            _models[key] = SentenceTransformer(model_name, device=device)
        return _models[key]


class BGEM3EmbeddingProvider(EmbeddingProvider):
    """
    BAAI BGE-M3 embedding provider.

    This class owns model loading and inference.
    It does not know about DocumentChunk, Postgres,
    MinIO, Chroma, or KnowledgeProcessingRun.
    """

    def __init__(
        self,
        *,
        model_name: str = "BAAI/bge-m3",
        device: str = "cpu",
        batch_size: int = 32,
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._batch_size = batch_size

        self._model = None

    @property
    def provider_name(self) -> str:
        return "huggingface"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_version(self) -> str | None:
        return None

    @property
    def dimension(self) -> int:
        return 1024

    def _load_model(self):
        if self._model is None:
            self._model = _shared_model(self._model_name, self._device)

        return self._model

    def embed(self, text: str) -> EmbeddingResult:
        if not isinstance(text, str):
            raise TypeError("text must be a string")

        if not text.strip():
            raise ValueError("text must not be empty")

        result = self.embed_batch([text])

        return result.embeddings[0]

    def embed_batch(
        self,
        texts: Sequence[str],
    ) -> EmbeddingBatchResult:

        if not texts:
            raise ValueError("texts must not be empty")

        normalized_texts = []

        for index, text in enumerate(texts):
            if not isinstance(text, str):
                raise TypeError(
                    f"texts[{index}] must be a string"
                )

            if not text.strip():
                raise ValueError(
                    f"texts[{index}] must not be empty"
                )

            normalized_texts.append(text)

        model = self._load_model()

        vectors = model.encode(
            normalized_texts,
            batch_size=self._batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

        embeddings = tuple(
            EmbeddingResult(
                vector=tuple(float(value) for value in vector),
                provider=self.provider_name,
                model=self.model_name,
                model_version=self.model_version,
                dimension=self.dimension,
            )
            for vector in vectors
        )

        return EmbeddingBatchResult(
            embeddings=embeddings,
        )