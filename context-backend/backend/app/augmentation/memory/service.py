"""
L8 Memory Service — load and write memory for a single retrieval request.

load_memory()          → RelevantMemoryPackage  (fed into L9 prompt builder)
write_turn()           → stores current query+answer as a new session turn
write_evidence_chunks() → stores top evidence chunks from the current retrieval round
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.enums import RequestSourceType
from app.augmentation.memory.schemas import MemoryItem, MemorySourceType, RelevantMemoryPackage
from app.augmentation.memory.store import MemoryStore, get_memory_store
from app.augmentation.memory.relevance import score_relevance, compute_priority_score

logger = logging.getLogger(__name__)

_AGENT_SOURCE_TYPES = {
    RequestSourceType.AGENT,
    RequestSourceType.PLANNER_AGENT,
    RequestSourceType.WORKFLOW,
}

_MAX_EVIDENCE_STORED = 10    # top-N evidence chunks written per request


def _make_item(
    item_id: str,
    source_type: MemorySourceType,
    content: str,
    query: str,
    ts_str: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> MemoryItem:
    rel = score_relevance(query, content)
    pri = compute_priority_score(rel, source_type, ts_str)
    return MemoryItem(
        item_id=item_id,
        source_type=source_type,
        content=content,
        relevance_score=rel,
        priority_score=pri,
        metadata=metadata or {},
    )


def load_memory(
    query: str,
    correlation_id: Optional[str] = None,
    user_id: Optional[str] = None,
    actor_id: Optional[str] = None,
    source_type: Optional[RequestSourceType] = None,
    scope: Optional[Dict[str, Any]] = None,
    max_items: int = 5,
    store: Optional[MemoryStore] = None,
) -> RelevantMemoryPackage:
    """
    Fetch and rank memory from all four sources, filtered by scope.

    Falls back to an empty package on any Redis error so retrieval is never
    blocked by a memory-layer failure.
    """
    if store is None:
        store = get_memory_store()

    # --- Session (conversation turns) ---
    session_items: list[MemoryItem] = []
    if correlation_id:
        try:
            for i, turn in enumerate(store.load_turns(correlation_id, limit=max_items * 2, scope=scope, owner=user_id)):
                q, ans = turn.get("query", ""), turn.get("answer_summary", "")
                content = f"Q: {q} A: {ans}" if ans else f"Q: {q}"
                session_items.append(_make_item(
                    f"sess_{i}", MemorySourceType.SESSION, content, query,
                    ts_str=turn.get("ts", ""),
                    metadata={"request_id": turn.get("request_id", ""), "ts": turn.get("ts", "")},
                ))
        except Exception as exc:
            logger.warning("L08 session memory load failed: %s", exc)

    # --- Long-term (user facts) ---
    long_term_items: list[MemoryItem] = []
    if user_id:
        try:
            for i, fact in enumerate(store.load_facts(user_id, scope=scope)):
                content = fact.get("content", "")
                item = _make_item(f"lt_{i}", MemorySourceType.LONG_TERM, content, query,
                                  metadata=fact.get("metadata", {}))
                if item.relevance_score > 0:
                    long_term_items.append(item)
        except Exception as exc:
            logger.warning("L08 long-term memory load failed: %s", exc)

    # --- Agent / workflow state ---
    agent_items: list[MemoryItem] = []
    if actor_id and source_type in _AGENT_SOURCE_TYPES:
        try:
            for i, entry in enumerate(store.load_agent(actor_id, scope=scope)):
                content = entry.get("content", "")
                agent_items.append(_make_item(
                    f"agent_{i}", MemorySourceType.AGENT, content, query,
                    metadata=entry.get("metadata", {}),
                ))
        except Exception as exc:
            logger.warning("L08 agent memory load failed: %s", exc)

    # --- Shared evidence (prior retrieval rounds) ---
    evidence_items: list[MemoryItem] = []
    if correlation_id:
        try:
            for i, chunk in enumerate(store.load_evidence_chunks(correlation_id, limit=max_items, scope=scope, owner=user_id)):
                doc_name = chunk.get("document_name") or chunk.get("document_id", "")
                snippet  = chunk.get("content_snippet", "")
                content  = f"[Evidence from {doc_name}] {snippet}"
                evidence_items.append(_make_item(
                    f"evid_{i}", MemorySourceType.EVIDENCE, content, query,
                    ts_str=chunk.get("ts", ""),
                    metadata={"chunk_id": chunk.get("chunk_id"), "document_id": chunk.get("document_id")},
                ))
        except Exception as exc:
            logger.warning("L08 evidence memory load failed: %s", exc)

    # Sort and cap each category by priority_score
    def _top(items: list[MemoryItem]) -> list[MemoryItem]:
        return sorted(items, key=lambda x: x.priority_score, reverse=True)[:max_items]

    session_items   = _top(session_items)
    long_term_items = _top(long_term_items)
    agent_items     = _top(agent_items)
    evidence_items  = _top(evidence_items)

    all_items    = session_items + long_term_items + agent_items + evidence_items
    total_tokens = sum(max(1, len(item.content) // 4) for item in all_items)

    return RelevantMemoryPackage(
        session_items=session_items,
        long_term_items=long_term_items,
        agent_items=agent_items,
        evidence_items=evidence_items,
        total_items=len(all_items),
        total_tokens=total_tokens,
    )


def write_turn(
    correlation_id: str,
    query: str,
    request_id: str,
    answer_summary: str = "",
    scope: Optional[Dict[str, Any]] = None,
    store: Optional[MemoryStore] = None,
    user_id: Optional[str] = None,
) -> None:
    """Append the current turn to session memory. No-op when correlation_id is absent."""
    if not correlation_id:
        return
    if store is None:
        store = get_memory_store()
    try:
        store.append_turn(correlation_id, {
            "query": query,
            "answer_summary": answer_summary[:200] if answer_summary else "",
            "request_id": request_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            "scope": scope or {},
        }, owner=user_id)
    except Exception as exc:
        logger.warning("L08 write_turn failed for correlation_id=%s: %s", correlation_id, exc)


def write_evidence_chunks(
    correlation_id: str,
    request_id: str,
    evidence: List[Any],           # List[PackageItem] from EvidencePackage
    scope: Optional[Dict[str, Any]] = None,
    store: Optional[MemoryStore] = None,
    user_id: Optional[str] = None,
) -> None:
    """Store top evidence chunks from the current retrieval round for future turns."""
    if not correlation_id or not evidence:
        return
    if store is None:
        store = get_memory_store()
    try:
        now = datetime.now(timezone.utc).isoformat()
        chunks = []
        for item in evidence[:_MAX_EVIDENCE_STORED]:
            chunks.append({
                "chunk_id":       item.source.chunk_id,
                "document_id":    item.source.document_id,
                "document_name":  item.source.document_name,
                "content_snippet": item.content[:300],
                "score":          item.score,
                "request_id":     request_id,
                "ts":             now,
                "scope":          scope or {},
            })
        store.append_evidence_chunks(correlation_id, chunks, owner=user_id)
    except Exception as exc:
        logger.warning("L08 write_evidence_chunks failed for correlation_id=%s: %s", correlation_id, exc)
