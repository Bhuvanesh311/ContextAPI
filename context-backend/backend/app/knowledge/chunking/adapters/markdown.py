from langchain_core.documents import Document

from app.knowledge.chunking.adapters.base import BaseFormatAdapter
from app.knowledge.chunking.contracts.input import ChunkingInput


class MarkdownAdapter(BaseFormatAdapter):
    """Adapter for Markdown documents."""

    @property
    def supported_formats(self) -> frozenset[str]:
        return frozenset({"md", "markdown"})

    def adapt(self, chunking_input: ChunkingInput) -> list[Document]:
        metadata = self.base_metadata(chunking_input)

        metadata.update(
            {
                "adapter": self.__class__.__name__,
            }
        )

        return [
            Document(
                page_content=chunking_input.content,
                metadata=metadata,
            )
        ]