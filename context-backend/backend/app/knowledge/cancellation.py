"""
Stopping a document's ingestion/indexing on request.

The API marks the document's runs CANCELLED, sets a Redis flag per document
version, and kills the Celery task working on it:

- Ingestion runs on a prefork worker, so its task process is killed outright
  (mid-parse, mid-scan or mid-LLM call), and its parser sandbox is removed.
- Indexing runs on a threads worker, which cannot kill a task; the pipeline
  polls the flag between stages and between chunks while embedding.

Queued tasks are revoked, and a task that still starts sees the flag (or the
CANCELLED run) and stops before doing anything.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_FLAG_KEY = "contextapi:cancelled:{}"   # per document version
_TASK_KEY = "contextapi:task:{}"        # per ingestion / processing run
_TTL_SECONDS = 24 * 3600

CANCELLED_CODE = "CANCELLED"
CANCELLED_MESSAGE = "Stopped by user."


class ProcessingCancelled(Exception):
    """Raised inside the pipeline when its document was stopped."""


def _redis():
    from app.infra.redis.client import redis_client

    return redis_client


def remember_task(run_id: str, task_id: str | None) -> None:
    """Record which Celery task is working on a run, so it can be killed."""
    if not task_id:
        return
    try:
        _redis().set(_TASK_KEY.format(run_id), task_id, ex=_TTL_SECONDS)
    except Exception:
        logger.warning("Could not record the task of run %s", run_id, exc_info=True)


def task_for(run_id: str) -> str | None:
    try:
        return _redis().get(_TASK_KEY.format(run_id))
    except Exception:
        logger.warning("Could not look up the task of run %s", run_id, exc_info=True)
        return None


def mark_cancelled(version_ids: list[str]) -> None:
    if not version_ids:
        return
    try:
        pipe = _redis().pipeline()
        for version_id in version_ids:
            pipe.set(_FLAG_KEY.format(version_id), "1", ex=_TTL_SECONDS)
        pipe.execute()
    except Exception:
        # The CANCELLED runs in the database still stop the pipeline between
        # stages; only the faster in-stage check is lost.
        logger.warning("Could not set cancel flags", exc_info=True)


def is_cancelled(version_id: str | None) -> bool:
    if not version_id:
        return False
    try:
        return bool(_redis().exists(_FLAG_KEY.format(version_id)))
    except Exception:
        return False


def raise_if_cancelled(version_id: str | None) -> None:
    if is_cancelled(version_id):
        raise ProcessingCancelled(version_id)
