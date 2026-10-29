from langchain_core.documents import Document

from app.knowledge.chunking.adapters.base import BaseFormatAdapter
from app.knowledge.chunking.contracts.input import ChunkingInput


class LogAdapter(BaseFormatAdapter):
    """Adapter for line-oriented log documents."""

    @property
    def supported_formats(self) -> frozenset[str]:
        return frozenset({"log"})

    def adapt(self, chunking_input: ChunkingInput) -> list[Document]:
        metadata = self.base_metadata(chunking_input)

        metadata.update(
            {
                "adapter": self.__class__.__name__,
                "structure": "line_oriented_text",
            }
        )

        # Preserve parser-provided log metadata without modifying it.
        for key in (
            "line_count",
            "timestamp_detected",
            "timestamped_line_count",
            "level_detected_line_count",
            "continuation_line_count",
            "level_counts",
            "extraction_strategies",
            "warnings",
        ):
            if key in chunking_input.metadata:
                metadata[key] = chunking_input.metadata[key]

        return [
            Document(
                page_content=chunking_input.content,
                metadata=metadata,
            )
        ]