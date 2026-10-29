from dataclasses import dataclass
from typing import Any

from app.core.enums import KnowledgeProcessingStage


@dataclass
class KnowledgeProcessingContext:
    knowledge_processing_run_id: str
    document_id: str
    document_version_id: str
    permanent_bucket: str
    permanent_object_key: str
    chunks_object_key: str
    embeddings_object_key: str
    current_stage: KnowledgeProcessingStage
    checkpoint_data: dict[str, Any]