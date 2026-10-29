import time
from typing import List, Set

from app.retrieval.sufficiency.enums import SignalName
from app.retrieval.sufficiency.evaluators.base import AssessmentInput, BaseSufficiencyEvaluator
from app.retrieval.sufficiency.models import SufficiencySignal
from app.retrieval.sufficiency.text import significant_terms, stem, tokens


def evidence_stems(inp: AssessmentInput) -> Set[str]:
    """Every word (stemmed) found in the accepted evidence."""
    found: Set[str] = set()
    for ev in inp.accepted:
        found.update(stem(t) for t in tokens(ev.candidate.content))
    return found


class TermCoverageEvaluator(BaseSufficiencyEvaluator):
    """How many of the question's topic words appear in the accepted evidence."""

    @property
    def name(self) -> SignalName:
        return SignalName.TERM_COVERAGE

    def evaluate(self, inp: AssessmentInput) -> SufficiencySignal:
        start = time.time()
        terms = significant_terms(inp.query.query_text)
        if not terms:
            return SufficiencySignal(
                signal_name=self.name,
                applicable=False,
                reason="Query has no topic words to check",
                latency_ms=int((time.time() - start) * 1000),
            )

        found = evidence_stems(inp)
        covered: List[str] = [surface for surface, st in terms if st in found]
        uncovered: List[str] = [surface for surface, st in terms if st not in found]
        value = len(covered) / len(terms)

        return SufficiencySignal(
            signal_name=self.name,
            value=value,
            target=self.config.coverage_target(inp.query.complexity),
            reason=f"{len(covered)} of {len(terms)} query terms found in evidence",
            details={"covered_terms": covered, "uncovered_terms": uncovered},
            latency_ms=int((time.time() - start) * 1000),
        )


class SubqueryCoverageEvaluator(BaseSufficiencyEvaluator):
    """For decomposed questions: is every sub-question answered by something?"""

    @property
    def name(self) -> SignalName:
        return SignalName.SUBQUERY_COVERAGE

    def evaluate(self, inp: AssessmentInput) -> SufficiencySignal:
        start = time.time()
        subqueries = inp.query.subqueries
        if not subqueries:
            return SufficiencySignal(
                signal_name=self.name,
                applicable=False,
                reason="Query was not decomposed",
                latency_ms=int((time.time() - start) * 1000),
            )

        found = evidence_stems(inp)
        uncovered: List[str] = []
        for sub in subqueries:
            terms = significant_terms(sub)
            if not terms:
                continue  # nothing checkable, do not punish
            hit = sum(1 for _, st in terms if st in found)
            if hit / len(terms) < self.config.min_subquery_term_coverage:
                uncovered.append(sub)

        value = (len(subqueries) - len(uncovered)) / len(subqueries)
        return SufficiencySignal(
            signal_name=self.name,
            value=value,
            target=1.0,
            reason=f"{len(subqueries) - len(uncovered)} of {len(subqueries)} sub-questions covered",
            details={"uncovered_subqueries": uncovered},
            latency_ms=int((time.time() - start) * 1000),
        )
