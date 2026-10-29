"""
Unit tests for L02 (Security & Scope Resolution).

No real database: a tiny fake session returns the user / project, and the
document lookup is replaced. Run from the backend folder:

    python -m pytest tests/retrieval/test_l02_security.py -v
"""
from types import SimpleNamespace

import pytest

from app.auth.models import User
from app.core.enums import ExecutionProfile, RequestSourceType
from app.project.models import Project
from app.retrieval.canonical.builder import build_canonical_request
from app.retrieval.intake.normalize import normalize_request
from app.retrieval.schemas import ActorModel, RetrievalRequestCreate
from app.retrieval.security import resolver
from app.retrieval.security.enums import AuthorizationDecision
from app.retrieval.security.profiles import PROFILE_CONTROLS, controls_for, parse_profile
from app.retrieval.security.resolver import resolve_security_context
from app.retrieval.security.schemas import ScopedDocument


class FakeQuery:
    def __init__(self, result):
        self.result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.result


class FakeDB:
    def __init__(self, user=None, project=None):
        self.user, self.project = user, project

    def query(self, model):
        return FakeQuery(self.user if model is User else self.project)


OWNER = SimpleNamespace(user_id="USR1", role="USER", is_verified=True, tenant_id="TEN1")
OTHER = SimpleNamespace(user_id="USR2", role="USER", is_verified=True, tenant_id="TEN1")
ADMIN = SimpleNamespace(user_id="USR9", role="ADMIN", is_verified=True, tenant_id="TEN1")
FOREIGN = SimpleNamespace(user_id="USR3", role="USER", is_verified=True, tenant_id="TEN2")
FOREIGN_ADMIN = SimpleNamespace(user_id="USR8", role="ADMIN", is_verified=True, tenant_id="TEN2")
PROJECT = SimpleNamespace(project_id="PROJ1", user_id="USR1", tenant_id="TEN1", status="active")
DOCS = [
    ScopedDocument(document_id="DOC1", name="a.pdf", document_version_id="V1"),
    ScopedDocument(document_id="DOC2", name="b.pdf", document_version_id="V2"),
]


@pytest.fixture(autouse=True)
def fake_documents(monkeypatch):
    seen = {}

    def fake(db, project_id, constraints):
        seen["project_id"], seen["constraints"] = project_id, constraints
        return list(DOCS)

    monkeypatch.setattr(resolver, "_searchable_documents", fake)
    return seen


def contract(actor_id="USR1", source=RequestSourceType.USER, scope=None, **ctx):
    scope = {"project_id": "PROJ1"} if scope is None else scope
    context = {"scope": scope} if scope else {}
    context.update(ctx)
    raw = RetrievalRequestCreate(
        instruction="What is ContextAPI?",
        source_type=source,
        actor=ActorModel(actor_type=source.value, actor_id=actor_id),
        execution_context=context,
    )
    return build_canonical_request(normalize_request(raw))


def resolve(c, user=OWNER, project=PROJECT):
    return resolve_security_context(c, FakeDB(user=user, project=project))


def reason(ctx):
    return ctx.decision_metadata["reason_code"]


# ------------------------------------------------------------ authorization
def test_owner_is_allowed_with_documents_and_scope_filter(fake_documents):
    ctx = resolve(contract())
    assert ctx.decision == AuthorizationDecision.ALLOW
    assert ctx.permitted_scope == {"project_id": "PROJ1"}
    assert ctx.effective_scope == {"document_version_id": {"$in": ["V1", "V2"]}}
    assert [d.document_id for d in ctx.documents] == ["DOC1", "DOC2"]
    assert fake_documents["project_id"] == "PROJ1"


def test_other_users_project_is_denied_and_scope_is_empty():
    ctx = resolve(contract(actor_id="USR2"), user=OTHER)
    assert ctx.decision == AuthorizationDecision.DENY
    assert reason(ctx) == "UNAUTHORIZED_PROJECT_ACCESS"
    assert ctx.effective_scope == {} and ctx.documents == []
    assert ctx.denied_scope == {"project_id": "PROJ1"}


