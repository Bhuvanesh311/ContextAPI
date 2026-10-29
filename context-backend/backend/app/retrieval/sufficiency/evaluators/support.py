import statistics
import time
from typing import Any, List

from app.retrieval.engine.enums import ExecutionStatus


def _is_hybrid(matched_by: Any) -> bool:
    """Return True when a chunk was found by more than one retriever."""
    if matched_by is None:
        return False
    if isinstance(matched_by, (list, tuple, set, frozenset)):
        return len(matched_by) > 1
    return "+" in str(matched_by)
from app.retrieval.evidence.enums import EvidenceState
from app.retrieval.sufficiency.enums import SignalName
from app.retrieval.sufficiency.evaluators.base import AssessmentInput, BaseSufficiencyEvaluator
from app.retrieval.sufficiency.models import SufficiencySignal


def _ms(start: float) -> int:
    return int((time.time() - start) * 1000)


class EvidenceQuantityEvaluator(BaseSufficiencyEvaluator):
    """Enough accepted pieces of evidence for this kind of question?"""

    @property
    def name(self) -> SignalName:
        return SignalName.EVIDENCE_QUANTITY

    def evaluate(self, inp: AssessmentInput) -> SufficiencySignal:
        start = time.time()
        target = self.config.evidence_target(inp.query.complexity, inp.top_k)
        count = len(inp.accepted)
        return SufficiencySignal(
            signal_name=self.name,
            value=min(1.0, count / target),
            target=1.0,
            reason=f"{count} accepted evidence, {target} wanted",
            details={"accepted": count, "wanted": target},
            latency_ms=_ms(start),
        )


class SourceDiversityEvaluator(BaseSufficiencyEvaluator):
    """Comparison / relationship questions need more than one document."""

    @property
    def name(self) -> SignalName:
        return SignalName.SOURCE_DIVERSITY

    def evaluate(self, inp: AssessmentInput) -> SufficiencySignal:
        start = time.time()
        wanted = self.config.source_target(inp.query.intent, inp.query.available_documents)
        if wanted <= 1:
            return SufficiencySignal(
                signal_name=self.name,
                applicable=False,
                reason="One source is enough for this kind of question",
                latency_ms=_ms(start),
            )
        documents = {ev.candidate.provenance.document_id for ev in inp.accepted}
        return SufficiencySignal(
            signal_name=self.name,
            value=min(1.0, len(documents) / wanted),
            target=1.0,
            reason=f"{len(documents)} documents, {wanted} wanted",
            details={"documents": len(documents), "wanted": wanted},
            latency_ms=_ms(start),
        )


class ContentAdequacyEvaluator(BaseSufficiencyEvaluator):
    """Guards against a pile of tiny chunks (headings, fragments)."""

    @property
    def name(self) -> SignalName:
        return SignalName.CONTENT_ADEQUACY

    def evaluate(self, inp: AssessmentInput) -> SufficiencySignal:
        start = time.time()
        lengths: List[int] = [len(ev.candidate.content.strip()) for ev in inp.accepted]
        total = sum(lengths)
        return SufficiencySignal(
            signal_name=self.name,
            value=min(1.0, total / self.config.min_total_chars),
            target=1.0,
            reason=f"{total} characters of evidence, {self.config.min_total_chars} wanted",
            details={
                "total_chars": total,
                "median_chunk_chars": int(statistics.median(lengths)) if lengths else 0,
            },
            latency_ms=_ms(start),
        )


class RetrievalConsensusEvaluator(BaseSufficiencyEvaluator):
    """
    Hybrid search records which retrievers found each chunk ("matched_by").
    A chunk found by BOTH semantic and lexical search is stronger evidence.
    Only measurable for hybrid results.
    """

    @property
    def name(self) -> SignalName:
        return SignalName.RETRIEVAL_CONSENSUS

    def evaluate(self, inp: AssessmentInput) -> SufficiencySignal:
        start = time.time()
        labelled = [
            ev for ev in inp.accepted
            if (ev.candidate.retrieval_metadata or {}).get("matched_by")
        ]
        if not labelled:
            return SufficiencySignal(
                signal_name=self.name,
                applicable=False,
                reason="No hybrid retrieval labels on the evidence",
                latency_ms=_ms(start),
            )
        top = sorted(labelled, key=lambda ev: ev.candidate.score, reverse=True)[
            : self.config.consensus_top_n
        ]
        both = sum(1 for ev in top if _is_hybrid(ev.candidate.retrieval_metadata.get("matched_by")))
        return SufficiencySignal(
            signal_name=self.name,
            value=both / len(top),
            target=self.config.min_consensus,
            reason=f"{both} of top {len(top)} evidence found by both semantic and lexical search",
            details={"found_by_both": both, "checked": len(top)},
            latency_ms=_ms(start),
        )


class ExecutionHealthEvaluator(BaseSufficiencyEvaluator):
    """Did the retrieval steps of the latest round actually run?"""

    @property
    def name(self) -> SignalName:
        return SignalName.EXECUTION_HEALTH

    def evaluate(self, inp: AssessmentInput) -> SufficiencySignal:
        start = time.time()
        latest: Any = inp.latest_round
        traces = latest.traces
        failed = [t for t in traces if t.status == ExecutionStatus.FAILED]

        if latest.fatal_error or latest.status == ExecutionStatus.FAILED:
            value = 0.0
        elif traces:
            value = (len(traces) - len(failed)) / len(traces)
        else:
            value = 1.0

        return SufficiencySignal(
            signal_name=self.name,
            value=value,
            target=1.0,
            reason=(
                latest.fatal_error
                or f"{len(traces) - len(failed)} of {len(traces)} retrieval steps succeeded"
            ),
            details={
                "status": latest.status.value,
                "failed_steps": len(failed),
                "errors": [t.error_message for t in failed if t.error_message][:3],
            },
            latency_ms=_ms(start),
        )


class EvidenceConflictEvaluator(BaseSufficiencyEvaluator):
    """Reports evidence that L06 flagged as contradicting itself."""

    @property
    def name(self) -> SignalName:
        return SignalName.EVIDENCE_CONFLICT

    def evaluate(self, inp: AssessmentInput) -> SufficiencySignal:
        start = time.time()
        conflicting = [ev for ev in inp.all_validated if ev.state == EvidenceState.CONFLICTING]
        if not conflicting:
            return SufficiencySignal(
                signal_name=self.name,
                applicable=False,
                reason="No conflicting evidence",
                latency_ms=_ms(start),
            )
        total = len(conflicting) + len(inp.accepted)
        return SufficiencySignal(
            signal_name=self.name,
            value=1.0 - (len(conflicting) / total),
            target=1.0,
            reason=f"{len(conflicting)} evidence items conflict with each other",
            details={"conflicting": len(conflicting)},
            latency_ms=_ms(start),
        )
