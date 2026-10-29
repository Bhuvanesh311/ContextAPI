from typing import List, Dict
from sqlalchemy.orm import Session
from app.retrieval.engine.resolution import BaseContentResolver
from app.retrieval.engine.schemas import RawRetrievalResult, CandidateEvidence, ProvenanceMetadata
from app.retrieval.engine.enums import OperatorType
from app.knowledge.uploads.models import ChunkEmbedding, DocumentChunk, DocumentVersion

class PostgresContentResolver(BaseContentResolver):
    def __init__(self, session: Session):
        self.session = session
        
    def resolve(self, raw_results: List[RawRetrievalResult]) -> List[CandidateEvidence]:
        if not raw_results:
            return []
            
        # Extract unique vector IDs
        vector_ids = [r.vector_id for r in raw_results if r.vector_id]
        
        if not vector_ids:
            return []
            
        # Query DB for ChunkEmbedding
        embeddings = (
            self.session.query(ChunkEmbedding)
            .filter(ChunkEmbedding.vector_id.in_(vector_ids))
            .all()
        )
        
        vector_to_chunk = {e.vector_id: e.chunk_id for e in embeddings}
        
        # Add lexical chunks
        _LEXICAL_PREFIX = "lexical_"
        lexical_ids = [r.vector_id for r in raw_results if r.vector_id and r.vector_id.startswith(_LEXICAL_PREFIX)]
        for lid in lexical_ids:
            vector_to_chunk[lid] = lid.removeprefix(_LEXICAL_PREFIX)
            
        chunk_ids = list(vector_to_chunk.values())
        
        # Query DB for DocumentChunk
        chunks = (
            self.session.query(DocumentChunk)
            .filter(DocumentChunk.chunk_id.in_(chunk_ids))
            .all()
        )
        
        chunk_map = {c.chunk_id: c for c in chunks}

        # NOTE (fix): DocumentChunk only stores document_version_id, not the
        # parent document_id. The original code hardcoded document_id as
        # "doc-unknown". We resolve the real document_id here via
        # DocumentVersion so the API response is actually useful.
        version_ids = {c.document_version_id for c in chunk_map.values()}
        versions = (
            self.session.query(DocumentVersion)
            .filter(DocumentVersion.document_version_id.in_(version_ids))
            .all()
        ) if version_ids else []
        version_to_document_id = {v.document_version_id: v.document_id for v in versions}
        
        candidates = []
        for raw in raw_results:
            if not raw.vector_id or raw.vector_id not in vector_to_chunk:
                continue
            
            chunk_id = vector_to_chunk[raw.vector_id]
            chunk = chunk_map.get(chunk_id)
            
            if not chunk:
                continue
                
            prov = ProvenanceMetadata(
                document_id=version_to_document_id.get(chunk.document_version_id, "doc-unknown"),
                document_version_id=chunk.document_version_id,
                chunk_id=chunk.chunk_id,
                source_type="postgres",
                step_id=raw.step_id,
                operator_type=(
                    OperatorType.LEXICAL
                    if raw.vector_id.startswith("lexical_")
                    else OperatorType.SEMANTIC
                ),
            )
            
            candidates.append(CandidateEvidence(
                content=chunk.content,
                provenance=prov,
                score=raw.score,
                retrieval_metadata=dict(raw.metadata_hits)
            ))
            
        return candidates