def test_admin_can_access_any_project_in_their_own_tenant():
    ctx = resolve(contract(actor_id="USR9"), user=ADMIN)
    assert ctx.decision == AuthorizationDecision.ALLOW


# --------------------------------------------------------- tenant isolation
def test_same_tenant_user_gets_the_tenant_in_the_security_context():
    ctx = resolve(contract())
    assert ctx.security_context["tenant_id"] == "TEN1"


def test_user_from_another_tenant_is_denied():
    ctx = resolve(contract(actor_id="USR3"), user=FOREIGN)
    assert ctx.decision == AuthorizationDecision.DENY
    assert reason(ctx) == "TENANT_MISMATCH"
    assert ctx.effective_scope == {} and ctx.documents == []
    assert ctx.denied_scope == {"project_id": "PROJ1"}


def test_admin_from_another_tenant_is_denied_too():
    ctx = resolve(contract(actor_id="USR8"), user=FOREIGN_ADMIN)
    assert ctx.decision == AuthorizationDecision.DENY
    assert reason(ctx) == "TENANT_MISMATCH"


@pytest.mark.parametrize("source", [
    RequestSourceType.AGENT, RequestSourceType.PLANNER_AGENT, RequestSourceType.WORKFLOW,
])
def test_agents_cannot_cross_tenants_either(source):
    ctx = resolve(contract(actor_id="USR3", source=source), user=FOREIGN)
    assert reason(ctx) == "TENANT_MISMATCH"


def test_user_without_a_tenant_fails_closed():
    no_tenant = SimpleNamespace(user_id="USR1", role="USER", is_verified=True, tenant_id=None)
    ctx = resolve(contract(), user=no_tenant)
    assert ctx.decision == AuthorizationDecision.DENY
    assert reason(ctx) == "TENANT_NOT_ASSIGNED"


def test_project_without_a_tenant_fails_closed():
    legacy_project = SimpleNamespace(project_id="PROJ1", user_id="USR1", tenant_id=None, status="active")
    ctx = resolve(contract(), project=legacy_project)
    assert ctx.decision == AuthorizationDecision.DENY
    assert reason(ctx) == "TENANT_NOT_ASSIGNED"


def test_unknown_user_is_denied():
    assert reason(resolve(contract(), user=None)) == "USER_NOT_FOUND"


def test_unknown_project_is_denied():
    assert reason(resolve(contract(), project=None)) == "PROJECT_NOT_FOUND"


def test_missing_scope_is_denied():
    assert reason(resolve(contract(scope={}))) == "MISSING_REQUESTED_SCOPE"


def test_knowledge_base_scope_is_denied_because_it_cannot_be_checked():
    ctx = resolve(contract(scope={"knowledge_base_id": "KB1"}))
    assert ctx.decision == AuthorizationDecision.DENY
    assert reason(ctx) == "KNOWLEDGE_BASE_SCOPE_UNSUPPORTED"
    ctx = resolve(contract(scope={"project_id": "PROJ1", "knowledge_base_id": "KB1"}))
    assert reason(ctx) == "KNOWLEDGE_BASE_SCOPE_UNSUPPORTED"
    assert ctx.effective_scope == {}


# ---------------------------------------------------------- delegated sources
@pytest.mark.parametrize("source", [
    RequestSourceType.AGENT, RequestSourceType.PLANNER_AGENT, RequestSourceType.WORKFLOW,
])
def test_agent_acts_with_the_users_access_and_no_more(source):
    ok = resolve(contract(source=source))
    assert ok.decision == AuthorizationDecision.ALLOW
    assert ok.security_context["delegated"] is True

    denied = resolve(contract(actor_id="USR2", source=source), user=OTHER)
    assert denied.decision == AuthorizationDecision.DENY
    assert reason(denied) == "UNAUTHORIZED_PROJECT_ACCESS"


