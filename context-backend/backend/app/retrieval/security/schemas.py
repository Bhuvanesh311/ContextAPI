from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.core.enums import ExecutionProfile
from app.retrieval.security.enums import AuthorizationDecision
from app.retrieval.security.profiles import ProfileControls, controls_for
from app.retrieval.canonical.schemas import RetrievalContract


class ScopedDocument(BaseModel):
    """One document L02 allows this request to search."""
    document_id: str
    name: str
    document_version_id: str
    updated_at: Optional[datetime] = None
    is_current: bool = True


class ScopedRetrievalContract(BaseModel):
    """
    The output of L02: Security & Scope Resolution.
    Downstream layers consume this to guarantee retrieval occurs strictly
    within authorized boundaries.
    """
    request: RetrievalContract

    security_context: Dict[str, Any] = Field(default_factory=dict)

    permitted_scope: Dict[str, Any] = Field(default_factory=dict)
    requested_scope: Dict[str, Any] = Field(default_factory=dict)
    effective_scope: Dict[str, Any] = Field(default_factory=dict)
    denied_scope: Dict[str, Any] = Field(default_factory=dict)

    decision: AuthorizationDecision
    decision_metadata: Dict[str, Any] = Field(default_factory=dict)

    # Execution profile (FAST / STANDARD / DEEP / COLLABORATIVE) and what it allows.
    profile: ExecutionProfile = ExecutionProfile.STANDARD
    controls: ProfileControls = Field(default_factory=lambda: controls_for(ExecutionProfile.STANDARD))

    # Documents (current versions) this request may search, after project
    # isolation and the caller's metadata constraints were applied.
    documents: List[ScopedDocument] = Field(default_factory=list)
    applied_constraints: Dict[str, Any] = Field(default_factory=dict)