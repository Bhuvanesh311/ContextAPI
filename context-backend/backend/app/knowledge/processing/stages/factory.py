from sqlalchemy.orm import Session

from app.infra.storage import storage_service

from app.knowledge.chunking.readers.ndjson import NDJSONReader
from app.knowledge.chunking.services.chunking_service import ChunkingService

from app.knowledge.embedding.providers.bge_m3 import (
    BGEM3EmbeddingProvider,
)
from app.knowledge.embedding.services.embedding_service import (
    EmbeddingService,
)

from app.knowledge.processing.services.chunk_persistence import (
    ChunkPersistenceService,
)
from app.knowledge.processing.services.embedding_persistence import (
    EmbeddingPersistenceService,
)

from app.knowledge.processing.stages.base import (
    BaseKnowledgeProcessingStage,
)
from app.knowledge.processing.stages.chunk_validation import (
    ChunkValidationStage,
)
from app.knowledge.processing.stages.chunking import (
    ChunkingStage,
)
from app.knowledge.processing.stages.embedding import (
    EmbeddingStage,
)
from app.knowledge.processing.stages.initialization import (
    InitializationStage,
)
from app.knowledge.processing.stages.registry import (
    KnowledgeProcessingStageRegistry,
)
from app.knowledge.processing.stages.source_validation import (
    SourceValidationStage,
)
from app.knowledge.processing.stages.vector_indexing import (
    VectorIndexingStage,
)
from app.knowledge.processing.stages.index_validation import (
    IndexValidationStage,
)
from app.knowledge.processing.services.indexing_persistence import (
    IndexingPersistenceService,
)
from app.infra.chromadb.client import chroma_client


def create_knowledge_processing_stage_registry(
    *,
    db: Session,
    chunking_service: ChunkingService,
) -> KnowledgeProcessingStageRegistry:
    chunk_persistence = ChunkPersistenceService(
        db=db,
    )

    embedding_persistence = EmbeddingPersistenceService(
        db=db,
    )

    indexing_persistence = IndexingPersistenceService(
        db=db,
    )

    embedding_provider = BGEM3EmbeddingProvider(
        model_name="BAAI/bge-m3",
        device="cpu",
        batch_size=32,
    )

    embedding_service = EmbeddingService(
        provider=embedding_provider,
    )

    stages: tuple[BaseKnowledgeProcessingStage, ...] = (
        InitializationStage(),

        SourceValidationStage(),

        ChunkingStage(
            chunking_service=chunking_service,
        ),

        ChunkValidationStage(
            storage=storage_service,
            reader=NDJSONReader(),
        ),

        EmbeddingStage(
            storage=storage_service,
            reader=NDJSONReader(),
            chunk_persistence=chunk_persistence,
            embedding_service=embedding_service,
            embedding_persistence=embedding_persistence,
            vector_database="chromadb",
            collection_name="knowledge",
        ),

        VectorIndexingStage(
            storage=storage_service,
            reader=NDJSONReader(),
            chroma_client=chroma_client,
            indexing_persistence=indexing_persistence,
            collection_name="knowledge",
        ),

        IndexValidationStage(
            storage=storage_service,
            chroma_client=chroma_client,
            collection_name="knowledge",
        ),
    )

    return KnowledgeProcessingStageRegistry(
        stages=stages,
    )