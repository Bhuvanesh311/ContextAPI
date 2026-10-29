from app.knowledge.chunking.adapters.document import DocumentAdapter
from app.knowledge.chunking.adapters.log import LogAdapter
from app.knowledge.chunking.adapters.markdown import MarkdownAdapter
from app.knowledge.chunking.adapters.registry import FormatAdapterRegistry
from app.knowledge.chunking.adapters.source_code import SourceCodeAdapter
from app.knowledge.chunking.adapters.structured import StructuredTextAdapter
from app.knowledge.chunking.adapters.text import TextAdapter

def create_default_registry() -> FormatAdapterRegistry:
    return FormatAdapterRegistry(
        adapters=(
            TextAdapter(),
            MarkdownAdapter(),
            LogAdapter(),
            StructuredTextAdapter(),
            SourceCodeAdapter(),
            DocumentAdapter(),
        )
    )