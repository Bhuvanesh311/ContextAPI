"""
EvidencePackage: the single object L06/L07 hand to the augmentation domain.

    validated evidence + provenance + coverage + conflicts
    + unresolved gaps + retrieval warnings

L08-L10 read this and nothing else about retrieval.
"""

import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

from pydantic import BaseModel, Field

from app.retrieval.evidence.enums import EvidenceState
from app.retrieval.evidence.models import RelationshipType, ValidatedEvidence, ValidatedEvidenceSet
from app.retrieval.textutil import significant_terms, term_coverage

EXPANSION = "expansion"


class PackageSource(BaseModel):
    document_id: str
    document_name: Optional[str] = None
    document_version_id: str
    chunk_id: str
    source_type: str
    operator_type: str
    step_id: str


class PackageItem(BaseModel):
    rank: int
    evidence_id: str
    content: str
    score: float
    state: str
    matched_by: Optional[str] = None
    round: int = 0
    source: PackageSource
    authority: Optional[str] = None
    relevance_coverage: Optional[float] = None
    relationships: List[Dict[str, str]] = Field(default_factory=list)


class PackageConflict(BaseModel):
    evidence_ids: List[str]
    chunk_ids: List[str]
    reason: str


class PackageCoverage(BaseModel):
    query_terms: List[str] = Field(default_factory=list)
    covered_terms: List[str] = Field(default_factory=list)
    uncovered_terms: List[str] = Field(default_factory=list)
    term_coverage: float = 0.0
    documents_in_scope: int = 0
    scope_truncated: bool = False
    documents_used: int = 0
    document_ids_used: List[str] = Field(default_factory=list)


class PackageGap(BaseModel):
    gap_type: str
    severity: str
    message: str


class EvidencePackage(BaseModel):
    package_id: str
    request_id: str
    query: str
    profile: str
    verdict: str
    sufficiency_score: float
    stop_reason: str
    rounds_executed: int
    evidence: List[PackageItem] = Field(default_factory=list)
    supporting_context: List[PackageItem] = Field(default_factory=list)
    conflicts: List[PackageConflict] = Field(default_factory=list)
    coverage: PackageCoverage = Field(default_factory=PackageCoverage)
    unresolved_gaps: List[PackageGap] = Field(default_factory=list)
    excluded: Dict[str, int] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    plan: Dict[str, Any] = Field(default_factory=dict)
    created_at: str


def _trace_value(ve: ValidatedEvidence, name: str) -> Any:
    for t in ve.evaluation_traces:
        if t.evaluator_name == name:
            return t.signal_value
    return None


def _item(rank: int, ve: ValidatedEvidence, names: Dict[str, str]) -> PackageItem:
    c = ve.candidate
    meta = c.retrieval_metadata or {}
    auth = _trace_value(ve, "authority_freshness")
    rel = _trace_value(ve, "relevance_evaluator")
    return PackageItem(
        rank=rank,
        evidence_id=ve.evidence_id,
        content=c.content,
        score=round(float(c.score), 4),
        state=ve.state.value,
        matched_by=meta.get("matched_by"),
        round=int(meta.get("l7_round", 0) or 0),
        source=PackageSource(
            document_id=c.provenance.document_id,
            document_name=names.get(c.provenance.document_id),
            document_version_id=c.provenance.document_version_id,
            chunk_id=c.provenance.chunk_id,
            source_type=c.provenance.source_type,
            operator_type=c.provenance.operator_type.value,
            step_id=c.provenance.step_id,
        ),
        authority=auth.get("status") if isinstance(auth, dict) else None,
        relevance_coverage=rel.get("coverage") if isinstance(rel, dict) else None,
        relationships=[
            {"type": r.relation_type.value, "target": r.target_evidence_id, "reason": r.reason or ""}
            for r in ve.relationships
        ],
    )


