from typing import List, Dict, Any
import time
from pydantic import BaseModel

from app.retrieval.engine.schemas import CandidateEvidenceSet
from app.retrieval.evidence.models import ValidatedEvidenceSet, ValidatedEvidence, EvidenceEvaluationTrace
from app.retrieval.evidence.enums import EvidenceState
from app.retrieval.evidence.evaluators.base import BaseEvaluator
from app.retrieval.evidence.policy import EvidencePolicy
from app.retrieval.evidence.deduplication import EvidenceDeduplicator
from app.retrieval.evidence.conflict import EvidenceConflictAnalyzer

class EvidenceIntelligenceConfig(BaseModel):
    max_candidates: int = 50
    max_evaluator_calls_per_candidate: int = 5
    max_total_latency_ms: int = 5000
    exact_deduplication_only: bool = True

from app.retrieval.evidence.evaluators.pairwise import BasePairwiseEvaluator

class EvidenceIntelligenceService:
    def __init__(self, evaluators: List[BaseEvaluator], policy: EvidencePolicy, config: EvidenceIntelligenceConfig = None, semantic_evaluator: BasePairwiseEvaluator = None):
        self.evaluators = evaluators
        self.policy = policy
        self.config = config or EvidenceIntelligenceConfig()
        self.deduplicator = EvidenceDeduplicator(exact_only=self.config.exact_deduplication_only, semantic_evaluator=semantic_evaluator)
        self.conflict_analyzer = EvidenceConflictAnalyzer()

    def process(self, candidate_set: CandidateEvidenceSet, context: Dict[str, Any]) -> ValidatedEvidenceSet:
        validated_list: List[ValidatedEvidence] = []
        
        start_time = time.time()
        
        # The profile's candidate budget (L02) wins over the service default.
        limit = int(context.get("max_candidates") or self.config.max_candidates)
        candidates_to_process = candidate_set.candidates[:limit]
        
        for candidate in candidates_to_process:
            if (time.time() - start_time) * 1000 > self.config.max_total_latency_ms:
                # Budget exhausted, we could log and break, leaving remainder unprocessed
                break
                
            traces = []
            
            evaluators_to_run = self.evaluators[:self.config.max_evaluator_calls_per_candidate]
            
            for evaluator in evaluators_to_run:
                try:
                    trace = evaluator.evaluate(candidate, context)
                    traces.append(trace)
                except Exception as e:
                    traces.append(EvidenceEvaluationTrace(
                        evaluator_name=evaluator.name,
                        signal_type="error",
                        signal_value=None,
                        reason=f"Evaluator error: {str(e)}",
                        latency_ms=0
                    ))
                    
            state, reason = self.policy.determine_state(candidate, traces)
            
            validated_list.append(ValidatedEvidence(
                evidence_id=candidate.evidence_id,
                candidate=candidate,
                state=state,
                primary_reason=reason,
                evaluation_traces=tuple(traces)
            ))
            
        # Every candidate that was not evaluated: cut by the candidate cap or
        # by the time budget. Both are reported, never silently dropped.
        unevaluated_count = len(candidate_set.candidates) - len(validated_list)

        freshness = {
            version_id: info.get("updated_at")
            for version_id, info in (context.get("version_info") or {}).items()
        }
        validated_list = self.deduplicator.process(validated_list)
        validated_list = self.conflict_analyzer.process(validated_list, freshness=freshness)

        return ValidatedEvidenceSet(
            plan_id=candidate_set.plan_id,
            original_candidates_count=len(candidate_set.candidates),
            unevaluated_count=unevaluated_count,
            validated_evidence=tuple(validated_list),
        )
