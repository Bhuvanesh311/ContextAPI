from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import time
import uuid

from app.retrieval.engine.schemas import RawRetrievalResult
from app.retrieval.engine.scope_guard import require_version_scope

def _thaw(value):
    """
    Turn the frozen structures produced by the planner back into plain
    Python types that ChromaDB accepts.

    The planner freezes every step_scope: dict -> FrozenDict and
    list -> tuple (see planning/schemas.py::_freeze_dict). ChromaDB's
    `where` validation requires a real list for the "$in" operator, so
    passing the frozen tuple makes every semantic search fail with
    "Expected where value for $in to be a list" -- and the executor
    swallows that error, so the API would just return zero results.
    """
    if isinstance(value, dict):
        return {k: _thaw(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(v) for v in value]
    return value


class VectorUpsertRequest(BaseModel):
    vector_id: str
    embedding: List[float]
    metadata: Dict[str, Any]
    
class VectorSearchRequest(BaseModel):
    embedding: List[float]
    top_k: int
    filters: Dict[str, Any]

class VectorStoreAdapter(ABC):
    @abstractmethod
    def upsert(self, requests: List[VectorUpsertRequest]) -> None:
        pass
        
    @abstractmethod
    def search(self, request: VectorSearchRequest, step_id: str) -> List[RawRetrievalResult]:
        pass

class ChromaVectorStoreAdapter(VectorStoreAdapter):
    # NOTE: "knowledge" is the collection the ingestion pipeline
    # (app/knowledge/processing/stages/vector_indexing.py) actually writes
    # to. It was "contextapi_chunks" before, which is a different, always-empty
    # collection, so search() would silently return nothing.
    def __init__(self, collection_name: str = "knowledge"):
        from app.infra.chromadb.client import chroma_client
        self.client = chroma_client
        self.collection_name = collection_name
        
        # The "knowledge" collection already exists (created by the ingestion
        # pipeline), so we just open it as it is.
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name
        )

    def upsert(self, requests: List[VectorUpsertRequest]) -> None:
        if not requests:
            return
            
        ids = [req.vector_id for req in requests]
        embeddings = [req.embedding for req in requests]
        metadatas = [req.metadata for req in requests]
        
        # We don't store documents in Chroma, only metadata and embeddings
        # PostgreSQL holds canonical content.
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas
        )

    def search(self, request: VectorSearchRequest, step_id: str) -> List[RawRetrievalResult]:
        start = time.time()
        
        # Translate filters to Chroma format if needed. 
        # For simple exact match dict, Chroma accepts it as is.
        require_version_scope(request.filters)
        chroma_where = _thaw(request.filters)
        
        results = self.collection.query(
            query_embeddings=[request.embedding],
            n_results=request.top_k,
            where=chroma_where,
            include=["metadatas", "distances"]
        )
        
        raw_hits = []
        if results and results["ids"] and len(results["ids"]) > 0:
            ids = results["ids"][0]
            distances = results["distances"][0] if results.get("distances") else []
            metadatas = results["metadatas"][0] if results.get("metadatas") else []
            
            for i, vid in enumerate(ids):
                # Chroma's default L2 distance; vectors are normalized, so
                # 1 - distance keeps the ranking (not a calibrated similarity).
                dist = distances[i] if i < len(distances) else 0.0
                score = 1.0 - dist
                
                meta = metadatas[i] if i < len(metadatas) else {}
                
                raw_hits.append(RawRetrievalResult(
                    step_id=step_id,
                    vector_id=vid,
                    score=score,
                    metadata_hits=meta
                ))
                
        return raw_hits