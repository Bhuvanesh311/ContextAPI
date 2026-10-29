from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.core.enums import (
    RetrievalRequestStatus,
    RequestSourceType,
    ExecutionProfile,
    QueryIntent,
    QueryComplexity,
)

class ActorModel(BaseModel):
    actor_type: str = Field(..., description="The type of actor (e.g., USER, AGENT, WORKFLOW)")
    actor_id: str = Field(..., description="The unique identity of the actor")

class LifecycleContext(BaseModel):
    request_id: str = Field(..., description="Stable retrieval request identity")
    correlation_id: Optional[str] = Field(None, description="Associates request with broader execution context")
    parent_request_id: Optional[str] = Field(None, description="Request lineage")
    deadline: Optional[datetime] = Field(None, description="Processing deadline")
    cancellation: bool = Field(False, description="Cancellation intent")
    idempotency_key: Optional[str] = Field(None, description="Key for idempotent creation")

class NormalizedRetrievalRequest(BaseModel):
    request_id: str
    source_type: RequestSourceType
    actor: ActorModel
    retrieval_instruction: str
    resource_context: Dict[str, Any] = Field(default_factory=dict)
    execution_context: Dict[str, Any] = Field(default_factory=dict)
    source_metadata: Dict[str, Any] = Field(default_factory=dict)
    lifecycle: LifecycleContext

class RetrievalRequestCreate(BaseModel):
    """
    The external schema for creating a retrieval request.

    project_id must be sent as execution_context.scope.project_id, e.g.:
        {
          "instruction": "What is ContextAPI?",
          "source_type": "USER",
          "actor": {"actor_type": "USER", "actor_id": "ignored-see-router"},
          "execution_context": {"scope": {"project_id": "PROJ000007"}}
        }
    actor/source_type are accepted for schema compatibility but the
    router overwrites them with the authenticated caller's identity, so
    one user can never search another user's data by lying about actor_id.
    """
    instruction: str = Field(..., description="The retrieval requirement (query, objective, or task)")
    source_type: RequestSourceType = RequestSourceType.USER
    actor: Optional[ActorModel] = None
    resource_context: Dict[str, Any] = Field(default_factory=dict)
    execution_context: Dict[str, Any] = Field(default_factory=dict)
    source_metadata: Dict[str, Any] = Field(default_factory=dict)
    lifecycle: Optional[LifecycleContext] = None
    top_k: int = Field(default=5, ge=1, le=20)
    # Execution profile: FAST / STANDARD / DEEP / COLLABORATIVE (default STANDARD).
    profile: Optional[ExecutionProfile] = Field(
        default=None,
        description="How much effort retrieval may spend. L02 decides what each profile may do.",
    )
    # Metadata constraints (document_ids, mime_types, created_after, created_before).
    constraints: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Same as execution_context.constraints.",
    )
    # L04 budget (time, token, cost). Each can only narrow the profile's limits.
    max_latency_ms: Optional[int] = Field(
        default=None, ge=500, le=60_000,
        description="Latency budget for the whole retrieval, in ms (capped by the profile).",
    )
    max_tokens: Optional[int] = Field(
        default=None, ge=1, le=1_000_000,
        description="Token budget for model calls made while retrieving (L03).",
    )
    max_cost: Optional[float] = Field(
        default=None, ge=0.0, le=100.0,
        description="Cost budget (USD) for external model calls made while retrieving.",
    )
    # Shortcut so callers do not have to build execution_context.scope by hand.
    project_id: Optional[str] = Field(
        default=None,
        description="Project to search. Same as execution_context.scope.project_id.",
    )

    # This is the body Swagger pre-fills. Everything else is optional.
    model_config = {
        "json_schema_extra": {
            "example": {
                "instruction": "What is ContextAPI?",
                "project_id": "PROJ000001",
                "profile": "DEEP",
                "top_k": 5,
            }
        }
    }

class RetrievalResultItem(BaseModel):
    rank: int
    document_id: str
    document_name: Optional[str] = None
    chunk_id: str
    content: str
    score: float
    state: str
    matched_by: Optional[str] = None
    round: int = 0

class RetrievalRequestResponse(BaseModel):
    request_id: str
    project_id: Optional[str] = None
    knowledge_base_id: Optional[str] = None
    user_id: Optional[str] = None
    source_type: RequestSourceType
    query: Optional[str] = None
    status: RetrievalRequestStatus
    execution_profile: Optional[ExecutionProfile] = None
    retrieval_plan: Optional[Dict[str, Any]] = None
    results: Optional[List[Dict[str, Any]]] = None
    sufficiency: Optional[Dict[str, Any]] = None
    evidence_package: Optional[Dict[str, Any]] = None
    generated_answer: Optional[Dict[str, Any]] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }

class AnswerSource(BaseModel):
    citation: Optional[int] = None
    document_id: Optional[str] = None
    document_name: Optional[str] = None
    score: Optional[float] = None
    snippet: Optional[str] = None


class RetrievalAnswerResponse(BaseModel):
    """Short view of a retrieval request: the answer and where it came from."""
    request_id: str
    status: RetrievalRequestStatus
    done: bool = Field(description="False while the request is still PENDING/RUNNING; call again.")
    project_id: Optional[str] = None
    question: Optional[str] = None
    profile: Optional[ExecutionProfile] = None
    answer: Optional[str] = None
    answer_status: Optional[str] = Field(default=None, description="SUCCESS / PARTIAL / FAILED / skipped")
    model_tier: Optional[str] = Field(default=None, description="B = local Ollama, C = external LLM")
    grounding_score: Optional[float] = None
    # How well the project's documents cover the question, once done:
    # "relevant" | "partial" | "not_relevant" | "no_documents", with a
    # message to show the user (None when relevant or still running).
    relevance: Optional[str] = None
    notice: Optional[str] = None
    # While the request runs: "indexing" | "searching" | "writing", and the
    # answer text generated so far (not yet validated; replaced by `answer`).
    stage: Optional[str] = None
    partial_answer: Optional[str] = None
    cited_sources: List[AnswerSource] = Field(default_factory=list)
    top_results: List[AnswerSource] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    error_code: Optional[str] = None
    error_message: Optional[str] = None
