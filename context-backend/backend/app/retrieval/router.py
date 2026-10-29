import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.database import get_db
from app.core.enums import RequestSourceType, RetrievalRequestStatus
from app.infra.redis.client import redis_client
from app.retrieval.schemas import (
    ActorModel,
    AnswerSource,
    RetrievalAnswerResponse,
    RetrievalRequestCreate,
    RetrievalRequestResponse,
)
from app.retrieval.models import RetrievalRequest
from app.retrieval.intake.validation import validate_intake_request, IntakeValidationError
from app.retrieval.intake.normalize import normalize_request
from app.retrieval.bootstrap import register_capabilities
from app.retrieval import progress
from app.retrieval.service import cancel_if_active

register_capabilities()

logger = logging.getLogger(__name__)

_RETRIEVAL_RATE_LIMIT = 10   # requests per user per window
_RETRIEVAL_RATE_WINDOW = 60  # seconds


def _check_retrieval_rate_limit(user_id: str) -> None:
    key = f"ratelimit:retrieval:{user_id}"
    # One MULTI/EXEC: the counter can never exist without a TTL (a crash
    # between INCR and EXPIRE would otherwise lock the user out for good).
    pipe = redis_client.pipeline(transaction=True)
    pipe.incr(key)
    pipe.expire(key, _RETRIEVAL_RATE_WINDOW, nx=True)
    count, _ = pipe.execute()
    if count > _RETRIEVAL_RATE_LIMIT:
        ttl = max(int(redis_client.ttl(key)), 1)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error_code": "RATE_LIMIT_EXCEEDED",
                "message": f"Too many retrieval requests. Retry after {ttl}s.",
                "retry_after_seconds": ttl,
            },
        )

router = APIRouter(
    prefix="/api/v1/retrieval/requests",
    tags=["Retrieval"],
)


def _require_own_request(req: RetrievalRequest | None, current_user: User) -> RetrievalRequest:
    if not req or req.user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Retrieval request not found")
    return req


