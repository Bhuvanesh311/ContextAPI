"""
L05 cross-encoder reranker.

Replaces retrieval scores (RRF / cosine distance) with relevance scores
produced by a cross-encoder model so that L06 and L07 work with a better
signal. The reranker runs after L05 execution, before L06 validation.

Only activated when the profile's allow_rerank flag is True
(STANDARD, DEEP, COLLABORATIVE — not FAST).

Model: BAAI/bge-reranker-base (same vendor family as BAAI/bge-m3).
      Override via RERANKER_MODEL in .env if needed.
"""

import logging
import os
import threading
from typing import Dict, List, Optional

from app.core.config import settings
from app.retrieval.engine.schemas import CandidateEvidence
from app.retrieval.engine.timeouts import CallTimeoutError, budgeted_timeout, call_with_timeout

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-base")
_DEFAULT_MAX_CANDIDATES = 50

# Module-level cache — model is loaded once and reused across requests.
_model_cache: Dict[str, object] = {}
_load_lock = threading.Lock()


def _load_model(model_name: str):
    with _load_lock:
        if model_name not in _model_cache:
            from sentence_transformers import CrossEncoder  # deferred: avoid import-time cost
            logger.info("Loading reranker model '%s' (first request)", model_name)
            _model_cache[model_name] = CrossEncoder(model_name)
            logger.info("Reranker model '%s' loaded", model_name)
    return _model_cache[model_name]


def preload_reranker_model(model_name: str = _DEFAULT_MODEL) -> None:
    """Warm up the reranker cache at startup so the first scored request isn't slow."""
    try:
        _load_model(model_name)
    except Exception:
        logger.warning(
            "Could not preload reranker model '%s' — first rerank call will load it",
            model_name,
            exc_info=True,
        )


class BGEReranker:
    """
    Cross-encoder reranker backed by sentence-transformers.

    Call rerank(query, candidates) after L05 execution. The returned list
    is sorted by relevance score (highest first). The score field on each
    CandidateEvidence is replaced with the cross-encoder score so downstream
    layers (L06, L07) see a calibrated relevance signal instead of an RRF
    score.

    Candidates beyond max_candidates are appended at the end unchanged so
    the caller always gets back exactly as many items as it passed in.

    Graceful degradation: if the model fails to load or score, the original
    candidates are returned in their original order with a warning logged.
    """

    def __init__(
        self,
        model_name: str = _DEFAULT_MODEL,
        max_candidates: int = _DEFAULT_MAX_CANDIDATES,
    ):
        self.model_name = model_name
        self.max_candidates = max_candidates

    def rerank(
        self,
        query: str,
        candidates: List[CandidateEvidence],
        deadline: Optional[float] = None,
    ) -> List[CandidateEvidence]:
        if not candidates or not query.strip():
            return candidates

        to_score = candidates[: self.max_candidates]
        remainder = candidates[self.max_candidates :]

        try:
            model = _load_model(self.model_name)
            pairs = [(query, c.content) for c in to_score]
            # predict() can't be interrupted; stop waiting and keep original order.
            raw_scores = call_with_timeout(
                model.predict,
                budgeted_timeout(settings.RETRIEVAL_RERANK_TIMEOUT_SECONDS, deadline),
                pairs,
            )
        except CallTimeoutError as exc:
            logger.warning("Reranker skipped (%s); keeping original order", exc)
            return candidates
        except Exception:
            logger.exception(
                "Reranker model '%s' failed; returning candidates in original order",
                self.model_name,
            )
            return candidates

        scored = sorted(
            zip(to_score, raw_scores),
            key=lambda x: float(x[1]),
            reverse=True,
        )
        reranked = [
            c.model_copy(update={"score": float(s)})
            for c, s in scored
        ]
        return reranked + list(remainder)
