"""
L02 execution-profile controls (FAST / STANDARD / DEEP / COLLABORATIVE).

L02 decides what each profile is ALLOWED to do. Later layers read these
controls and can only narrow them, never widen them:

    L03 uses allow_llm            L04 uses max_steps / max_subqueries / budgets
    L05 uses allow_rerank / allow_expansion
    L07 uses max_rounds / max_latency_ms / max_top_k
"""

from pydantic import BaseModel, ConfigDict

from app.core.enums import ExecutionProfile


class ProfileControls(BaseModel):
    model_config = ConfigDict(frozen=True)

    profile: ExecutionProfile
    max_rounds: int
    max_latency_ms: int
    max_top_k: int
    max_steps: int
    max_subqueries: int
    max_candidates: int
    max_llm_calls: int
    allow_llm: bool
    allow_rerank: bool
    allow_expansion: bool


PROFILE_CONTROLS = {
    ExecutionProfile.FAST: ProfileControls(
        profile=ExecutionProfile.FAST,
        max_rounds=1, max_latency_ms=8_000, max_top_k=10, max_steps=2,
        max_subqueries=1, max_candidates=20, max_llm_calls=0,
        allow_llm=False, allow_rerank=False, allow_expansion=False,
    ),
    ExecutionProfile.STANDARD: ProfileControls(
        profile=ExecutionProfile.STANDARD,
        max_rounds=2, max_latency_ms=30_000, max_top_k=20, max_steps=4,
        max_subqueries=3, max_candidates=50, max_llm_calls=0,
        allow_llm=False, allow_rerank=True, allow_expansion=False,
    ),
    ExecutionProfile.DEEP: ProfileControls(
        profile=ExecutionProfile.DEEP,
        max_rounds=3, max_latency_ms=60_000, max_top_k=30, max_steps=6,
        max_subqueries=5, max_candidates=80, max_llm_calls=1,
        allow_llm=True, allow_rerank=True, allow_expansion=True,
    ),
    ExecutionProfile.COLLABORATIVE: ProfileControls(
        profile=ExecutionProfile.COLLABORATIVE,
        max_rounds=3, max_latency_ms=60_000, max_top_k=30, max_steps=8,
        max_subqueries=5, max_candidates=100, max_llm_calls=2,
        allow_llm=True, allow_rerank=True, allow_expansion=True,
    ),
}

DEFAULT_PROFILE = ExecutionProfile.STANDARD


def parse_profile(value) -> ExecutionProfile:
    """Unknown or missing values fall back to STANDARD (never to a wider profile)."""
    if isinstance(value, ExecutionProfile):
        return value
    try:
        return ExecutionProfile(str(value).upper())
    except ValueError:
        return DEFAULT_PROFILE


def controls_for(profile) -> ProfileControls:
    return PROFILE_CONTROLS[parse_profile(profile)]