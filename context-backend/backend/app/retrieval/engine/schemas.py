from typing import List, Dict, Any, Optional, Tuple, Mapping
from pydantic import BaseModel, Field, ConfigDict, field_validator
import uuid
from datetime import datetime, timezone


def utc_now() -> datetime:
    """Current UTC time as a naive datetime (same value utcnow() gave, no deprecation warning)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

from app.retrieval.engine.enums import ExecutionStatus, OperatorType

class FrozenDict(dict):
    def __setitem__(self, key, value):
        raise TypeError(f"'{type(self).__name__}' object does not support item assignment")
    def __delitem__(self, key):
        raise TypeError(f"'{type(self).__name__}' object does not support item deletion")
    def update(self, *args, **kwargs):
        raise TypeError(f"'{type(self).__name__}' object does not support update")

def _freeze_dict(v):
    if isinstance(v, dict):
        return FrozenDict({k: _freeze_dict(val) for k, val in v.items()})
    elif isinstance(v, list):
        return tuple(_freeze_dict(val) for val in v)
    return v

class ProvenanceMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)
    document_id: str
    document_version_id: str
    chunk_id: str
    source_type: str
    source_reference: Optional[str] = None
    step_id: str
    operator_type: OperatorType

class RawRetrievalResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    step_id: str
    vector_id: Optional[str] = None
    graph_node_id: Optional[str] = None
    score: float = Field(default=0.0)
    metadata_hits: Mapping[str, Any] = Field(default_factory=dict)
    
    @field_validator("metadata_hits", mode="after")
    def freeze_metadata(cls, v):
        return _freeze_dict(v)
    
class CandidateEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)
    evidence_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str
    provenance: ProvenanceMetadata
    score: float
    retrieval_metadata: Mapping[str, Any] = Field(default_factory=dict)
    
    @field_validator("retrieval_metadata", mode="after")
    def freeze_metadata(cls, v):
        return _freeze_dict(v)

class ExecutionTrace(BaseModel):
    model_config = ConfigDict(frozen=True)
    step_id: str
    operator_type: OperatorType
    status: ExecutionStatus
    start_time: datetime = Field(default_factory=utc_now)
    end_time: Optional[datetime] = None
    candidates_found: int = 0
    latency_ms: int = 0
    error_message: Optional[str] = None
    retry_count: int = 0

class CandidateEvidenceSet(BaseModel):
    model_config = ConfigDict(frozen=True)
    set_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    plan_id: str
    status: ExecutionStatus
    candidates: Tuple[CandidateEvidence, ...] = Field(default_factory=tuple)
    traces: Tuple[ExecutionTrace, ...] = Field(default_factory=tuple)
    total_latency_ms: int = 0
    fatal_error: Optional[str] = None
    # Operators that make LLM calls populate these so the budget guard in
    # service.py can enforce max_tokens / max_cost limits from the plan.
    tokens_used: int = 0
    cost_used: float = 0.0