
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict

from app.core.enums import (
    QueryIntent,
    QueryComplexity,
    QuerySafetyOutcome,
    MemoryRequirement,
    RetrievalRequirementType,
    AnalysisMethod,
)
from app.retrieval.security.schemas import ScopedRetrievalContract

class ObjectIntelligence(BaseModel):
    model_config = ConfigDict(frozen=True)
    entities: List[str] = Field(default_factory=list, description="Extracted entities")
    identifiers: List[str] = Field(default_factory=list, description="Extracted standard identifiers (UUIDs, IDs)")
    temporal_references: List[str] = Field(default_factory=list, description="Dates, times, or relative periods")
    relationships: List[str] = Field(default_factory=list, description="Detected relational hints")

class QueryIntelligence(BaseModel):
    model_config = ConfigDict(frozen=True)
    intent: QueryIntent = Field(default=QueryIntent.UNKNOWN)
    complexity: QueryComplexity = Field(default=QueryComplexity.LOW)
    ambiguity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    retrieval_requirements: List[RetrievalRequirementType] = Field(default_factory=list)

class QuerySafetyAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)
    outcome: QuerySafetyOutcome = Field(default=QuerySafetyOutcome.SAFE)
    risk_level: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reasons: List[str] = Field(default_factory=list)
    categories: List[str] = Field(default_factory=list)

class Subquery(BaseModel):
    model_config = ConfigDict(frozen=True)
    parent_request_id: str
    query: str
    purpose: str

class DecompositionResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    is_decomposed: bool = False
    subqueries: List[Subquery] = Field(default_factory=list)

class QueryAnalysisResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    request: ScopedRetrievalContract = Field(..., description="The L02 boundaries preserved exactly")
    
    original_query: Optional[str] = Field(None)
    normalized_query: Optional[str] = Field(None)
    resolved_objective: Optional[str] = Field(None)
    
    object_signals: ObjectIntelligence = Field(default_factory=ObjectIntelligence)
    query_intelligence: QueryIntelligence = Field(default_factory=QueryIntelligence)
    memory_requirement: MemoryRequirement = Field(default=MemoryRequirement.NONE)
    query_safety: QuerySafetyAssessment = Field(default_factory=QuerySafetyAssessment)
    decomposition: DecompositionResult = Field(default_factory=DecompositionResult)
    
    analysis_method: AnalysisMethod = Field(default=AnalysisMethod.DETERMINISTIC)
    analysis_metadata: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    
    # LLM usage (Tier B/C calls only; 0 for pure Tier A deterministic analysis).
    # service.py uses these to pre-charge the per-request budget before L05 runs.
    llm_tokens_used: int = Field(default=0, ge=0)
    llm_cost_used: float = Field(default=0.0, ge=0.0)

    # Traceability
    analyzer_trace: List[str] = Field(default_factory=list)
