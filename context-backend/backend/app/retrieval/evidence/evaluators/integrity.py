"""
L06 evaluators: scope defense, provenance, quality, authority/freshness and
relevance. Each one returns one EvidenceEvaluationTrace; the policy decides
what the traces mean (see policy.py).

All of them read what they need from the `context` dict passed to
EvidenceIntelligenceService.process():

    allowed_version_ids : set[str]   L02's document versions (scope defense)
    version_info        : dict       version_id -> {document_active, is_current, updated_at, name}
    query               : str        the user's question (relevance)
"""

import time
from datetime import datetime, timezone
from typing import Any, Dict

from app.retrieval.engine.schemas import CandidateEvidence
from app.retrieval.evidence.evaluators.base import BaseEvaluator
from app.retrieval.evidence.models import EvidenceEvaluationTrace
from app.retrieval.textutil import term_coverage

UNKNOWN_DOCUMENT = "doc-unknown"


def _trace(name: str, signal_type: str, value: Any, reason: str, start: float) -> EvidenceEvaluationTrace:
    return EvidenceEvaluationTrace(
        evaluator_name=name,
        signal_type=signal_type,
        signal_value=value,
        reason=reason,
        latency_ms=int((time.time() - start) * 1000),
    )


class ScopeDefenseEvaluator(BaseEvaluator):
    """Second line of defense: is the chunk inside what L02 allowed?"""

    @property
    def name(self) -> str:
        return "scope_defense"

    def evaluate(self, candidate: CandidateEvidence, context: Dict[str, Any]) -> EvidenceEvaluationTrace:
        start = time.time()
        allowed = context.get("allowed_version_ids")
        if allowed is None:
            return _trace(self.name, "scope", True, "No scope supplied", start)
        version_id = candidate.provenance.document_version_id
        if version_id in allowed:
            return _trace(self.name, "scope", True, "Inside L02 effective scope", start)
        return _trace(self.name, "scope", False, f"Document version {version_id} is outside the L02 scope", start)


class ProvenanceEvaluator(BaseEvaluator):
    """Every piece of evidence must say exactly where it came from."""

    @property
    def name(self) -> str:
        return "provenance_validator"

    def evaluate(self, candidate: CandidateEvidence, context: Dict[str, Any]) -> EvidenceEvaluationTrace:
        start = time.time()
        p = candidate.provenance
        if not p.document_id or p.document_id == UNKNOWN_DOCUMENT:
            return _trace(self.name, "provenance", False, "Document could not be resolved", start)
        if not p.chunk_id or not p.document_version_id:
            return _trace(self.name, "provenance", False, "Missing chunk or document version id", start)
        info = context.get("version_info")
        if info is not None and p.document_version_id not in info:
            return _trace(self.name, "provenance", False, "Document version is not known to this request", start)
        return _trace(self.name, "provenance", True, "Provenance complete", start)


class QualityEvaluator(BaseEvaluator):
    """Evidence quality: not empty, not garbage."""

    def __init__(self, min_chars: int = 20, min_alpha_ratio: float = 0.3):
        self.min_chars = min_chars
        self.min_alpha_ratio = min_alpha_ratio

    @property
    def name(self) -> str:
        return "quality_evaluator"

    def evaluate(self, candidate: CandidateEvidence, context: Dict[str, Any]) -> EvidenceEvaluationTrace:
        start = time.time()
        text = (candidate.content or "").strip()
        if len(text) < self.min_chars:
            return _trace(self.name, "quality", False, f"Content shorter than {self.min_chars} characters", start)
        # Whitespace is layout, and digits are data (tables, CSV rows, prices):
        # only punctuation/symbol noise should count against a chunk. Counting
        # letters over all characters rejected indented CSV/JSON rows.
        visible = [ch for ch in text if not ch.isspace()]
        alpha = sum(ch.isalnum() for ch in visible) / len(visible)
        if alpha < self.min_alpha_ratio:
            return _trace(self.name, "quality", False, "Content is mostly non-text characters", start)
        return _trace(self.name, "quality", True, "Content is usable text", start)


class AuthorityFreshnessEvaluator(BaseEvaluator):
    """Is this the current version of an active document, and how old is it?"""

    @property
    def name(self) -> str:
        return "authority_freshness"

    def evaluate(self, candidate: CandidateEvidence, context: Dict[str, Any]) -> EvidenceEvaluationTrace:
        start = time.time()
        info = (context.get("version_info") or {}).get(candidate.provenance.document_version_id)
        if not info:
            return _trace(self.name, "authority", {"status": "unknown", "age_days": None}, "No version information", start)
        if not info.get("document_active", True):
            status = "inactive"
        elif not info.get("is_current", True):
            status = "superseded"
        else:
            status = "current"
        age_days = None
        updated = info.get("updated_at")
        if isinstance(updated, datetime):
            age_days = max(0, (datetime.now(timezone.utc).replace(tzinfo=None) - updated.replace(tzinfo=None)).days)
        return _trace(self.name, "authority", {"status": status, "age_days": age_days}, f"Document is {status}", start)


class RelevanceEvaluator(BaseEvaluator):
    """
    How many of the question's topic words does the evidence contain?
    Raw retrieval scores are not calibrated (Chroma L2 distance, RRF), so
    relevance is judged from the text instead.
    """

    @property
    def name(self) -> str:
        return "relevance_evaluator"

    def evaluate(self, candidate: CandidateEvidence, context: Dict[str, Any]) -> EvidenceEvaluationTrace:
        start = time.time()
        coverage, covered, missing = term_coverage(context.get("query", ""), candidate.content)
        matched_by = str((candidate.retrieval_metadata or {}).get("matched_by") or "")
        # No matched_by (plain semantic search) counts as semantic.
        semantic = (not matched_by) or "semantic" in matched_by
        return _trace(
            self.name,
            "relevance",
            {"coverage": round(coverage, 3), "semantic": semantic, "covered": covered, "missing": missing},
            f"{len(covered)} of {len(covered) + len(missing)} query terms found",
            start,
        )