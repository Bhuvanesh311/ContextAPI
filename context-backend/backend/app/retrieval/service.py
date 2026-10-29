"""
Runs a retrieval request end-to-end inside the Celery worker
(app/retrieval/tasks.py). The HTTP handler only persists PENDING and enqueues.

    L02 security -> L03 intelligence -> L04 planning
        -> L05 execution -> L06 evidence -> L07 sufficiency (loop)
        -> L08-L11 augmentation (DEEP / COLLABORATIVE only)

L05 + L06 + L07 run inside ProgressiveRetrievalController: after every round
L07 judges whether the evidence answers the question. If not, it escalates
(deeper search, gap-focused query, sub-question search, ...) within the
limits in SufficiencyConfig, and never outside the L02 scope.

L08-L11 (augmentation) run after retrieval completes.  Only profiles with
allow_llm=True (DEEP, COLLABORATIVE) call the LLM; FAST/STANDARD skip and
return evidence chunks only.

State: RUNNING is claimed with a conditional update, and the row is committed
before the L05-L07 loop so pollers see progress and cancel calls aren't
blocked by a row lock. Cancellation is checked between rounds; the task does a
final locked check before committing results.

NOTE on scope: ChromaDB's stored metadata (see
app/knowledge/processing/stages/vector_indexing.py) has no project_id, only
document_id / document_version_id. So the security layer's "effective_scope"
(project_id) is translated here into a document_version_id "$in" filter that
both Chroma and the Postgres lexical search understand.

Capabilities (see bootstrap.py): SEMANTIC (Chroma + bge-m3), LEXICAL
(Postgres full-text) and HYBRID (both, fused with RRF).
"""

import logging
import time
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import (
    DocumentStatus,
    IngestionRunStatus,
    KnowledgeProcessingRunStatus,
    RetrievalRequestStatus,
    RetrievalRequirementType,
)
from app.knowledge.uploads.models import Document, IngestionRun, KnowledgeProcessingRun
from app.retrieval.canonical.schemas import RetrievalContract
from app.retrieval.models import RetrievalRequest

from app.retrieval.security.resolver import resolve_security_context
from app.retrieval.security.enums import AuthorizationDecision

from app.retrieval.intelligence.aggregate import analyze_request
from app.core.enums import QuerySafetyOutcome

from app.retrieval.planning.planner import L04Planner
from app.retrieval.planning.schemas import ExecutionLimits
from app.retrieval.planning.exceptions import L04PlanningError

from app.retrieval.engine.executor import EngineExecutor
from app.retrieval.engine.operators.semantic import SemanticOperator
from app.retrieval.engine.adapters.embedding import BGEM3EmbeddingAdapter
from app.retrieval.engine.adapters.vector_store import ChromaVectorStoreAdapter
from app.retrieval.engine.postgres_resolution import PostgresContentResolver

from app.retrieval.evidence.service import EvidenceIntelligenceService, EvidenceIntelligenceConfig
from app.retrieval.evidence.policy import EvidencePolicy
from app.retrieval.evidence.enums import EvidenceState
from app.retrieval.evidence.evaluators.deterministic import DeterministicValidator
from app.retrieval.evidence.evaluators.similarity import SimilarityEvaluator
from app.retrieval.evidence.package import build_evidence_package
from app.retrieval.evidence.evaluators.pairwise import TokenJaccardPairwiseEvaluator
from app.retrieval.evidence.evaluators.integrity import (
    AuthorityFreshnessEvaluator,
    ProvenanceEvaluator,
    QualityEvaluator,
    RelevanceEvaluator,
    ScopeDefenseEvaluator,
)

from app.retrieval.engine.operators.lexical import LexicalOperator
from app.retrieval.engine.operators.hybrid import HybridOperator
from app.retrieval.engine.operators.structured import StructuredOperator
from app.retrieval.engine.adapters.lexical_store import PostgresLexicalStoreAdapter
from app.retrieval.engine.adapters.structured_store import PostgresStructuredStoreAdapter
from app.retrieval.engine.reranker import BGEReranker
from app.retrieval.engine.exceptions import ScopeViolationError

from app.retrieval.sufficiency import (
    ProgressiveRetrievalController,
    StopReason,
    SufficiencyConfig,
    SufficiencyQuery,
    SufficiencyReport,
    SufficiencyVerdict,
)

