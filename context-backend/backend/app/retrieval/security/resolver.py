from typing import Any, Dict, List

from sqlalchemy import exists
from sqlalchemy.orm import Session

from app.core.enums import (
    DocumentStatus,
    DocumentVersionStatus,
    KnowledgeProcessingRunStatus,
    ProjectStatus,
    RequestSourceType,
)
from app.auth.models import User
from app.project.models import Project
from app.knowledge.uploads.models import Document, DocumentVersion, KnowledgeProcessingRun

from app.retrieval.canonical.schemas import RetrievalContract
from app.retrieval.security.constraints import ConstraintError, parsed_dates, validate_constraints
from app.retrieval.security.enums import AuthorizationDecision
from app.retrieval.security.exceptions import SecurityResolutionError
from app.retrieval.security.profiles import controls_for, parse_profile
from app.retrieval.security.schemas import ScopedDocument, ScopedRetrievalContract

_ROLE_ADMIN = "ADMIN"
_MAX_SCOPE_DOCUMENTS = 500  # hard ceiling — prevents loading unbounded sets into memory

# Callers that act on behalf of an authenticated user. They never get more
# than that user could get; the actor_id is always the user's id.
_DELEGATED_SOURCES = (
    RequestSourceType.AGENT,
    RequestSourceType.WORKFLOW,
    RequestSourceType.PLANNER_AGENT,
)


def resolve_security_context(canonical: RetrievalContract, db: Session) -> ScopedRetrievalContract:
    """
    Evaluate the canonical request and produce a trusted security context:
    authorization decision, effective scope, profile controls and the exact
    list of documents (current versions) that may be searched.
    """
    profile = parse_profile(canonical.profile)

    context = ScopedRetrievalContract(
        request=canonical,
        security_context={
            "caller_type": canonical.source_type,
            "caller_id": canonical.actor.actor_id,
            "delegated": canonical.source_type in _DELEGATED_SOURCES,
        },
        requested_scope=canonical.scope,
        permitted_scope={},
        effective_scope={},
        denied_scope={},
        decision=AuthorizationDecision.SECURITY_BLOCKED,
        decision_metadata={"reason_code": "PENDING"},
        profile=profile,
        controls=controls_for(profile),
    )

    try:
        if canonical.source_type == RequestSourceType.USER or canonical.source_type in _DELEGATED_SOURCES:
            _resolve_user_authorization(canonical, context, db)
        elif canonical.source_type == RequestSourceType.INTERNAL:
            _resolve_internal_authorization(canonical, context, db)
        else:
            context.decision = AuthorizationDecision.DENY
            context.decision_metadata["reason_code"] = "UNSUPPORTED_CALLER_TYPE"
    except Exception as e:
        # Fail closed on any DB error or internal evaluation failure
        raise SecurityResolutionError(f"Failed to evaluate security context: {str(e)}")

    if context.decision in (AuthorizationDecision.DENY, AuthorizationDecision.SECURITY_BLOCKED):
        context.effective_scope = {}
        context.documents = []

    return context


def _deny(context: ScopedRetrievalContract, reason: str) -> None:
    context.decision = AuthorizationDecision.DENY
    context.decision_metadata["reason_code"] = reason


def _resolve_user_authorization(canonical: RetrievalContract, context: ScopedRetrievalContract, db: Session) -> None:
    user_id = canonical.actor.actor_id

    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        return _deny(context, "USER_NOT_FOUND")

    requested_project_id = canonical.scope.get("project_id")
    requested_kb_id = canonical.scope.get("knowledge_base_id")

    if not requested_project_id and not requested_kb_id:
        return _deny(context, "MISSING_REQUESTED_SCOPE")

    # There is no knowledge-base table to check ownership against, so a
    # knowledge_base_id can never be authorized. Fail closed.
    if requested_kb_id:
        context.denied_scope["knowledge_base_id"] = requested_kb_id
        return _deny(context, "KNOWLEDGE_BASE_SCOPE_UNSUPPORTED")

    project = db.query(Project).filter(Project.project_id == requested_project_id).first()
    if not project:
        context.denied_scope["project_id"] = requested_project_id
        return _deny(context, "PROJECT_NOT_FOUND")

    # Tenant isolation: the caller and the project must belong to the same
    # tenant. This is checked before ownership, so even an ADMIN can never
    # reach a project that lives in another tenant. A missing tenant on
    # either side fails closed.
    user_tenant = getattr(user, "tenant_id", None)
    project_tenant = getattr(project, "tenant_id", None)
    if not user_tenant or not project_tenant:
        context.denied_scope["project_id"] = requested_project_id
        return _deny(context, "TENANT_NOT_ASSIGNED")
    if str(user_tenant) != str(project_tenant):
        context.denied_scope["project_id"] = requested_project_id
        return _deny(context, "TENANT_MISMATCH")
    context.security_context["tenant_id"] = str(user_tenant)

    if project.user_id != user_id and user.role != _ROLE_ADMIN:
        context.denied_scope["project_id"] = requested_project_id
        return _deny(context, "UNAUTHORIZED_PROJECT_ACCESS")

    # Status is checked only after tenant + ownership, so "not active" is told
    # to someone who may see the project and reveals nothing to anyone else.
    if project.status != ProjectStatus.ACTIVE:
        context.denied_scope["project_id"] = requested_project_id
        return _deny(context, "PROJECT_NOT_ACTIVE")

    context.permitted_scope["project_id"] = requested_project_id
    _apply_project_scope(canonical, context, db, requested_project_id)