def build_evidence_package(
    *,
    request_id: str,
    query: str,
    profile: str,
    final_evidence: Sequence[ValidatedEvidence],
    report: Any,                                  # SufficiencyReport
    last_validated: Optional[ValidatedEvidenceSet],
    document_names: Dict[str, str],
    documents_in_scope: int,
    scope_truncated: bool = False,
    plan: Optional[Dict[str, Any]] = None,
    extra_warnings: Iterable[str] = (),
) -> EvidencePackage:
    primary = [ve for ve in final_evidence if (ve.candidate.retrieval_metadata or {}).get("matched_by") != EXPANSION]
    supporting = [ve for ve in final_evidence if (ve.candidate.retrieval_metadata or {}).get("matched_by") == EXPANSION]

    all_validated: List[ValidatedEvidence] = list(last_validated.validated_evidence) if last_validated else []
    by_id = {ve.evidence_id: ve for ve in all_validated}

    # ---- conflicts: every CONTRADICTS relationship, once per pair ----------
    conflicts: List[PackageConflict] = []
    seen_pairs = set()
    for ve in all_validated:
        for rel in ve.relationships:
            if rel.relation_type != RelationshipType.CONTRADICTS:
                continue
            pair = tuple(sorted((ve.evidence_id, rel.target_evidence_id)))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            other = by_id.get(rel.target_evidence_id)
            conflicts.append(
                PackageConflict(
                    evidence_ids=list(pair),
                    chunk_ids=[
                        x.candidate.provenance.chunk_id for x in (ve, other) if x is not None
                    ],
                    reason=rel.reason or "Contradicting evidence",
                )
            )

    # ---- coverage ----------------------------------------------------------
    terms = significant_terms(query)
    joined = "\n".join(ve.candidate.content for ve in primary) if primary else ""
    ratio, covered, missing = term_coverage(query, joined)
    used_docs = list(dict.fromkeys(ve.candidate.provenance.document_id for ve in primary))
    coverage = PackageCoverage(
        query_terms=[s for _, s in terms],
        covered_terms=covered,
        uncovered_terms=missing,
        term_coverage=round(ratio if terms else 0.0, 3),
        documents_in_scope=documents_in_scope,
        scope_truncated=scope_truncated,
        documents_used=len(used_docs),
        document_ids_used=used_docs,
    )

    excluded = dict(Counter(ve.state.value for ve in all_validated if ve.state != EvidenceState.ACCEPTED))

    # ---- retrieval warnings -----------------------------------------------
    warnings: List[str] = list(extra_warnings)
    if conflicts:
        warnings.append(f"{len(conflicts)} conflict(s) between evidence items; both sides are listed under conflicts.")
    semantic_only = sum(
        1 for ve in primary if (_trace_value(ve, "relevance_evaluator") or {}).get("coverage", 1.0) == 0
    )
    if semantic_only:
        warnings.append(f"{semantic_only} evidence item(s) matched by meaning only (none of the question's words appear in them).")
    stale = sum(1 for ve in primary if _trace_value(ve, "authority_freshness") and
                (_trace_value(ve, "authority_freshness") or {}).get("status") == "unknown")
    if stale:
        warnings.append(f"{stale} evidence item(s) have no version information.")
    if last_validated is not None and getattr(last_validated, "unevaluated_count", 0):
        warnings.append(f"{last_validated.unevaluated_count} candidate(s) were not evaluated (candidate or time budget).")
    stop = getattr(report.stop_reason, "value", str(report.stop_reason))
    if stop in ("DEADLINE_EXCEEDED", "EXECUTION_ERROR", "MAX_ROUNDS_REACHED", "NO_PROGRESS") and \
            getattr(report.verdict, "value", str(report.verdict)) != "SUFFICIENT":
        warnings.append(f"Retrieval stopped early: {stop}.")

    gaps = [
        PackageGap(
            gap_type=getattr(g.gap_type, "value", str(g.gap_type)),
            severity=getattr(g.severity, "value", str(g.severity)),
            message=g.message,
        )
        for g in report.gaps
    ]

    return EvidencePackage(
        package_id="EVP-" + uuid.uuid4().hex[:12],
        request_id=request_id,
        query=query,
        profile=profile,
        verdict=getattr(report.verdict, "value", str(report.verdict)),
        sufficiency_score=round(float(report.score), 4),
        stop_reason=stop,
        rounds_executed=report.rounds_executed,
        evidence=[_item(i, ve, document_names) for i, ve in enumerate(primary, start=1)],
        supporting_context=[_item(i, ve, document_names) for i, ve in enumerate(supporting, start=1)],
        conflicts=conflicts,
        coverage=coverage,
        unresolved_gaps=gaps,
        excluded=excluded,
        warnings=list(dict.fromkeys(warnings)),
        plan=dict(plan or {}),
        created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        
    )