@router.post("", response_model=RetrievalRequestResponse, status_code=status.HTTP_202_ACCEPTED)
def create_retrieval_request(
    request: RetrievalRequestCreate,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_retrieval_rate_limit(current_user.user_id)

    # L00 source adaptation. The authenticated user is always the principal.
    # A caller may declare it is acting as an AGENT / PLANNER_AGENT / WORKFLOW;
    # it then acts ON BEHALF OF the authenticated user: actor_id is always the
    # user's id (never what the body says), and later layers give it no more
    # access than that user has. INTERNAL (trusted) cannot be claimed by a
    # client; validate_intake_request rejects it.
    # project_id shortcut -> execution_context.scope.project_id
    execution_context = dict(request.execution_context or {})
    if request.project_id:
        scope = dict(execution_context.get("scope") or {})
        scope["project_id"] = request.project_id
        execution_context["scope"] = scope
    # L01 shortcuts: constraints and profile can be sent at the top level.
    if request.constraints is not None:
        execution_context["constraints"] = request.constraints
    if request.profile is not None:
        execution_context["profile"] = request.profile.value

    request = request.model_copy(
        update={
            "actor": ActorModel(actor_type=request.source_type.value, actor_id=current_user.user_id),
            "execution_context": execution_context,
        }
    )

    try:
        validate_intake_request(request)
    except IntakeValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": e.error_code, "message": str(e)}
        )
    
    normalized = normalize_request(request)
    
    # L01 Canonicalization
    try:
        from app.retrieval.canonical.builder import build_canonical_request
        from app.retrieval.canonical.exceptions import CanonicalizationError
        canonical = build_canonical_request(normalized)
    except CanonicalizationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": e.error_code, "message": str(e), "field": e.field}
        )

    # Idempotency check
    # Both lookups are limited to the caller's own requests, so one user can
    # never read another user's result by reusing a key or a request id.
    if canonical.lifecycle.idempotency_key:
        existing_idempotent = (
            db.query(RetrievalRequest)
            .filter_by(idempotency_key=canonical.lifecycle.idempotency_key, user_id=current_user.user_id)
            .first()
        )
        if existing_idempotent:
            response.status_code = status.HTTP_200_OK
            return existing_idempotent

    existing = db.query(RetrievalRequest).filter_by(request_id=canonical.request_id).first()
    if existing:
        if existing.user_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Conflict during request creation",
            )
        response.status_code = status.HTTP_200_OK
        return existing

    # Persistence
    # NOTE (fix): project_id lives in canonical.scope (execution_context.scope
    # is where canonicalization puts it -- see canonical/builder.py), not in
    # resource_context. The original code read resource_context.get("project_id"),
    # which is always None for a normal request, so the project_id column was
    # always NULL and nothing downstream could resolve a project.
    db_request = RetrievalRequest(
        request_id=canonical.request_id,
        source_type=canonical.source_type,
        query=canonical.query,
        # Set by the worker only after L02 authorizes it. Writing the requested
        # id here would hit the projects FK, and "unknown project -> 409" vs
        # "someone else's project -> 202" would reveal which ids exist.
        # The requested scope is kept in `scope`.
        project_id=None,
        knowledge_base_id=canonical.scope.get("knowledge_base_id"),
        user_id=canonical.actor.actor_id,
        idempotency_key=canonical.lifecycle.idempotency_key,
        scope=canonical.scope,
        constraints=canonical.constraints,
        execution_profile=canonical.profile,
        max_latency_ms=request.max_latency_ms,
        max_tokens=request.max_tokens,
        max_cost=request.max_cost,
        status=RetrievalRequestStatus.PENDING,
    )

    db.add(db_request)
    try:
        db.commit()
        db.refresh(db_request)
    except IntegrityError:
        db.rollback()
        # Lost a race on the same request_id or on this user's idempotency key.
        existing = db.query(RetrievalRequest).filter_by(request_id=canonical.request_id).first()
        if existing is None and canonical.lifecycle.idempotency_key:
            existing = (
                db.query(RetrievalRequest)
                .filter_by(idempotency_key=canonical.lifecycle.idempotency_key, user_id=current_user.user_id)
                .first()
            )
        if existing and existing.user_id == current_user.user_id:
            response.status_code = status.HTTP_200_OK
            return existing
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflict during request creation"
        )
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal database error"
        )

    # Enqueue the retrieval pipeline as a Celery task.
    # The worker owns its own DB session and runs L02-L11 asynchronously.
    # The client polls GET /{request_id}/status for completion.
    from app.retrieval.tasks import run_retrieval_task
    try:
        run_retrieval_task.apply_async(
            kwargs={
                "request_id": db_request.request_id,
                "canonical_dict": canonical.model_dump(mode="json"),
                "top_k": request.top_k,
            },
            queue="retrieval",
        )
    except Exception:
        # Broker down: don't leave a PENDING row no worker will ever pick up.
        logger.exception("Could not enqueue retrieval request %s", db_request.request_id)
        db_request.status = RetrievalRequestStatus.FAILED
        db_request.error_code = "QUEUE_UNAVAILABLE"
        db_request.error_message = "The request could not be queued. Please retry."
        db_request.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(db_request)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return db_request

@router.get("/{request_id}", response_model=RetrievalRequestResponse)
def get_retrieval_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = db.query(RetrievalRequest).filter_by(request_id=request_id).first()
    return _require_own_request(req, current_user)

