from datetime import datetime
from typing import Dict, List, Mapping, Optional

from app.retrieval.evidence.contradiction import find_contradiction
from app.retrieval.evidence.enums import EvidenceState
from app.retrieval.evidence.models import EvidenceRelationship, RelationshipType, ValidatedEvidence
from app.retrieval.textutil import jaccard, stem_set

MAX_COMPARED = 30            # only the best-ranked accepted evidence is compared
TOPIC_PREFILTER_JACCARD = 0.15


class EvidenceConflictAnalyzer:
    """
    Detects evidence that contradicts other evidence.

    1. Same chunk id with different content (data integrity problem).
    2. Different chunks whose matching statements disagree on a number or
       negate each other (see contradiction.py).

    The more recently updated document stays ACCEPTED and the other becomes
    CONFLICTING; with no (or equal) freshness information the better-ranked
    item wins. Both get a CONTRADICTS relationship, so the EvidencePackage can
    show both sides of every conflict instead of silently picking one.
    """

    def process(
        self,
        validated_evidences: List[ValidatedEvidence],
        freshness: Optional[Mapping[str, Optional[datetime]]] = None,
    ) -> List[ValidatedEvidence]:
        freshness = freshness or {}

        def updated(ev: ValidatedEvidence) -> Optional[datetime]:
            return freshness.get(ev.candidate.provenance.document_version_id)

        def winner_loser(better_ranked: ValidatedEvidence, other: ValidatedEvidence):
            a, b = updated(better_ranked), updated(other)
            if a is not None and b is not None and b > a:
                return other, better_ranked
            return better_ranked, other

        items = list(validated_evidences)
        new_state: Dict[str, EvidenceState] = {}
        new_reason: Dict[str, str] = {}
        relations: Dict[str, List[EvidenceRelationship]] = {}

        def link(a: ValidatedEvidence, b: ValidatedEvidence, reason: str) -> None:
            relations.setdefault(a.evidence_id, []).append(
                EvidenceRelationship(target_evidence_id=b.evidence_id, relation_type=RelationshipType.CONTRADICTS, reason=reason)
            )
            relations.setdefault(b.evidence_id, []).append(
                EvidenceRelationship(target_evidence_id=a.evidence_id, relation_type=RelationshipType.CONTRADICTS, reason=reason)
            )
            new_state[b.evidence_id] = EvidenceState.CONFLICTING
            new_reason[b.evidence_id] = f"Conflicts with {a.evidence_id}: {reason}"

        accepted = [ev for ev in items if ev.state == EvidenceState.ACCEPTED][:MAX_COMPARED]
        topic = {ev.evidence_id: stem_set(ev.candidate.content) for ev in accepted}

        for j, later in enumerate(accepted):
            for earlier in accepted[:j]:
                if earlier.evidence_id in new_state:      # already lost a conflict
                    continue
                if later.evidence_id in new_state:
                    break
                same_chunk = (
                    later.candidate.provenance.chunk_id
                    and later.candidate.provenance.chunk_id == earlier.candidate.provenance.chunk_id
                )
                if same_chunk:
                    if later.candidate.content.strip() != earlier.candidate.content.strip():
                        link(earlier, later, "Same chunk id but different content")
                    continue
                if jaccard(topic[earlier.evidence_id], topic[later.evidence_id]) < TOPIC_PREFILTER_JACCARD:
                    continue
                reason = find_contradiction(earlier.candidate.content, later.candidate.content)
                if reason:
                    winner, loser = winner_loser(earlier, later)
                    link(winner, loser, reason)

        result: List[ValidatedEvidence] = []
        for ev in items:
            update = {}
            if ev.evidence_id in relations:
                update["relationships"] = ev.relationships + tuple(relations[ev.evidence_id])
            if ev.evidence_id in new_state:
                update["state"] = new_state[ev.evidence_id]
                update["primary_reason"] = new_reason[ev.evidence_id]
            result.append(ev.model_copy(update=update) if update else ev)
        return result