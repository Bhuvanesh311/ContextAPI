from copy import deepcopy

from app.core.enums import ExecutionProfile
from app.retrieval.schemas import NormalizedRetrievalRequest
from app.retrieval.canonical.schemas import RetrievalContract
from app.retrieval.canonical.exceptions import CanonicalizationError
from app.retrieval.security.constraints import ConstraintError, validate_constraints

# Only these keys are passed through from execution_context into execution_metadata.
# Anything else is discarded so a client can never smuggle unsupported directives.
_ALLOWED_EXECUTION_METADATA_KEYS = frozenset({"profile"})


def build_canonical_request(normalized: NormalizedRetrievalRequest) -> RetrievalContract:
    """
    Transform the L00 NormalizedRetrievalRequest into the L01 RetrievalContract
    (request identity, actor/source, project scope, objective/query,
    constraints, execution metadata, correlation/lifecycle metadata).
    Validates structural integrity and semantic invariants.
    """
    if not normalized.request_id:
        raise CanonicalizationError("Canonical request requires a stable request_id.", field="request_id")

    if not normalized.lifecycle:
        raise CanonicalizationError("Lifecycle context is required.", field="lifecycle")

    query = normalized.retrieval_instruction.strip()
    if not query:
        raise CanonicalizationError("Canonical query cannot be empty.", field="query")

    execution_ctx = deepcopy(normalized.execution_context)
    raw_constraints = execution_ctx.pop("constraints", {})
    scope = execution_ctx.pop("scope", {})

    resource_ctx = deepcopy(normalized.resource_context)
    if "scope" in resource_ctx and not scope:
        scope = resource_ctx.pop("scope")

    if not isinstance(scope, dict):
        raise CanonicalizationError("scope must be an object.", field="scope")

    # Constraints are validated here so an unsupported one is rejected,
    # not silently ignored (ignoring it would search wider than asked).
    try:
        constraints = validate_constraints(raw_constraints)
    except ConstraintError as exc:
        raise CanonicalizationError(str(exc), field=f"constraints.{exc.key}", error_code="UNSUPPORTED_CONSTRAINT")

    raw_profile = execution_ctx.get("profile")
    if raw_profile is None:
        profile = ExecutionProfile.STANDARD
    else:
        try:
            profile = ExecutionProfile(str(raw_profile).upper())
        except ValueError:
            raise CanonicalizationError(
                f"Unknown execution profile '{raw_profile}'.", field="profile", error_code="INVALID_PROFILE"
            )
    execution_metadata = {
        k: v for k, v in execution_ctx.items()
        if k in _ALLOWED_EXECUTION_METADATA_KEYS
    }
    execution_metadata["profile"] = profile.value

    return RetrievalContract(
        request_id=normalized.request_id,
        query=query,
        source_type=normalized.source_type,
        actor=normalized.actor,
        resource_context=resource_ctx,
        scope=scope,
        constraints=constraints,
        profile=profile,
        execution_metadata=execution_metadata,
        lifecycle=normalized.lifecycle,
        request_metadata=deepcopy(normalized.source_metadata),
    )