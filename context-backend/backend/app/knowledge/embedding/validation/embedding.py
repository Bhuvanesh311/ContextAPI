from __future__ import annotations

import math
from collections.abc import Sequence


class EmbeddingValidationError(ValueError):
    """Raised when an embedding fails validation."""


class EmbeddingValidator:
    """
    Validates embedding vectors independently from the provider.
    """

    @staticmethod
    def validate(
        vector: Sequence[float],
        *,
        expected_dimension: int,
    ) -> None:

        if not isinstance(vector, Sequence):
            raise EmbeddingValidationError(
                "embedding vector must be a sequence"
            )

        if not vector:
            raise EmbeddingValidationError(
                "embedding vector must not be empty"
            )

        if len(vector) != expected_dimension:
            raise EmbeddingValidationError(
                f"embedding dimension mismatch: "
                f"expected {expected_dimension}, "
                f"got {len(vector)}"
            )

        for index, value in enumerate(vector):

            if not isinstance(value, (float, int)):
                raise EmbeddingValidationError(
                    f"embedding[{index}] must be numeric"
                )

            if not math.isfinite(float(value)):
                raise EmbeddingValidationError(
                    f"embedding[{index}] must be finite"
                )

    @staticmethod
    def validate_batch(
        vectors: Sequence[Sequence[float]],
        *,
        expected_count: int,
        expected_dimension: int,
    ) -> None:

        if len(vectors) != expected_count:
            raise EmbeddingValidationError(
                f"embedding count mismatch: "
                f"expected {expected_count}, "
                f"got {len(vectors)}"
            )

        for vector in vectors:
            EmbeddingValidator.validate(
                vector,
                expected_dimension=expected_dimension,
            )