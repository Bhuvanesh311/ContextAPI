from typing import Dict, List, Optional
import hashlib

from app.retrieval.evidence.enums import EvidenceState
from app.retrieval.evidence.models import ValidatedEvidence, EvidenceRelationship, RelationshipType
from app.retrieval.evidence.evaluators.pairwise import BasePairwiseEvaluator

_SKIP_STATES = frozenset((
    EvidenceState.REJECTED,
    EvidenceState.INVALID,
    EvidenceState.DUPLICATE,
    EvidenceState.CONFLICTING,
))


class EvidenceDeduplicator:
    def __init__(self, exact_only: bool = True, semantic_evaluator: Optional[BasePairwiseEvaluator] = None):
        self.exact_only = exact_only
        self.semantic_evaluator = semantic_evaluator

    def process(self, validated_evidences: List[ValidatedEvidence]) -> List[ValidatedEvidence]:
        retained_evidences: List[ValidatedEvidence] = []
        processed: List[ValidatedEvidence] = []
        # Cache SHA256 hash per evidence_id to avoid O(n²) hash recomputation.
        _hash_cache: Dict[str, str] = {}

        def _content_hash(ev: ValidatedEvidence) -> str:
            if ev.evidence_id not in _hash_cache:
                _hash_cache[ev.evidence_id] = hashlib.sha256(
                    ev.candidate.content.strip().encode("utf-8")
                ).hexdigest()
            return _hash_cache[ev.evidence_id]

        for ev in validated_evidences:
            if ev.state in _SKIP_STATES:
                processed.append(ev)
                continue

            is_dup = False
            content_hash = _content_hash(ev)

            for retained_ev in retained_evidences:
                retained_hash = _content_hash(retained_ev)  # O(1): already cached

                if content_hash == retained_hash:
                    rel = EvidenceRelationship(
                        target_evidence_id=retained_ev.evidence_id,
                        relation_type=RelationshipType.DUPLICATES,
                        reason="Exact content hash match",
                    )
                    dup_ev = ev.model_copy(update={
                        "state": EvidenceState.DUPLICATE,
                        "primary_reason": f"Exact duplicate of {retained_ev.evidence_id}",
                        "relationships": ev.relationships + (rel,),
                    })
                    processed.append(dup_ev)
                    is_dup = True
                    break

                # Near-duplicate (semantic) check if configured
                if not self.exact_only and self.semantic_evaluator:
                    try:
                        trace = self.semantic_evaluator.evaluate_pair(ev.candidate, retained_ev.candidate)
                        if trace.is_duplicate:
                            rel = EvidenceRelationship(
                                target_evidence_id=retained_ev.evidence_id,
                                relation_type=RelationshipType.DUPLICATES,
                                reason=f"Semantic near-duplicate (score {trace.score:.2f}): {trace.reason}",
                            )
                            dup_ev = ev.model_copy(update={
                                "state": EvidenceState.DUPLICATE,
                                "primary_reason": f"Semantic near-duplicate of {retained_ev.evidence_id}",
                                "relationships": ev.relationships + (rel,),
                            })
                            processed.append(dup_ev)
                            is_dup = True
                            break
                    except Exception:
                        pass  # graceful degradation: skip near-dup check on error

            if not is_dup:
                retained_evidences.append(ev)
                processed.append(ev)

        return processed
