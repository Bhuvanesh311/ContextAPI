from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from app.knowledge.embedding.contract.result import (
    EmbeddingBatchResult,
    EmbeddingResult,
)


class EmbeddingProvider(ABC):
    """
    Provider abstraction for embedding generation.

    Providers are responsible only for converting text into vectors.
    They must not persist database records or write to Chroma.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider identifier."""
        raise NotImplementedError

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model identifier."""
        raise NotImplementedError

    @property
    @abstractmethod
    def model_version(self) -> str | None:
        """Return the model version when available."""
        raise NotImplementedError

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the embedding dimension."""
        raise NotImplementedError

    @abstractmethod
    def embed(self, text: str) -> EmbeddingResult:
        """
        Generate one embedding.
        """
        raise NotImplementedError

    @abstractmethod
    def embed_batch(
        self,
        texts: Sequence[str],
    ) -> EmbeddingBatchResult:
        """
        Generate embeddings for multiple texts.
        """
        raise NotImplementedError