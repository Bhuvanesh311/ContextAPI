from __future__ import annotations

from collections.abc import Sequence

from app.knowledge.embedding.contract.result import (
    EmbeddingBatchResult,
    EmbeddingResult,
)
from app.knowledge.embedding.providers.base import EmbeddingProvider
from app.knowledge.embedding.validation.embedding import (
    EmbeddingValidator,
)


class EmbeddingService:
    """
    Application service for embedding generation.

    Responsibilities:
    - validate input
    - invoke provider
    - validate provider output
    - return canonical embedding results

    Does not:
    - persist database records
    - write vectors to MinIO
    - write vectors to Chroma
    - modify processing-run state
    """

    def __init__(
        self,
        *,
        provider: EmbeddingProvider,
    ) -> None:
        self._provider = provider

    @property
    def provider(self) -> EmbeddingProvider:
        return self._provider

    def embed(self, text: str) -> EmbeddingResult:
        if not isinstance(text, str):
            raise TypeError("text must be a string")

        if not text.strip():
            raise ValueError("text must not be empty")

        result = self._provider.embed(text)

        EmbeddingValidator.validate(
            result.vector,
            expected_dimension=self._provider.dimension,
        )

        return result

    def embed_batch(
        self,
        texts: Sequence[str],
    ) -> EmbeddingBatchResult:

        if not texts:
            raise ValueError("texts must not be empty")

        result = self._provider.embed_batch(texts)

        vectors = tuple(
            embedding.vector
            for embedding in result.embeddings
        )

        EmbeddingValidator.validate_batch(
            vectors,
            expected_count=len(texts),
            expected_dimension=self._provider.dimension,
        )

        return result