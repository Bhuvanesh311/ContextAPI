"""
L8 Memory Store — Redis-backed read/write for the four memory layers.

Key patterns
    Session   : memory:session:{owner}:{correlation_id}   → Redis list (LPUSH)
    Long-term : memory:lt:{user_id}:{fact_key}            → Redis string (JSON)
    Agent     : memory:agent:{actor_id}:{key}             → Redis string (JSON)
    Evidence  : memory:evidence:{owner}:{correlation_id}  → Redis list (LPUSH)

correlation_id comes from the client, so session and evidence keys are
namespaced by the owning user: another user reusing the same correlation_id
gets a different key and can never read this conversation.

Scope filtering: every stored item carries a "scope" dict in its payload.
load_* methods accept an optional scope dict and skip items that don't match.

Accepts a Redis client in __init__ so tests can inject a mock.
Use get_memory_store() for the production singleton.
"""

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SESSION_TTL   = 3_600        # 1 hour
LONG_TERM_TTL = 2_592_000    # 30 days
AGENT_TTL     = 86_400       # 24 hours

_MAX_TURNS          = 20     # max session turns per correlation_id
_MAX_EVIDENCE_CHUNKS = 20    # max evidence chunks per correlation_id


class MemoryStore:
    def __init__(self, redis) -> None:
        self._r = redis

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _session_key(correlation_id: str, owner: Optional[str]) -> str:
        return f"memory:session:{owner}:{correlation_id}" if owner else f"memory:session:{correlation_id}"

    @staticmethod
    def _evidence_key(correlation_id: str, owner: Optional[str]) -> str:
        return f"memory:evidence:{owner}:{correlation_id}" if owner else f"memory:evidence:{correlation_id}"

    def _scan_keys(self, pattern: str) -> List[str]:
        # SCAN, not KEYS: KEYS walks the whole keyspace and blocks Redis.
        return list(self._r.scan_iter(match=pattern, count=200))

    @staticmethod
    def _matches_scope(item_scope: Dict[str, Any], required_scope: Dict[str, Any]) -> bool:
        """True when every key in required_scope matches item_scope."""
        if not required_scope:
            return True
        for k, v in required_scope.items():
            if item_scope.get(k) != v:
                return False
        return True

    def _load_list_filtered(
        self,
        key: str,
        fetch_limit: int,
        result_limit: int,
        scope: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Shared helper: read a Redis list, parse JSON, apply scope filter."""
        raw = self._r.lrange(key, 0, fetch_limit - 1)
        result: List[Dict[str, Any]] = []
        for item in raw:
            try:
                parsed = json.loads(item)
                if scope and not self._matches_scope(parsed.get("scope", {}), scope):
                    continue
                result.append(parsed)
                if len(result) >= result_limit:
                    break
            except (json.JSONDecodeError, TypeError):
                logger.debug("Skipping malformed memory item in %s", key)
        return result

    # ------------------------------------------------------------------
    # Session (conversation turns)
    # ------------------------------------------------------------------

    def append_turn(self, correlation_id: str, turn: Dict[str, Any], owner: Optional[str] = None) -> None:
        key = self._session_key(correlation_id, owner)
        pipe = self._r.pipeline(transaction=True)
        pipe.lpush(key, json.dumps(turn))
        pipe.ltrim(key, 0, _MAX_TURNS - 1)
        pipe.expire(key, SESSION_TTL)
        pipe.execute()

    def load_turns(
        self,
        correlation_id: str,
        limit: int = 10,
        scope: Optional[Dict[str, Any]] = None,
        owner: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return self._load_list_filtered(
            self._session_key(correlation_id, owner),
            fetch_limit=limit * 4,
            result_limit=limit,
            scope=scope,
        )

    # ------------------------------------------------------------------
    # Long-term (cross-session user facts)
    # ------------------------------------------------------------------

    def write_fact(self, user_id: str, fact_key: str, content: str, metadata: Dict[str, Any]) -> None:
        key = f"memory:lt:{user_id}:{fact_key}"
        self._r.set(key, json.dumps({"content": content, "metadata": metadata}), ex=LONG_TERM_TTL)

    def load_facts(
        self,
        user_id: str,
        scope: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        keys = self._scan_keys(f"memory:lt:{user_id}:*")
        result: List[Dict[str, Any]] = []
        for k in keys:
            raw = self._r.get(k)
            if raw:
                try:
                    parsed = json.loads(raw)
                    if scope and not self._matches_scope(parsed.get("metadata", {}).get("scope", {}), scope):
                        continue
                    result.append(parsed)
                except (json.JSONDecodeError, TypeError):
                    logger.debug("Skipping malformed long-term memory item")
        return result

    # ------------------------------------------------------------------
    # Agent / workflow state
    # ------------------------------------------------------------------

    def write_agent(self, actor_id: str, key_suffix: str, content: str, metadata: Dict[str, Any]) -> None:
        key = f"memory:agent:{actor_id}:{key_suffix}"
        self._r.set(key, json.dumps({"content": content, "metadata": metadata}), ex=AGENT_TTL)

    def load_agent(
        self,
        actor_id: str,
        scope: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        keys = self._scan_keys(f"memory:agent:{actor_id}:*")
        result: List[Dict[str, Any]] = []
        for k in keys:
            raw = self._r.get(k)
            if raw:
                try:
                    parsed = json.loads(raw)
                    if scope and not self._matches_scope(parsed.get("metadata", {}).get("scope", {}), scope):
                        continue
                    result.append(parsed)
                except (json.JSONDecodeError, TypeError):
                    logger.debug("Skipping malformed agent memory item")
        return result

    # ------------------------------------------------------------------
    # Shared evidence (prior retrieval rounds)
    # ------------------------------------------------------------------

    def append_evidence_chunks(
        self, correlation_id: str, chunks: List[Dict[str, Any]], owner: Optional[str] = None
    ) -> None:
        key = self._evidence_key(correlation_id, owner)
        pipe = self._r.pipeline(transaction=True)
        for chunk in chunks:
            pipe.lpush(key, json.dumps(chunk))
        pipe.ltrim(key, 0, _MAX_EVIDENCE_CHUNKS - 1)
        pipe.expire(key, SESSION_TTL)
        pipe.execute()

    def load_evidence_chunks(
        self,
        correlation_id: str,
        limit: int = 10,
        scope: Optional[Dict[str, Any]] = None,
        owner: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return self._load_list_filtered(
            self._evidence_key(correlation_id, owner),
            fetch_limit=limit * 4,
            result_limit=limit,
            scope=scope,
        )


_store: Optional[MemoryStore] = None


def get_memory_store() -> MemoryStore:
    global _store
    if _store is None:
        from app.infra.redis.client import redis_client
        _store = MemoryStore(redis_client)
    return _store
