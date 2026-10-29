"""
Live progress of a running retrieval request, for clients that show it.

The worker writes the current stage and the answer text generated so far to
Redis; GET /requests/{id}/answer reads them while the request is still
running. Progress is best effort: a Redis failure never fails a request, it
only means the client sees no live text until the answer is stored.
"""

import logging
import time
from typing import Callable, Optional, Tuple

from app.infra.redis.client import redis_client

logger = logging.getLogger(__name__)

_TTL_SECONDS = 15 * 60
# Writing every token would flood Redis; clients poll about once a second.
_MIN_WRITE_INTERVAL = 0.4

STAGE_INDEXING = "indexing"
STAGE_SEARCHING = "searching"
STAGE_WRITING = "writing"


def _key(request_id: str) -> str:
    return f"retrieval:progress:{request_id}"


def set_stage(request_id: str, stage: str) -> None:
    try:
        pipe = redis_client.pipeline()
        pipe.hset(_key(request_id), mapping={"stage": stage})
        pipe.expire(_key(request_id), _TTL_SECONDS)
        pipe.execute()
    except Exception as exc:
        logger.debug("progress stage write failed for %s: %s", request_id, exc)


def partial_writer(request_id: str) -> Callable[[str], None]:
    """Returns a callback that stores the answer text so far, throttled."""
    last = [0.0]

    def write(text: str, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - last[0] < _MIN_WRITE_INTERVAL:
            return
        last[0] = now
        try:
            pipe = redis_client.pipeline()
            pipe.hset(_key(request_id), mapping={"stage": STAGE_WRITING, "partial": text})
            pipe.expire(_key(request_id), _TTL_SECONDS)
            pipe.execute()
        except Exception as exc:
            logger.debug("progress text write failed for %s: %s", request_id, exc)

    return write


def read(request_id: str) -> Tuple[Optional[str], Optional[str]]:
    """(stage, partial answer) for a running request, or (None, None)."""
    try:
        data = redis_client.hgetall(_key(request_id)) or {}
    except Exception as exc:
        logger.debug("progress read failed for %s: %s", request_id, exc)
        return None, None
    return data.get("stage") or None, data.get("partial") or None


def clear(request_id: str) -> None:
    try:
        redis_client.delete(_key(request_id))
    except Exception as exc:
        logger.debug("progress clear failed for %s: %s", request_id, exc)
