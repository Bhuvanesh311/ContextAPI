from __future__ import annotations

from langchain_core.documents import Document

from app.knowledge.chunking.adapters.base import BaseFormatAdapter
from app.knowledge.chunking.contracts.input import ChunkingInput


class StructuredTextAdapter(BaseFormatAdapter):
    """
    Adapter for structured documents whose parsing stage has already
    normalized the source content into text.

    Supported parser formats:
        - json
        - yaml
        - xml
        - csv
        - config

    The adapter does not re-parse the source content.

    Parsing is already the responsibility of the parsing layer.
    This layer only adapts the security-approved NormalizedDocument
    representation into LangChain Documents for framework-based chunking.
    """

    @property
    def supported_formats(self) -> frozenset[str]:
        return frozenset(
            {
                "json",
                "yaml",
                "xml",
                "csv",
                "config",
            }
        )

    def adapt(
        self,
        chunking_input: ChunkingInput,
    ) -> list[Document]:
        metadata = self.base_metadata(chunking_input)

        metadata.update(
            {
                "adapter": self.__class__.__name__,
                "chunking_strategy": "structured_text",
            }
        )

        # Preserve parser-produced metadata without re-parsing content.
        for key in (
            "file_extension",
            "parser",
            "format",
            "file_size_bytes",
            "structure",
            "root_type",
            "node_count",
            "object_count",
            "array_count",
            "object_key_count",
            "array_item_count",
            "maximum_depth",
            "string_characters",
            "root_key_count",
            "root_keys",
            "root_item_count",
            "row_count",
            "column_count",
            "headers",
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