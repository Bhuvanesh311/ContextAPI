from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EmbeddingRequest:
    """
    Input contract for generating an embedding.

    The embedding provider receives normalized text only.
    """

    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise TypeError("text must be a string")

        if not self.text.strip():
            raise ValueError("text must not be empty")



@dataclass(frozen=True)
class EmbeddingBatchRequest:
    """
    Input contract for batch embedding generation.
    """

    texts: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.texts, tuple):
            raise TypeError("texts must be a tuple")

        if not self.texts:
            raise ValueError("texts must not be empty")

        for index, text in enumerate(self.texts):
            if not isinstance(text, str):
                raise TypeError(
                    f"texts[{index}] must be a string"
                )

            if not text.strip():
                raise ValueError(
                    f"texts[{index}] must not be empty"
                )