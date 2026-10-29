from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class EmbeddingResult:
    """
    Result produced by an embedding provider for one text.
    """

    vector: tuple[float, ...]
    provider: str
    model: str
    model_version: str | None
    dimension: int

    def __post_init__(self) -> None:
        if not self.vector:
            raise ValueError("vector must not be empty")

        if not self.provider.strip():
            raise ValueError("provider must not be empty")

        if not self.model.strip():
            raise ValueError("model must not be empty")

        if self.model_version is not None and not self.model_version.strip():
            raise ValueError(
                "model_version must not be empty when provided"
            )

        if self.dimension <= 0:
            raise ValueError("dimension must be greater than zero")

        if len(self.vector) != self.dimension:
            raise ValueError(
                "vector length must match dimension"
            )

        for index, value in enumerate(self.vector):
            if not isinstance(value, (float, int)):
                raise TypeError(
                    f"vector[{index}] must be numeric"
                )


@dataclass(frozen=True)
class EmbeddingBatchResult:
    """
    Result produced by an embedding provider for multiple texts.
    """

    embeddings: tuple[EmbeddingResult, ...]

    def __post_init__(self) -> None:
        if not self.embeddings:
            raise ValueError("embeddings must not be empty")