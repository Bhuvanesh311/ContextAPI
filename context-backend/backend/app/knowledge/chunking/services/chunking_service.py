from app.knowledge.chunking.adapters.registry import FormatAdapterRegistry
from app.knowledge.chunking.contracts.chunk import CanonicalChunk
from app.knowledge.chunking.readers.permanent_artifact import (
    PermanentArtifactReader,
)
from app.knowledge.chunking.services.canonicalizer import ChunkCanonicalizer
from app.knowledge.chunking.splitters.framework import FrameworkTextSplitter
from app.knowledge.chunking.writers.ndjson import NDJSONWriter


class ChunkingService:
    """Orchestrates the standalone document chunking pipeline."""

    def __init__(
        self,
        *,
        reader: PermanentArtifactReader,
        adapter_registry: FormatAdapterRegistry,
        splitter: FrameworkTextSplitter,
        canonicalizer: ChunkCanonicalizer,
        writer: NDJSONWriter,
    ) -> None:
        self.reader = reader
        self.adapter_registry = adapter_registry
        self.splitter = splitter
        self.canonicalizer = canonicalizer
        self.writer = writer

    def process(
        self,
        *,
        document_id: str,
        document_version_id: str,
        permanent_bucket: str,
        permanent_object_key: str,
        chunks_object_key: str,
    ) -> list[CanonicalChunk]:
        chunking_input = self.reader.read(
            document_id=document_id,
            document_version_id=document_version_id,
            permanent_bucket=permanent_bucket,
            permanent_object_key=permanent_object_key,
        )

        adapter = self.adapter_registry.get(
            chunking_input.source_format
        )

        documents = adapter.adapt(chunking_input)

        split_documents = self.splitter.split(documents)

        chunks = self.canonicalizer.canonicalize(
            documents=split_documents,
            chunking_input=chunking_input,
        )

        self.writer.write(
            chunks=chunks,
            bucket=permanent_bucket,
            object_key=chunks_object_key,
        )

        return chunks