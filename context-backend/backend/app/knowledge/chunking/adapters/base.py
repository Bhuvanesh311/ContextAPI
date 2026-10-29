from abc import ABC, abstractmethod
from typing import Any

from langchain_core.documents import Document

from app.knowledge.chunking.contracts.input import ChunkingInput


class BaseFormatAdapter(ABC):
    """Base contract for converting normalized input into framework documents."""

    @property
    @abstractmethod
    def supported_formats(self) -> frozenset[str]:
        """Return the source formats supported by this adapter."""
        raise NotImplementedError

    def supports(self, source_format: str) -> bool:
        """Return whether this adapter supports the given source format."""
        return source_format.lower() in self.supported_formats

    @abstractmethod
    def adapt(self, chunking_input: ChunkingInput) -> list[Document]:
        """
        Convert a normalized document into framework documents.

        Each returned Document represents a logical structural unit
        that can subsequently be processed by the framework splitter.
        """
        raise NotImplementedError

    @staticmethod
    def base_metadata(chunking_input: ChunkingInput) -> dict[str, Any]:
        """Build metadata common to all adapted documents."""
        return {
            "document_id": chunking_input.document_id,
            "document_version_id": chunking_input.document_version_id,
            "file_name": chunking_input.file_name,
            "source_format": chunking_input.source_format,
            "mime_type": chunking_input.mime_type,
        }