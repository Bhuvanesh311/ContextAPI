from datetime import datetime, timezone


def _utcnow() -> datetime:
    """Naive UTC datetime for SQLAlchemy DateTime (no timezone) columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

from sqlalchemy import (
    String,
    Integer,
    Numeric,
    DateTime,
    Boolean,
    Text,
    JSON,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy import Enum as SqlEnum

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.core.database import Base
from app.core.enums import (
    RetrievalRequestStatus,
    RequestSourceType,
    ExecutionProfile,
    QueryIntent,
    QueryComplexity,
)

class RetrievalRequest(Base):
    __tablename__ = "retrieval_requests"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_retrieval_requests_user_idempotency_key"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    request_id: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        index=True,
        nullable=False,
    )

    # Unique per user (see __table_args__): one user's key must never block
    # or collide with another user's.
    idempotency_key: Mapped[str | None] = mapped_column(
        String(255),
        index=True,
        nullable=True,
    )

    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.project_id"),
        nullable=True,
        index=True,
    )

    knowledge_base_id: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        index=True,
    )

    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.user_id"),
        nullable=True,
        index=True,
    )

    source_type: Mapped[RequestSourceType] = mapped_column(
        SqlEnum(RequestSourceType),
        nullable=False,
    )

    source_reference: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    query: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    objective: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    scope: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    constraints: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    execution_profile: Mapped[ExecutionProfile | None] = mapped_column(
        SqlEnum(ExecutionProfile),
        nullable=True,
    )

    normalized_query: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    resolved_objective: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    intent: Mapped[QueryIntent | None] = mapped_column(
        SqlEnum(QueryIntent),
        nullable=True,
    )

    complexity: Mapped[QueryComplexity | None] = mapped_column(
        SqlEnum(QueryComplexity),
        nullable=True,
    )

    ambiguity_score: Mapped[float | None] = mapped_column(
        Numeric,
        nullable=True,
    )

    confidence_score: Mapped[float | None] = mapped_column(
        Numeric,
        nullable=True,
    )

    requires_decomposition: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    requires_relationship_search: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    requires_multi_hop: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    analysis_method: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    analysis_model: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    analysis_metadata: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    query_safety_outcome: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    query_safety_risk_level: Mapped[float | None] = mapped_column(
        Numeric,
        nullable=True,
    )

    memory_requirement: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    retrieval_plan: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    # NEW: the actual search results (list of dicts). Nothing wrote to a
    # results field before this, so GET /{request_id} always returned an
    # empty/absent result set even when a search technically "ran".
    results: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
    )
    
    # L07: was the evidence enough? verdict, score, gaps, and every
    # escalation round that ran (see app/retrieval/sufficiency/models.py).
    sufficiency: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    # EvidencePackage handed to the augmentation domain (L08+)
    evidence_package: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    # L08-L11 augmentation output: GeneratedAnswer (set when profile allows LLM)
    generated_answer: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    max_latency_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    max_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    max_cost: Mapped[float | None] = mapped_column(
        Numeric,
        nullable=True,
    )

    max_model_calls: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    max_rounds: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    current_round: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    status: Mapped[RetrievalRequestStatus] = mapped_column(
        SqlEnum(RetrievalRequestStatus),
        nullable=False,
        default=RetrievalRequestStatus.PENDING,
    )

    error_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    error_details: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=_utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

Index(
    "idx_retrieval_request_status",
    RetrievalRequest.status,
)

Index(
    "idx_retrieval_request_project",
    RetrievalRequest.project_id,
)

Index(
    "idx_retrieval_request_user",
    RetrievalRequest.user_id,
)