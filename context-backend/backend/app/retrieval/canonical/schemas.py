from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, ConfigDict

from app.core.enums import ExecutionProfile, RequestSourceType
from app.retrieval.schemas import ActorModel, LifecycleContext


class RetrievalContract(BaseModel):
    """
    The established canonical contract for a retrieval request.
    This is passed from L01 -> L02 and must contain only semantically valid,
    structurally verified data. Must be immutable.
    """
    model_config = ConfigDict(frozen=True)

    request_id: str = Field(..., description="Stable retrieval request identity")
    query: str = Field(..., description="Canonicalized retrieval instruction/query")
    source_type: RequestSourceType = Field(..., description="The origination context")
    actor: ActorModel = Field(..., description="The verified or explicit actor information")

    resource_context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Preserved contextual resource information"
    )
    scope: Dict[str, Any] = Field(
        default_factory=dict,
        description="Requested scope. This is NOT effective authorized scope."
    )
    constraints: Dict[str, Any] = Field(
        default_factory=dict,
        description="Caller-provided restrictions and constraints (validated)"
    )
    profile: ExecutionProfile = Field(
        default=ExecutionProfile.STANDARD,
        description="Requested execution profile. L02 decides what it may do."
    )
    execution_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata related to execution"
    )
    lifecycle: LifecycleContext = Field(..., description="Lifecycle and reliability context")
    request_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Source metadata or upstream lineage"
    )