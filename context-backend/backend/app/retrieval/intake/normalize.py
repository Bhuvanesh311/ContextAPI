import uuid

from app.retrieval.schemas import (
    RetrievalRequestCreate,
    NormalizedRetrievalRequest,
    LifecycleContext,
)
from app.retrieval.textutil import clean_text

_MAX_META_KEYS = 20
_MAX_META_VALUE_LEN = 200


def _clean_source_metadata(meta: dict) -> dict:
    """
    Source identification metadata (agent_id, workflow_id, planner_id, ...)
    is kept for lineage but never trusted: only short scalar values survive.
    """
    cleaned = {}
    for key, value in list((meta or {}).items())[:_MAX_META_KEYS]:
        if not isinstance(key, str):
            continue
        if isinstance(value, (int, float, bool)) or value is None:
            cleaned[key[:64]] = value
        elif isinstance(value, str):
            cleaned[key[:64]] = clean_text(value)[:_MAX_META_VALUE_LEN]
    return cleaned


def normalize_request(raw_request: RetrievalRequestCreate) -> NormalizedRetrievalRequest:
    """
    L00: adapt an incoming request from any source (user, agent, planner,
    workflow, internal service) into one NormalizedRetrievalRequest.

    - request reception: a server-issued request_id (never the caller's)
    - source identification: source_type + actor are carried through
    - context extraction: resource/execution context and source metadata
    - normalization: Unicode NFKC, control characters removed, whitespace collapsed
    """
    # The request identity is always issued here. A caller-chosen id would be
    # a global key: reusing another user's id would collide (409) and reveal
    # that it exists. The caller's id is kept for tracing (correlation id and
    # request_metadata.client_request_id); idempotency uses idempotency_key.
    req_id = "req_" + uuid.uuid4().hex[:16]
    client_request_id = raw_request.lifecycle.request_id if raw_request.lifecycle else None

    lifecycle = raw_request.lifecycle or LifecycleContext(request_id=req_id, cancellation=False)
    lifecycle = lifecycle.model_copy(
        update={
            "request_id": req_id,
            "correlation_id": lifecycle.correlation_id or client_request_id or req_id,
        }
    )

    source_metadata = _clean_source_metadata(raw_request.source_metadata)
    if client_request_id:
        source_metadata["client_request_id"] = clean_text(client_request_id)[:_MAX_META_VALUE_LEN]

    return NormalizedRetrievalRequest(
        request_id=req_id,
        source_type=raw_request.source_type,
        actor=raw_request.actor,
        retrieval_instruction=clean_text(raw_request.instruction),
        resource_context=raw_request.resource_context,
        execution_context=raw_request.execution_context,
        source_metadata=source_metadata,
        lifecycle=lifecycle,
    )