def _apply_project_scope(
    canonical: RetrievalContract, context: ScopedRetrievalContract, db: Session, project_id: str
) -> None:
    """
    Metadata constraints -> concrete document list -> effective scope.
    Shared by user-type callers (after the ownership check) and INTERNAL
    callers, so both reach L05/L06 with the same document_version_id filter.
    """
    try:
        constraints = validate_constraints(canonical.constraints)
    except ConstraintError as exc:
        return _deny(context, f"INVALID_CONSTRAINT:{exc.key}")
    context.applied_constraints = constraints

    # Fetch one past the cap so truncation is detected and reported, not silent.
    documents = _searchable_documents(db, project_id, constraints)
    scope_truncated = len(documents) > _MAX_SCOPE_DOCUMENTS
    documents = documents[:_MAX_SCOPE_DOCUMENTS]
    context.documents = documents
    context.effective_scope = {
        "document_version_id": {"$in": [d.document_version_id for d in documents]}
    }
    context.decision = (
        AuthorizationDecision.ALLOW_RESTRICTED if constraints else AuthorizationDecision.ALLOW
    )
    context.decision_metadata = {
        "reason_code": "OK",
        "profile": context.profile.value,
        "documents_in_scope": len(documents),
        "scope_truncated": scope_truncated,
        "max_scope_documents": _MAX_SCOPE_DOCUMENTS,
        "constraints_applied": sorted(constraints),
    }


def _searchable_documents(db: Session, project_id: str, constraints: Dict[str, Any]) -> List[ScopedDocument]:
    # A Document is ACTIVE from upload time, so that alone says nothing about
    # whether its content is searchable. Require the current version to have
    # passed ingestion (COMPLETED) AND a completed knowledge-processing run
    # (chunked, embedded, indexed). Half-processed versions are never searched.
    indexed = exists().where(
        KnowledgeProcessingRun.document_version_id == Document.current_version_id,
        KnowledgeProcessingRun.status == KnowledgeProcessingRunStatus.COMPLETED,
    )
    query = (
        db.query(Document)
        .join(DocumentVersion, DocumentVersion.document_version_id == Document.current_version_id)
        .filter(
            Document.project_id == project_id,
            Document.status == DocumentStatus.ACTIVE,
            DocumentVersion.status == DocumentVersionStatus.COMPLETED,
            indexed,
        )
    )
    if "document_ids" in constraints:
        query = query.filter(Document.document_id.in_(constraints["document_ids"]))
    if "mime_types" in constraints:
        query = query.filter(Document.mime_type.in_(constraints["mime_types"]))
    after, before = parsed_dates(constraints)
    if after is not None:
        query = query.filter(Document.created_at >= after)
    if before is not None:
        query = query.filter(Document.created_at < before)

    return [
        ScopedDocument(
            document_id=row.document_id,
            name=row.name,
            document_version_id=row.current_version_id,
            updated_at=row.updated_at,
            is_current=True,
        )
        for row in query.order_by(Document.updated_at.desc()).limit(_MAX_SCOPE_DOCUMENTS + 1).all()
    ]


def _resolve_internal_authorization(
    canonical: RetrievalContract, context: ScopedRetrievalContract, db: Session
) -> None:
    """
    INTERNAL callers are trusted: no user / ownership check. They still get
    the same project-scoped document list as everyone else, so L05 and L06
    always receive a document_version_id filter.
    """
    requested_project_id = canonical.scope.get("project_id")
    if not requested_project_id or canonical.scope.get("knowledge_base_id"):
        return _deny(context, "MISSING_REQUESTED_SCOPE")

    context.permitted_scope = {"project_id": requested_project_id}
    _apply_project_scope(canonical, context, db, requested_project_id)