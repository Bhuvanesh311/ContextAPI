from collections.abc import Iterable

from app.knowledge.chunking.adapters.base import BaseFormatAdapter


class FormatAdapterRegistry:
    """Resolves the correct format adapter for a normalized document."""

    def __init__(self, adapters: Iterable[BaseFormatAdapter]) -> None:
        self._adapters = tuple(adapters)

        if not self._adapters:
            raise ValueError("At least one format adapter must be registered")

        self._validate_supported_formats()

    def get(self, source_format: str) -> BaseFormatAdapter:
        normalized_format = source_format.strip().lower()

        if not normalized_format:
            raise ValueError("source_format cannot be empty")

        matches = [
            adapter
            for adapter in self._adapters
            if adapter.supports(normalized_format)
        ]

        if not matches:
            raise ValueError(
                f"No chunking adapter registered for format "
                f"'{normalized_format}'"
            )

        if len(matches) > 1:
            raise ValueError(
                f"Multiple chunking adapters registered for format "
                f"'{normalized_format}'"
            )

        return matches[0]

    def _validate_supported_formats(self) -> None:
        seen: dict[str, BaseFormatAdapter] = {}

        for adapter in self._adapters:
            for source_format in adapter.supported_formats:
                normalized_format = source_format.strip().lower()

                if not normalized_format:
                    raise ValueError(
                        f"{adapter.__class__.__name__} declares an empty format"
                    )

                if normalized_format in seen:
                    previous = seen[normalized_format].__class__.__name__

                    raise ValueError(
                        f"Format '{normalized_format}' is registered by both "
                        f"{previous} and {adapter.__class__.__name__}"
                    )

                seen[normalized_format] = adapter