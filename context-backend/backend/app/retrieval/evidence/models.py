from typing import List, Dict, Any, Optional, Tuple, Mapping
from pydantic import BaseModel, Field, ConfigDict, field_validator
import uuid
from app.core.identifiers import generate_offline_id

from app.retrieval.engine.schemas import CandidateEvidence, ProvenanceMetadata, _freeze_dict
from app.retrieval.evidence.enums import EvidenceState

class EvidenceEvaluationTrace(BaseModel):
    model_config = ConfigDict(frozen=True)
    evaluator_name: str
    signal_type: str
    signal_value: Any
    reason: str
    latency_ms: int = 0

from enum import Enum

class RelationshipType(str, Enum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    DUPLICATES = "DUPLICATES"
    RELATED = "RELATED"
    UNKNOWN = "UNKNOWN"

class EvidenceRelationship(BaseModel):
    model_config = ConfigDict(frozen=True)
    target_evidence_id: str
    relation_type: RelationshipType
    reason: Optional[str] = None

class ValidatedEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)
    evidence_id: str
    candidate: CandidateEvidence
    state: EvidenceState
    primary_reason: str
    evaluation_traces: Tuple[EvidenceEvaluationTrace, ...] = Field(default_factory=tuple)
    relationships: Tuple[EvidenceRelationship, ...] = Field(default_factory=tuple)

class ValidatedEvidenceSet(BaseModel):
    model_config = ConfigDict(frozen=True)
    set_id: str = Field(default_factory=lambda: generate_offline_id("EVA-SET"))
    plan_id: str
    original_candidates_count: int
    unevaluated_count: int = Field(default=0, ge=0)
    validated_evidence: Tuple[ValidatedEvidence, ...] = Field(default_factory=tuple)

