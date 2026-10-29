from app.infra.storage import storage_service
from app.knowledge.chunking.adapters.defaults import (
    create_default_registry,
)
from app.knowledge.chunking.readers.permanent_artifact import (
    PermanentArtifactReader,
)
from app.knowledge.chunking.services.canonicalizer import (
    ChunkCanonicalizer,
)
from app.knowledge.chunking.services.chunking_service import (
    ChunkingService,
)
from app.knowledge.chunking.splitters.framework import (
    FrameworkTextSplitter,
)
from app.knowledge.chunking.writers.ndjson import (
    NDJSONWriter,
)


def create_chunking_service() -> ChunkingService:
    return ChunkingService(
        reader=PermanentArtifactReader(storage_service),
        adapter_registry=create_default_registry(),
        splitter=FrameworkTextSplitter(),
        canonicalizer=ChunkCanonicalizer(),
        writer=NDJSONWriter(storage_service),
    )