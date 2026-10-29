from __future__ import annotations

from langchain_core.documents import Document

from app.knowledge.chunking.adapters.base import BaseFormatAdapter
from app.knowledge.chunking.contracts.input import ChunkingInput


class SourceCodeAdapter(BaseFormatAdapter):
    """
    Adapter for source-code and SQL documents.

    Parsing, validation, and structural analysis are already handled
    by the parsing layer.

    This adapter does not parse or execute source code or SQL.

    It only converts the approved normalized representation into a
    LangChain Document while preserving parser-produced metadata.
    """

    @property
    def supported_formats(self) -> frozenset[str]:
        return frozenset(
            {
                "source_code",
                "sql",
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
                "chunking_strategy": "source_code",
            }
        )

        # Common parser metadata.
        for key in (
            "file_extension",
            "parser",
            "format",
            "file_size_bytes",
            "line_count",
            "word_count",
            "extraction_strategies",
            "warnings",
        ):
            if key in chunking_input.metadata:
                metadata[key] = chunking_input.metadata[key]

        # Source-code specific metadata.
        for key in (
            "language",
            "character_count",
            "tree_root_type",
            "tree_node_count",
            "syntax_error_count",
            "declaration_count",
            "declarations",
            "structured_json",
        ):
            if key in chunking_input.metadata:
                metadata[key] = chunking_input.metadata[key]

        # SQL-specific metadata.
        for key in (
            "structure",
            "statement_count",
            "statement_type_counts",
            "statements",
            "tables",
            "columns",
            "table_count",
            "column_count",
            "dialect",
        ):
            if key in chunking_input.metadata:
                metadata[key] = chunking_input.metadata[key]

        return [
            Document(
                page_content=chunking_input.content,
                metadata=metadata,
            )
        ]