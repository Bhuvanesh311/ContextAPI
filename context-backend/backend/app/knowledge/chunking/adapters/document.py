from __future__ import annotations

from langchain_core.documents import Document

from app.knowledge.chunking.adapters.base import BaseFormatAdapter
from app.knowledge.chunking.contracts.input import ChunkingInput


class DocumentAdapter(BaseFormatAdapter):
    """
    Adapter for document-oriented formats.

    The parsing layer has already extracted and normalized the document
    content. This adapter does not parse the original DOCX/PDF file.

    It converts the approved normalized representation into a LangChain
    Document while preserving relevant parser metadata.
    """

    @property
    def supported_formats(self) -> frozenset[str]:
        return frozenset(
            {
                "docx",
                "pdf",
                "pptx",
                "xlsx",
                "html",
                "image",
                "legacy_office",
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
                "chunking_strategy": "document",
            }
        )

        # Common document/parser metadata.
        for key in (
            "file_extension",
            "parser",
            "format",
            "file_size_bytes",
            "line_count",
            "extraction_strategies",
            "warnings",
        ):
            if key in chunking_input.metadata:
                metadata[key] = chunking_input.metadata[key]

        # Document structure metadata.
        for key in (
            "page_count",
            "paragraph_count",
            "section_count",
            "table_count",
            "image_count",
            "heading_count",
            "character_count",
            "word_count",
        ):
            if key in chunking_input.metadata:
                metadata[key] = chunking_input.metadata[key]

        return [
            Document(
                page_content=chunking_input.content,
                metadata=metadata,
            )
        ]