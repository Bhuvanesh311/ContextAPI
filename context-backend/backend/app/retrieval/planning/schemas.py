
from typing import List, Dict, Any, Optional, Set, Tuple, Mapping
from pydantic import BaseModel, Field, ConfigDict, field_validator
import uuid

from app.core.enums import RetrievalRequirementType

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

class ExecutionLimits(BaseModel):
    model_config = ConfigDict(frozen=True)
    max_steps: int = Field(default=5, ge=1)
    max_parallelism: int = Field(default=3, ge=1)
    max_query_variants: int = Field(default=3, ge=1)
    max_subqueries: int = Field(default=5, ge=1)
    max_rounds: int = Field(default=3, ge=1)
    max_latency_ms: int = Field(default=10000, ge=0)
    # Per-request caller-supplied caps (None = no extra limit beyond profile).
    # service.py reads these from the DB row and passes them to the planner.
    max_tokens: Optional[int] = Field(default=None, ge=1)
    max_cost: Optional[float] = Field(default=None, ge=0.0)

class StopConditions(BaseModel):
    model_config = ConfigDict(frozen=True)
    sufficient_evidence: bool = Field(default=True)
    max_rounds_reached: bool = Field(default=True)
    deadline_exceeded: bool = Field(default=True)
    budget_exhausted: bool = Field(default=True)

class FallbackPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)
    strategy_id: str
    max_attempts: int = Field(default=1, ge=0)
    fallback_capabilities: Tuple[str, ...] = Field(default_factory=tuple)

class CapabilityDescriptor(BaseModel):
    model_config = ConfigDict(frozen=True)
    capability_id: str
    capability_type: RetrievalRequirementType
    is_available: bool = Field(default=True)
    supported_constraints: Tuple[str, ...] = Field(default_factory=tuple)
    version: str = Field(default="1.0.0")

class QueryBinding(BaseModel):
    model_config = ConfigDict(frozen=True)
    binding_type: str = Field(..., description="e.g., original, normalized, subquery, structured")
    query_text: str
    subquery_id: Optional[str] = None

class RetrievalStep(BaseModel):
    model_config = ConfigDict(frozen=True)
    step_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    capability_id: str
    query_binding: QueryBinding
    step_scope: Mapping[str, Any] = Field(..., description="Must be <= L02 effective_scope")
    depends_on: Tuple[str, ...] = Field(default_factory=tuple)
    
    @field_validator("step_scope", mode="after")
    def freeze_scope(cls, v):
        return _freeze_dict(v)

class ExecutionGraph(BaseModel):
    model_config = ConfigDict(frozen=True)
    steps: Tuple[RetrievalStep, ...] = Field(default_factory=tuple)
    
class RetrievalPlan(BaseModel):
    model_config = ConfigDict(frozen=True)
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str
    correlation_id: str
    plan_version: str = Field(default="1.0.0")
    
    effective_scope: Mapping[str, Any]
    planning_summary: str
    
    graph: ExecutionGraph
    execution_limits: ExecutionLimits
    stop_conditions: StopConditions
    fallback_policy: Optional[FallbackPolicy] = None
    validation_metadata: Mapping[str, Any] = Field(default_factory=dict)
    
    @field_validator("effective_scope", "validation_metadata", mode="after")
    def freeze_mapping(cls, v):
        return _freeze_dict(v)