def test_internal_source_is_trusted_and_gets_the_project_documents():
    ctx = resolve(contract(source=RequestSourceType.INTERNAL))
    assert ctx.decision == AuthorizationDecision.ALLOW
    assert ctx.effective_scope == {"document_version_id": {"$in": ["V1", "V2"]}}
    assert [d.document_id for d in ctx.documents] == ["DOC1", "DOC2"]


def test_internal_source_applies_constraints_too(fake_documents):
    ctx = resolve(contract(source=RequestSourceType.INTERNAL, constraints={"document_ids": ["DOC1"]}))
    assert ctx.decision == AuthorizationDecision.ALLOW_RESTRICTED
    assert fake_documents["constraints"] == {"document_ids": ["DOC1"]}


def test_internal_source_without_project_scope_is_denied():
    ctx = resolve(contract(source=RequestSourceType.INTERNAL, scope={}))
    assert ctx.decision == AuthorizationDecision.DENY
    assert reason(ctx) == "MISSING_REQUESTED_SCOPE"
    assert ctx.effective_scope == {}


# ---------------------------------------------------------------- constraints
def test_constraints_are_applied_and_make_the_decision_restricted(fake_documents):
    ctx = resolve(contract(constraints={"document_ids": ["DOC1"]}))
    assert ctx.decision == AuthorizationDecision.ALLOW_RESTRICTED
    assert ctx.applied_constraints == {"document_ids": ["DOC1"]}
    assert fake_documents["constraints"] == {"document_ids": ["DOC1"]}
    assert ctx.decision_metadata["constraints_applied"] == ["document_ids"]


def test_no_constraints_means_plain_allow():
    ctx = resolve(contract())
    assert ctx.decision == AuthorizationDecision.ALLOW
    assert ctx.applied_constraints == {}


# ------------------------------------------------------------------- profiles
def test_profile_controls_come_with_the_context():
    ctx = resolve(contract(profile="deep"))
    assert ctx.profile == ExecutionProfile.DEEP
    assert ctx.controls.allow_llm is True and ctx.controls.allow_expansion is True


def test_default_profile_is_standard():
    ctx = resolve(contract())
    assert ctx.profile == ExecutionProfile.STANDARD
    assert ctx.controls.allow_llm is False


def test_every_profile_has_controls_and_they_grow_with_effort():
    for p in ExecutionProfile:
        assert PROFILE_CONTROLS[p].profile == p
    fast, std, deep = (controls_for(p) for p in (
        ExecutionProfile.FAST, ExecutionProfile.STANDARD, ExecutionProfile.DEEP))
    assert fast.max_rounds <= std.max_rounds <= deep.max_rounds
    assert fast.max_top_k <= std.max_top_k <= deep.max_top_k
    assert fast.max_latency_ms <= std.max_latency_ms <= deep.max_latency_ms
    assert fast.allow_llm is False and fast.allow_rerank is False


def test_unknown_profile_values_fall_back_to_standard_never_wider():
    assert parse_profile("turbo") == ExecutionProfile.STANDARD
    assert parse_profile(None) == ExecutionProfile.STANDARD
    assert parse_profile("fast") == ExecutionProfile.FAST


def test_denied_request_still_reports_its_profile_but_no_scope():
    ctx = resolve(contract(actor_id="USR2", profile="fast"), user=OTHER)
    assert ctx.decision == AuthorizationDecision.DENY
    assert ctx.profile == ExecutionProfile.FAST
    assert ctx.documents == [] and ctx.effective_scope == {}

# ---------------------------------------------------------------- scope cap

def test_scope_within_cap_is_not_truncated(fake_documents):
    ctx = resolve(contract())
    assert ctx.decision_metadata["scope_truncated"] is False


def test_scope_over_cap_is_truncated_and_flagged(fake_documents, monkeypatch):
    monkeypatch.setattr(resolver, "_MAX_SCOPE_DOCUMENTS", 1)
    ctx = resolve(contract())
    assert ctx.decision_metadata["scope_truncated"] is True
    assert len(ctx.documents) == 1
    assert ctx.effective_scope == {"document_version_id": {"$in": ["V1"]}}