@router.get("/{request_id}/status", response_model=RetrievalRequestResponse)
def get_retrieval_request_status(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = db.query(RetrievalRequest).filter_by(request_id=request_id).first()
    return _require_own_request(req, current_user)

@router.post("/{request_id}/cancel", response_model=RetrievalRequestResponse)
def cancel_retrieval_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = db.query(RetrievalRequest).filter_by(request_id=request_id).first()
    req = _require_own_request(req, current_user)
    
    cancel_if_active(db, req.id)
    db.refresh(req)

    return req

_DONE_STATUSES = {
    RetrievalRequestStatus.COMPLETED,
    RetrievalRequestStatus.PARTIAL,
    RetrievalRequestStatus.FAILED,
    RetrievalRequestStatus.CANCELLED,
}
_MAX_WAIT_SECONDS = 60


def _answer_warnings(req: RetrievalRequest, generated: dict) -> list[str]:
    warnings = list(generated.get("warnings") or [])
    if generated.get("answer") or req.status not in _DONE_STATUSES:
        return warnings
    # No answer: say why instead of returning a bare null.
    reasons = [generated.get("skip_reason")]
    reasons += [g.get("message") for g in (req.sufficiency or {}).get("gaps") or [] if isinstance(g, dict)]
    if not req.results and not generated:
        reasons.append("No matching text was found in this project's documents.")
    for reason in reasons:
        if reason and reason not in warnings:
            warnings.append(reason)
    return warnings


_NOTICES = {
    "no_documents": "This project has no searchable documents yet. Upload a file to ask questions about it.",
    "not_relevant": (
        "Your documents don't seem to cover this question. "
        "Try asking about something in them, or upload a file that covers it."
    ),
    "partial": "Your documents only partly cover this question, so some details may be missing.",
}


def _relevance(req: RetrievalRequest, generated: dict) -> tuple[str | None, str | None]:
    """
    One verdict for every profile: L07's sufficiency decides, and a model that
    abstained or a partial answer can only lower it. Failures keep their own
    error message, so they get no relevance.
    """
    if req.status not in _DONE_STATUSES or req.status in (
        RetrievalRequestStatus.FAILED, RetrievalRequestStatus.CANCELLED,
    ):
        return None, None
    answer_status = generated.get("status")
    if answer_status in ("FAILED", "CANCELLED"):
        return None, None

    sufficiency = req.sufficiency or {}
    verdict = sufficiency.get("verdict")
    if sufficiency.get("stop_reason") == "NO_SEARCHABLE_DOCUMENTS":
        relevance = "no_documents"
    elif answer_status == "INSUFFICIENT_CONTEXT" or verdict == "INSUFFICIENT" or not req.results:
        relevance = "not_relevant"
    elif verdict == "PARTIALLY_SUFFICIENT" or answer_status == "PARTIAL":
        relevance = "partial"
    else:
        relevance = "relevant"
    return relevance, _NOTICES.get(relevance)


def _to_answer(req: RetrievalRequest) -> RetrievalAnswerResponse:
    generated = req.generated_answer or {}
    relevance, notice = _relevance(req, generated)
    if generated.get("skipped"):
        answer_status = "skipped"
    else:
        answer_status = generated.get("status")
    done = req.status in _DONE_STATUSES
    stage, partial = (None, None) if done else progress.read(req.request_id)
    return RetrievalAnswerResponse(
        stage=stage or (None if done else "queued" if req.status == RetrievalRequestStatus.PENDING else "searching"),
        partial_answer=partial,
        request_id=req.request_id,
        status=req.status,
        done=done,
        project_id=req.project_id or (req.scope or {}).get("project_id"),
        question=req.query,
        profile=req.execution_profile,
        answer=generated.get("answer") or None,
        answer_status=answer_status if generated else None,
        model_tier=generated.get("tier") or None,
        grounding_score=generated.get("grounding_score") if generated else None,
        relevance=relevance,
        notice=notice,
        cited_sources=[
            AnswerSource(
                citation=c.get("citation_number"),
                document_id=c.get("document_id"),
                document_name=c.get("document_name"),
            )
            for c in generated.get("citations") or []
        ],
        top_results=[
            AnswerSource(
                citation=r.get("rank"),
                document_id=r.get("document_id"),
                document_name=r.get("document_name"),
                score=r.get("score"),
                snippet=(r.get("content") or "")[:300] or None,
            )
            for r in (req.results or [])[:5]
        ],
        warnings=_answer_warnings(req, generated),
        error_code=req.error_code,
        error_message=req.error_message,
    )


@router.get(
    "/{request_id}/answer",
    response_model=RetrievalAnswerResponse,
    summary="Get the answer (waits until it is ready)",
    description=(
        "Short view of a request: answer, cited documents and the top results. "
        "Waits up to `wait_seconds` for the request to finish; if `done` is false, call it again. "
        "While it runs, `stage` and `partial_answer` show live progress; poll with a small "
        "`wait_seconds` (e.g. 1) to display the answer as it is written."
    ),
)
def get_retrieval_answer(
    request_id: str = Path(description="The `request_id` returned when the request was created, e.g. req_1a2b3c4d5e6f7a8b (no quotes)."),
    wait_seconds: int = Query(default=30, ge=0, le=_MAX_WAIT_SECONDS, description="How long to wait for the answer."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = _require_own_request(db.query(RetrievalRequest).filter_by(request_id=request_id).first(), current_user)
    deadline = time.monotonic() + wait_seconds
    while req.status not in _DONE_STATUSES and time.monotonic() < deadline:
        time.sleep(1)
        db.refresh(req)
    return _to_answer(req)
