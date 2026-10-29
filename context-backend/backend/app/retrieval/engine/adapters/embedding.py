from abc import ABC, abstractmethod
from typing import List, Optional
from pydantic import BaseModel
import time

class QueryEmbeddingRequest(BaseModel):
    query_text: str
    
class DocumentEmbeddingRequest(BaseModel):
    document_texts: List[str]

class QueryEmbeddingResult(BaseModel):
    embedding: List[float]
    dimensions: int
    provider: str
    model: str
    latency_ms: int

class DocumentEmbeddingResult(BaseModel):
    embeddings: List[List[float]]
    dimensions: int
    provider: str
    model: str
    latency_ms: int

class EmbeddingAdapter(ABC):
    @abstractmethod
    def embed_query(self, request: QueryEmbeddingRequest) -> QueryEmbeddingResult:
        pass
        
    @abstractmethod
    def embed_documents(self, request: DocumentEmbeddingRequest) -> DocumentEmbeddingResult:
        pass

# Sentinel for lazy loading
_model_instance = None

class SentenceTransformerEmbeddingAdapter(EmbeddingAdapter):
    """
    Kept for reference / future use. NOT used by the retrieval pipeline
    right now, because the documents already indexed in ChromaDB were
    embedded with BAAI/bge-m3 (see BGEM3EmbeddingAdapter below), and a
    query must be embedded with the SAME model + dimension as the
    documents, or the vector search is meaningless (and may error on a
    dimension mismatch).
    """
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._lazy_init_model()
        
    def _lazy_init_model(self):
        global _model_instance
        if _model_instance is None:
            from sentence_transformers import SentenceTransformer
            _model_instance = SentenceTransformer(self.model_name)
        self.model = _model_instance

    def embed_query(self, request: QueryEmbeddingRequest) -> QueryEmbeddingResult:
        start = time.time()
        embedding = self.model.encode(request.query_text, normalize_embeddings=True)
        vec = embedding.tolist()
        
        if not vec:
            raise ValueError("Empty vector generated")
            
        latency = int((time.time() - start) * 1000)
        return QueryEmbeddingResult(
            embedding=vec,
            dimensions=len(vec),
            provider="sentence-transformers",
            model=self.model_name,
            latency_ms=latency
        )

    def embed_documents(self, request: DocumentEmbeddingRequest) -> DocumentEmbeddingResult:
        start = time.time()
        embeddings = self.model.encode(request.document_texts, normalize_embeddings=True)
        vecs = [e.tolist() for e in embeddings]
        
        if not vecs or not vecs[0]:
            raise ValueError("Empty vector generated")
            
        latency = int((time.time() - start) * 1000)
        return DocumentEmbeddingResult(
            embeddings=vecs,
            dimensions=len(vecs[0]),
            provider="sentence-transformers",
            model=self.model_name,
            latency_ms=latency
        )


_bge_provider_instance = None


class BGEM3EmbeddingAdapter(EmbeddingAdapter):
    """
    Wraps the SAME embedding provider used by the ingestion pipeline
    (app/knowledge/embedding/providers/bge_m3.py). This is the adapter
    the retrieval pipeline must use, so that a query and the documents
    it searches against live in the same vector space.
    """

    def __init__(self):
        global _bge_provider_instance
        if _bge_provider_instance is None:
            from app.knowledge.embedding.providers.bge_m3 import BGEM3EmbeddingProvider
            _bge_provider_instance = BGEM3EmbeddingProvider()
        self._provider = _bge_provider_instance

    def warm_up(self) -> None:
        self._provider.embed("warm up")

    def embed_query(self, request: QueryEmbeddingRequest) -> QueryEmbeddingResult:
        start = time.time()
        result = self._provider.embed(request.query_text)
        vec = list(result.vector)

        if not vec:
            raise ValueError("Empty vector generated")

        return QueryEmbeddingResult(
            embedding=vec,
            dimensions=len(vec),
            provider="bge-m3",
            model="BAAI/bge-m3",
            latency_ms=int((time.time() - start) * 1000),
        )

    def embed_documents(self, request: DocumentEmbeddingRequest) -> DocumentEmbeddingResult:
        start = time.time()
        vecs = [list(self._provider.embed(text).vector) for text in request.document_texts]

        if not vecs or not vecs[0]:
            raise ValueError("Empty vector generated")

        return DocumentEmbeddingResult(
            embeddings=vecs,
            dimensions=len(vecs[0]),
            provider="bge-m3",
            model="BAAI/bge-m3",
            latency_ms=int((time.time() - start) * 1000),
        )