from app.augmentation.service import run_augmentation
from app.retrieval import progress
from app.augmentation.schemas import GeneratedAnswer, GenerationStatus
from app.augmentation.memory.service import load_memory, write_turn, write_evidence_chunks

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("app.retrieval.audit")

_EXISTENCE_REVEALING_REASONS = frozenset({
    "USER_NOT_FOUND",
    "PROJECT_NOT_FOUND",
    "TENANT_NOT_ASSIGNED",
    "TENANT_MISMATCH",
    "UNAUTHORIZED_PROJECT_ACCESS",
})

_DENY_MESSAGES = {
    "PROJECT_NOT_ACTIVE": "This project is not active. Set its status to active to search it.",
    "MISSING_REQUESTED_SCOPE": "A project_id is required.",
    "KNOWLEDGE_BASE_SCOPE_UNSUPPORTED": "Searching by knowledge_base_id is not supported; use project_id.",
}

# Every L07 threshold and limit lives in this one object.

SUFFICIENCY_CONFIG = SufficiencyConfig(allow_top_k_growth=False, partial_status_on_gaps=True)

# Share of the request latency budget L03 may spend (LLM tiers B + C together).
L03_BUDGET_SHARE = 0.2

# ---------------------------------------------------------------------------
# Module-level singletons — built once, shared across all requests.
# SemanticOperator holds the Chroma client + BGE-M3 adapter (no per-request
# state). EvidenceIntelligenceService and its evaluators are stateless.
# DB-bound objects (LexicalOperator, HybridOperator, resolver) must still be
# created per-request because they hold a live SQLAlchemy Session.
# ---------------------------------------------------------------------------
_semantic_operator: "SemanticOperator | None" = None
_evidence_service:  "EvidenceIntelligenceService | None" = None
_rerankers:         "dict[int, BGEReranker]" = {}


def _get_semantic_operator() -> "SemanticOperator":
    global _semantic_operator
    if _semantic_operator is None:
        _semantic_operator = SemanticOperator(
            embedding_adapter=BGEM3EmbeddingAdapter(),
            vector_adapter=ChromaVectorStoreAdapter(collection_name="knowledge"),
        )
    return _semantic_operator


def _get_evidence_service() -> "EvidenceIntelligenceService":
    global _evidence_service
    if _evidence_service is None:
        _evaluators = [
            DeterministicValidator(),
            ScopeDefenseEvaluator(),
            ProvenanceEvaluator(),
            QualityEvaluator(),
            AuthorityFreshnessEvaluator(),
            SimilarityEvaluator(),
            RelevanceEvaluator(),
        ]
        _evidence_service = EvidenceIntelligenceService(
            evaluators=_evaluators,
            policy=EvidencePolicy(),
            config=EvidenceIntelligenceConfig(
                max_evaluator_calls_per_candidate=len(_evaluators),
                exact_deduplication_only=False,
            ),
            semantic_evaluator=TokenJaccardPairwiseEvaluator(),
        )
    return _evidence_service


def _get_reranker(max_candidates: int) -> "BGEReranker":
    if max_candidates not in _rerankers:
        _rerankers[max_candidates] = BGEReranker(max_candidates=max_candidates)
    return _rerankers[max_candidates]


class _StageError(Exception):
    """An L05/L06 failure that keeps its error code for the API response."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


_ACTIVE_STATUSES = (RetrievalRequestStatus.PENDING, RetrievalRequestStatus.RUNNING)


def cancel_if_active(db: Session, request_pk: int) -> bool:
    """Cancel only PENDING/RUNNING rows, so a finished request stays terminal."""
    rows = (
        db.query(RetrievalRequest)
        .filter(RetrievalRequest.id == request_pk, RetrievalRequest.status.in_(_ACTIVE_STATUSES))
        .update(
            {"status": RetrievalRequestStatus.CANCELLED, "cancelled_at": datetime.now(timezone.utc)},
            synchronize_session=False,
        )
    )
    db.commit()
    return bool(rows)


def fail_stale_requests(
    db: Session,
    pending_older_than_s: int = 600,
    running_older_than_s: int = 900,
) -> int:
    """
    Fail requests no worker will finish: PENDING too long (message lost or
    queue down) or RUNNING too long (worker died mid-run). Conditional
    updates, so a request that completes concurrently is left alone.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    failed = 0
    for status, column, age, code in (
        (RetrievalRequestStatus.PENDING, RetrievalRequest.created_at, pending_older_than_s, "QUEUE_TIMEOUT"),
        (RetrievalRequestStatus.RUNNING, RetrievalRequest.started_at, running_older_than_s, "WORKER_LOST"),
    ):
        failed += (
            db.query(RetrievalRequest)
            .filter(
                RetrievalRequest.status == status,
                column < now - timedelta(seconds=age),
            )
            .update(
                {
                    "status": RetrievalRequestStatus.FAILED,
                    "error_code": code,
                    "error_message": "The request was not processed in time. Please retry.",
                    "completed_at": now,
                },
                synchronize_session=False,
            )
        )
    db.commit()
    return failed


def commit_unless_cancelled(db: Session, db_request: RetrievalRequest) -> bool:
    """
    Final write of a worker run. The row is locked first: a cancel committed
    after the last round check wins (pending results are discarded), and a
    cancel arriving now waits for this commit and then finds a terminal row.
    """
    with db.no_autoflush:
        current = (
            db.query(RetrievalRequest.status)
            .filter(RetrievalRequest.id == db_request.id)
            .with_for_update()
            .scalar()
        )
    if current == RetrievalRequestStatus.CANCELLED:
        db.rollback()
        return False
    db.commit()
    return True


def _current_status(db: Session, db_request: RetrievalRequest) -> RetrievalRequestStatus | None:
    with db.no_autoflush:
        return (
            db.query(RetrievalRequest.status)
            .filter(RetrievalRequest.id == db_request.id)
            .scalar()
        )


def _fail(db_request: RetrievalRequest, error_code: str, message: str) -> None:
    db_request.status = RetrievalRequestStatus.FAILED
    db_request.error_code = error_code
    db_request.error_message = message
    db_request.completed_at = datetime.now(timezone.utc)


def _remaining_ms(deadline: datetime | None) -> int | None:
    """Milliseconds until the caller's deadline (None = no deadline)."""
    if deadline is None:
        return None
    now = datetime.now(timezone.utc) if deadline.tzinfo else datetime.now(timezone.utc)
    return int((deadline - now).total_seconds() * 1000)


def _complete_empty(db_request: RetrievalRequest, report: SufficiencyReport | None = None) -> None:
    db_request.status = RetrievalRequestStatus.COMPLETED
    db_request.results = []
    if report is not None:
        db_request.sufficiency = report.model_dump(mode="json")
    db_request.completed_at = datetime.now(timezone.utc)


def _version_info(db: Session, rows) -> Dict[str, Dict[str, Any]]:
    """
    Fresh state of every document in scope, read at L06 time (not at L02
    time), so a document archived or re-versioned in between is noticed.
    """
    doc_ids = [r.document_id for r in rows]
    fresh = {
        d.document_id: d
        for d in db.query(
            Document.document_id,
            Document.status,
            Document.current_version_id,
            Document.updated_at,
        )
        .filter(Document.document_id.in_(doc_ids))
        .all()
    } if doc_ids else {}
    info: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        d = fresh.get(r.document_id)
        info[r.current_version_id] = {
            "name": r.name,
            "document_active": bool(d and d.status == DocumentStatus.ACTIVE),
            "is_current": bool(d and d.current_version_id == r.current_version_id),
            "updated_at": d.updated_at if d else None,
        }
    return info


_RUNNING_INGESTION = (IngestionRunStatus.PENDING, IngestionRunStatus.RUNNING, IngestionRunStatus.RETRYING)
_RUNNING_PROCESSING = (
    KnowledgeProcessingRunStatus.PENDING,
    KnowledgeProcessingRunStatus.RUNNING,
    KnowledgeProcessingRunStatus.RETRYING,
)


def _documents_still_indexing(db: Session, project_id: str) -> int:
    """Active documents of the project that are still being parsed or embedded."""
    project_docs = (Document.project_id == project_id, Document.status == DocumentStatus.ACTIVE)
    ingesting = (
        db.query(IngestionRun.document_id)
        .join(Document, Document.document_id == IngestionRun.document_id)
        .filter(*project_docs, IngestionRun.status.in_(_RUNNING_INGESTION))
        .distinct()
        .count()
    )
    embedding = (
        db.query(KnowledgeProcessingRun.document_version_id)
        .join(Document, Document.current_version_id == KnowledgeProcessingRun.document_version_id)
        .filter(*project_docs, KnowledgeProcessingRun.status.in_(_RUNNING_PROCESSING))
        .distinct()
        .count()
    )
    return ingesting + embedding


def _wait_for_indexing(
    db: Session, project_id: str | None, request_pk: int, request_id: str | None = None,
) -> int:
    """
    A question asked right after an upload would otherwise search without the
    new document. Wait (bounded) until the project has nothing left to index.
    Returns how many documents were still indexing when the wait ended.
    """
    if not project_id:
        return 0
    deadline = time.monotonic() + max(0, settings.RETRIEVAL_INDEXING_WAIT_SECONDS)
    announced = False
    while True:
        try:
            pending = _documents_still_indexing(db, project_id)
            status = db.query(RetrievalRequest.status).filter(RetrievalRequest.id == request_pk).scalar()
        except Exception:
            logger.exception("Indexing check failed for project %s", project_id)
            db.rollback()
            return 0
        db.rollback()  # end the read transaction so the next poll sees new commits
        if pending == 0 or status not in _ACTIVE_STATUSES or time.monotonic() >= deadline:
            if pending:
                logger.warning("Searching project %s while %d document(s) are still indexing", project_id, pending)
            return pending
        if request_id and not announced:
            progress.set_stage(request_id, progress.STAGE_INDEXING)
            announced = True
        time.sleep(1)


def run_retrieval(
    db: Session,
    db_request: RetrievalRequest,
    canonical: RetrievalContract,
    top_k: int = 5,
) -> None:
    started_monotonic = time.monotonic()

    # Conditional transition: a cancel that lands before the worker starts must
    # not be overwritten with RUNNING.
    claimed = (
        db.query(RetrievalRequest)
        .filter(
            RetrievalRequest.id == db_request.id,
            RetrievalRequest.status.in_(_ACTIVE_STATUSES),
        )
        .update(
            {"status": RetrievalRequestStatus.RUNNING, "started_at": datetime.now(timezone.utc)},
            synchronize_session=False,
        )
    )
    db.commit()
    if not claimed:
        return

    # ---- L01 lifecycle: cancellation and deadline ----------------------
    if canonical.lifecycle.cancellation:
        db_request.status = RetrievalRequestStatus.CANCELLED
        db_request.completed_at = datetime.now(timezone.utc)
        return
    progress.set_stage(db_request.request_id, progress.STAGE_SEARCHING)
    still_indexing = _wait_for_indexing(
        db, (canonical.scope or {}).get("project_id"), db_request.id, db_request.request_id,
    )
    if _current_status(db, db_request) == RetrievalRequestStatus.CANCELLED:
        return
    progress.set_stage(db_request.request_id, progress.STAGE_SEARCHING)
    # Time spent waiting for indexing is not part of the retrieval budget.
    started_monotonic = time.monotonic()

    deadline_ms = _remaining_ms(canonical.lifecycle.deadline)
    if deadline_ms is not None and deadline_ms <= 0:
        _fail(db_request, "DEADLINE_EXCEEDED", "The request deadline has already passed.")
        return
    budget_ms = 60000 if deadline_ms is None else max(1, min(60000, deadline_ms))

    # ---- L02: security & scope resolution ----------------------------
    try:
        security_context = resolve_security_context(canonical, db)
    except Exception:
        logger.exception("L02 security resolution failed for %s", db_request.request_id)
        _fail(db_request, "SECURITY_RESOLUTION_ERROR", "Security check could not be completed.")
        return

    reason = security_context.decision_metadata.get("reason_code", "DENIED")
    denied = security_context.decision in (
        AuthorizationDecision.DENY,
        AuthorizationDecision.SECURITY_BLOCKED,
    )
    audit_logger.log(
        logging.WARNING if denied else logging.INFO,
        "retrieval_access request_id=%s user_id=%s source=%s project_id=%s decision=%s reason=%s documents=%s",
        db_request.request_id,
        canonical.actor.actor_id,
        canonical.source_type.value,
        canonical.scope.get("project_id"),
        security_context.decision.value,
        reason,
        security_context.decision_metadata.get("documents_in_scope"),
    )
    if denied:
        code = reason.split(":")[0]
        if code in _EXISTENCE_REVEALING_REASONS:
            # One answer for "no such project" and "not yours": sequential
            # project ids must not be enumerable. The real reason is audited above.
            _fail(db_request, "PROJECT_NOT_FOUND_OR_DENIED", "Project not found or access denied.")
        else:
            _fail(db_request, code, _DENY_MESSAGES.get(code, f"Request rejected: {reason}"))
        return

    db_request.project_id = security_context.permitted_scope.get("project_id")

    if "document_version_id" not in security_context.effective_scope:
        _fail(
            db_request,
            "UNSUPPORTED_SCOPE",
            "Only project-scoped search (execution_context.scope.project_id) is supported right now.",
        )
        return

    # ---- L02 output: profile controls + the documents this request may search
    controls = security_context.controls
    top_k = max(1, min(top_k, controls.max_top_k))
    budget_ms = max(1, min(budget_ms, controls.max_latency_ms))
    if db_request.max_latency_ms:
        budget_ms = max(1, min(budget_ms, db_request.max_latency_ms))
    # Per-call L5 timeouts are capped by the time left in this budget.
    call_deadline = started_monotonic + budget_ms / 1000
    rounds_limit = max(1, min(SUFFICIENCY_CONFIG.max_rounds, controls.max_rounds))

    # L02 already applied project isolation and the caller's constraints, so
    # nothing is re-queried here. The effective scope is the document_version_id
    # "$in" filter that reaches ChromaDB, Postgres lexical search and L06.
    rows = [
        SimpleNamespace(document_id=d.document_id, name=d.name, current_version_id=d.document_version_id)
        for d in security_context.documents
    ]

    scope_truncated = bool(security_context.decision_metadata.get("scope_truncated"))
    if scope_truncated:
        logger.warning("Scope truncated to %d documents for %s", len(rows), db_request.request_id)

    if not rows and still_indexing:
        # Not an empty answer: the uploaded documents just aren't searchable yet.
        _fail(
            db_request,
            "DOCUMENTS_STILL_INDEXING",
            f"{still_indexing} document(s) in this project are still being processed. "
            "Please ask again in a few minutes.",
        )
        return

    if not rows:
        _complete_empty(
            db_request,
            SufficiencyReport.empty(
                StopReason.NO_SEARCHABLE_DOCUMENTS,
                "No active documents match this request's project and constraints.",
            ),
        )
        return

    # Reranker: fetched from the module-level cache (lazy model load on first
    # rerank call, then reused across requests for the same max_candidates).
    reranker = _get_reranker(controls.max_candidates) if controls.allow_rerank else None

    version_to_document: Dict[str, tuple[str, str]] = {
        row.current_version_id: (row.document_id, row.name) for row in rows
    }

    # ---- L03: intelligence (deterministic, no LLM call) ---------------
    try:
        l03_result = analyze_request(
            security_context,
            max_tokens=db_request.max_tokens or None,
            max_cost=float(db_request.max_cost) if db_request.max_cost is not None else None,
            # L03 (incl. any LLM tier) gets a fixed share of the budget.
            time_budget_s=max(1.0, budget_ms / 1000 * L03_BUDGET_SHARE),
        )
    except Exception as exc:
        _fail(db_request, "INTELLIGENCE_ERROR", str(exc)[:500])
        return

    db_request.normalized_query = l03_result.normalized_query
    db_request.resolved_objective = l03_result.resolved_objective
    db_request.intent = l03_result.query_intelligence.intent
    db_request.complexity = l03_result.query_intelligence.complexity
    db_request.ambiguity_score = l03_result.query_intelligence.ambiguity_score
    db_request.confidence_score = l03_result.confidence
    db_request.memory_requirement = l03_result.memory_requirement.value
    db_request.query_safety_outcome = l03_result.query_safety.outcome.value
    db_request.query_safety_risk_level = l03_result.query_safety.risk_level
    db_request.analysis_method = l03_result.analysis_method.value
    db_request.requires_decomposition = l03_result.decomposition.is_decomposed

    if l03_result.query_safety.outcome == QuerySafetyOutcome.BLOCKED:
        _fail(
            db_request,
            "QUERY_SAFETY_BLOCKED",
            "; ".join(l03_result.query_safety.reasons) or "Query blocked by safety check.",
        )
        return

    # SEMANTIC alone misses lexical (Postgres FTS) and RRF fusion — upgrade to HYBRID.
    # RELATIONAL (Neo4j) is not yet deployed — fall back to HYBRID.
    # EXACT maps to cap_structured (Postgres phrase exact-match).
    # LEXICAL and HYBRID pass through unchanged.
    _REQUIREMENT_MAP = {
        RetrievalRequirementType.SEMANTIC: RetrievalRequirementType.HYBRID,
        RetrievalRequirementType.RELATIONAL: RetrievalRequirementType.HYBRID,
    }
    adjusted_reqs = list(dict.fromkeys(
        _REQUIREMENT_MAP.get(r, r)
        for r in l03_result.query_intelligence.retrieval_requirements
    ))
    l03_result = l03_result.model_copy(
        update={
            "query_intelligence": l03_result.query_intelligence.model_copy(
                update={"retrieval_requirements": adjusted_reqs}
            )
        }
    )

    # ---- L04: planning --------------------------------------------------
    try:
        planner = L04Planner(
            execution_limits=ExecutionLimits(
                max_latency_ms=budget_ms,
                max_rounds=rounds_limit,
                max_steps=controls.max_steps,
                max_subqueries=controls.max_subqueries,
                # Carry caller-supplied token / cost caps into the plan so
                # downstream layers (L03 LLM calls) can respect them.
                max_tokens=db_request.max_tokens or None,
                max_cost=float(db_request.max_cost) if db_request.max_cost is not None else None,
            )
        )
        plan = planner.plan(l03_result)
    except L04PlanningError as exc:
        _fail(db_request, "PLANNING_ERROR", str(exc)[:500])
        return

    db_request.retrieval_plan = {
        "plan_id": plan.plan_id,
        "steps": len(plan.graph.steps),
        "summary": plan.planning_summary,
        "profile": controls.profile.value,
        "documents_in_scope": len(rows),
        "scope_truncated": scope_truncated,
        "budget": {
            "latency_ms": budget_ms,
            "max_rounds": rounds_limit,
            "max_steps": controls.max_steps,
            "max_tokens": db_request.max_tokens,
            "max_cost": float(db_request.max_cost) if db_request.max_cost is not None else None,
        },
    }

    if not plan.graph.steps:
        _complete_empty(db_request)
        return

    # Persist RUNNING + L03/L04 output so pollers see progress, and release the
    # row lock before the long L05-L07 loop so a cancel call isn't blocked.
    db.commit()

    # ---- L05 + L06 + L07: retrieve, validate, judge, escalate ----------
    # SemanticOperator and EvidenceIntelligenceService are module-level
    # singletons (no per-request state). DB-bound operators are per-request.
    semantic_operator  = _get_semantic_operator()
    lexical_operator   = LexicalOperator(PostgresLexicalStoreAdapter(db))
    hybrid_operator    = HybridOperator(semantic_operator, lexical_operator, db)
    structured_operator = StructuredOperator(PostgresStructuredStoreAdapter(db))

    executor = EngineExecutor(
        operators=[semantic_operator, lexical_operator, hybrid_operator, structured_operator],
        resolver=PostgresContentResolver(db),
    )

    # Chroma's default distance space for the "knowledge" collection is L2,
    # not cosine, so `score = 1 - distance` is only a rough ranking signal,
    # not a calibrated 0..1 similarity. We do not reject on a similarity
    # threshold for that reason. L07 does not use raw scores either.
    query_text = l03_result.normalized_query or l03_result.original_query or canonical.query or ""
    allowed_versions = set(version_to_document)

    evidence_service = _get_evidence_service()

    # Per-request budget accumulator, pre-charged with L03 LLM usage (Tier B/C).
    # Each execute_fn call adds the L05 round's operator usage (currently 0 for
    # vector/lexical; populated by LLM operators once those exist).
    _budget = [l03_result.llm_tokens_used, l03_result.llm_cost_used]

    def execute_fn(round_plan, round_top_k):
        # Scalar read, not refresh(): refresh would discard unsaved fields on db_request.
        if _current_status(db, db_request) == RetrievalRequestStatus.CANCELLED:
            raise _StageError("CANCELLED", "Request was cancelled between rounds.")

        lims = plan.execution_limits
        if lims.max_tokens is not None and _budget[0] >= lims.max_tokens:
            raise _StageError(
                "BUDGET_EXHAUSTED",
                f"Token budget exhausted: {_budget[0]}/{lims.max_tokens} tokens used",
            )
        if lims.max_cost is not None and _budget[1] >= lims.max_cost:
            raise _StageError(
                "BUDGET_EXHAUSTED",
                f"Cost budget exhausted: {_budget[1]:.6f}/{lims.max_cost:.6f} used",
            )
        try:
            result = executor.execute_plan(
                round_plan, context_data={"top_k": round_top_k, "deadline": call_deadline}
            )
        except ScopeViolationError as exc:
            raise _StageError("SCOPE_VIOLATION", "Search without document scope is not allowed.") from exc
        except Exception as exc:
            raise _StageError("EXECUTION_ERROR", str(exc)[:500]) from exc
        _budget[0] += result.tokens_used
        _budget[1] += result.cost_used
        if reranker is not None and result.candidates:
            reranked = reranker.rerank(query_text, list(result.candidates), deadline=call_deadline)
            result = result.model_copy(update={"candidates": tuple(reranked)})
        return result

    last_validated = {"set": None}

    def evidence_fn(candidate_set):
        try:
            validated = evidence_service.process(
                candidate_set,
                context={
                    "required_scope": {},
                    "allowed_version_ids": allowed_versions,
                    "version_info": _version_info(db, rows),
                    "query": query_text,
                    "max_candidates": controls.max_candidates,
                },
            )
            last_validated["set"] = validated
            return validated
        except Exception as exc:
            raise _StageError("EVIDENCE_ERROR", str(exc)[:500]) from exc

    sufficiency_query = SufficiencyQuery.create(
        query_text=l03_result.normalized_query or l03_result.original_query or canonical.query or "",
        intent=l03_result.query_intelligence.intent,
        complexity=l03_result.query_intelligence.complexity,
        subqueries=tuple(sq.query for sq in l03_result.decomposition.subqueries)
        if l03_result.decomposition.is_decomposed
        else (),
        available_documents=len(rows),
    )

    # The caller's deadline also limits the L07 loop.
    config = SUFFICIENCY_CONFIG.model_copy(
        update={
            "max_total_latency_ms": max(1, min(SUFFICIENCY_CONFIG.max_total_latency_ms, budget_ms)),
            "max_rounds": rounds_limit,
            # "Search deeper" may never fetch more than L02 allows this profile.
            "max_top_k": controls.max_top_k,
        }
    )
    controller = ProgressiveRetrievalController(
        config=config,
        execute_fn=execute_fn,
        evidence_fn=evidence_fn,
    )

    try:
        outcome = controller.run(
            plan,
            sufficiency_query,
            top_k=top_k,
            request_id=db_request.request_id,
        )
    except _StageError as exc:
        if exc.code == "CANCELLED":
            # Status was already set to CANCELLED by the cancel endpoint;
            # just record when processing stopped.
            db_request.completed_at = datetime.now(timezone.utc)
        else:
            _fail(db_request, exc.code, exc.message)
        return
    except Exception as exc:
        logger.exception("L7 retrieval loop failed for %s", db_request.request_id)
        _fail(db_request, "EXECUTION_ERROR", str(exc)[:500])
        return

    report = outcome.report
    last_round = report.rounds[-1] if report.rounds else None
    db_request.retrieval_plan = {
        **(db_request.retrieval_plan or {}),
        "rounds": report.rounds_executed,
        "execution_status": last_round.execution_status if last_round else None,
        "usage": {
            "elapsed_ms": int((time.monotonic() - started_monotonic) * 1000),
            "tokens": _budget[0],
            "cost": round(_budget[1], 6),
        },
    }

    document_names = {doc_id: name for doc_id, name in version_to_document.values()}

    results: List[Dict[str, Any]] = []
    for rank, ve in enumerate(outcome.evidence, start=1):
        candidate = ve.candidate
        metadata = candidate.retrieval_metadata or {}
        results.append(
            {
                "rank": rank,
                "document_id": candidate.provenance.document_id,
                "document_name": document_names.get(candidate.provenance.document_id),
                "chunk_id": candidate.provenance.chunk_id,
                "content": candidate.content,
                "score": round(candidate.score, 4),
                "state": ve.state.value,
                "matched_by": metadata.get("matched_by"),
                "round": metadata.get("l7_round", 0),
            }
        )

    # COMPLETED only when L07 judged the evidence SUFFICIENT; otherwise PARTIAL
    # (with or without results) so clients never mistake weak evidence for an answer.
    if (
        SUFFICIENCY_CONFIG.partial_status_on_gaps
        and report.verdict != SufficiencyVerdict.SUFFICIENT
    ):
        db_request.status = RetrievalRequestStatus.PARTIAL
    else:
        db_request.status = RetrievalRequestStatus.COMPLETED

    package = build_evidence_package(
        request_id=db_request.request_id,
        query=query_text,
        profile=controls.profile.value,
        final_evidence=outcome.evidence,
        report=report,
        last_validated=last_validated["set"],
        document_names=document_names,
        documents_in_scope=len(rows),
        scope_truncated=scope_truncated,
        extra_warnings=(
            [f"Project has more than {len(rows)} searchable documents; only the "
             f"{len(rows)} most recently updated were searched."]
            if scope_truncated else []
        ),
    )

    db_request.results = results
    db_request.sufficiency = report.model_dump(mode="json")
    db_request.evidence_package = package.model_dump(mode="json")
    db_request.current_round = report.rounds_executed
    db_request.max_rounds = report.max_rounds
    db_request.completed_at = datetime.now(timezone.utc)

    # ---- L08: load memory context (session + long-term + agent + evidence) -
    memory_scope = {"project_id": db_request.project_id} if db_request.project_id else None
    memory_package = None
    try:
        memory_package = load_memory(
            query=query_text,
            correlation_id=canonical.lifecycle.correlation_id,
            user_id=db_request.user_id,
            actor_id=canonical.actor.actor_id,
            source_type=canonical.source_type,
            scope=memory_scope,
        )
    except Exception as exc:
        logger.warning("L08 memory load failed for %s: %s", db_request.request_id, exc)

    # Store this round's evidence so the next request in the same session
    # sees it as shared working state. Evidence L07 judged insufficient is
    # not worth remembering.
    if canonical.lifecycle.correlation_id and report.verdict != SufficiencyVerdict.INSUFFICIENT:
        write_evidence_chunks(
            correlation_id=canonical.lifecycle.correlation_id,
            request_id=db_request.request_id,
            evidence=package.evidence,
            scope=memory_scope,
            user_id=db_request.user_id,
        )

    # ---- L09-L11 + G8: augmentation (DEEP / COLLABORATIVE only) ----------
    tokens_used_so_far = _budget[0]
    cost_used_so_far = _budget[1]
    budget_tokens_left = (
        (db_request.max_tokens - tokens_used_so_far)
        if db_request.max_tokens
        else None
    )
    budget_cost_left = (
        (float(db_request.max_cost) - cost_used_so_far)
        if db_request.max_cost
        else None
    )
    if controls.allow_llm and package.evidence:
        progress.set_stage(db_request.request_id, progress.STAGE_WRITING)
    try:
        generated = run_augmentation(
            package=package,
            query=query_text,
            intent=l03_result.query_intelligence.intent,
            controls=controls,
            budget_tokens_remaining=budget_tokens_left,
            budget_cost_remaining=budget_cost_left,
            memory_package=memory_package,
            source_type=canonical.source_type,
            # Don't spend model time on a request the caller already cancelled.
            is_cancelled=lambda: _current_status(db, db_request) == RetrievalRequestStatus.CANCELLED,
            on_text=progress.partial_writer(db_request.request_id),
        )
        db_request.generated_answer = generated.model_dump(mode="json")

        # Remember the turn only when it produced something usable (or was a
        # retrieval-only profile): failed / ungrounded output must not become
        # conversation context for the next request.
        if canonical.lifecycle.correlation_id and generated.status in (
            GenerationStatus.SUCCESS, GenerationStatus.PARTIAL, GenerationStatus.SKIPPED,
        ):
            write_turn(
                correlation_id=canonical.lifecycle.correlation_id,
                query=query_text,
                request_id=db_request.request_id,
                answer_summary=generated.answer[:200] if generated.answer else "",
                scope=memory_scope,
                user_id=db_request.user_id,
            )
    except Exception as exc:
        logger.exception("L09-L11 augmentation failed for %s", db_request.request_id)
        db_request.generated_answer = GeneratedAnswer(
            status=GenerationStatus.FAILED,
            error_code="AUGMENTATION_ERROR",
            warnings=["Answer generation failed unexpectedly."],
        ).model_dump(mode="json")