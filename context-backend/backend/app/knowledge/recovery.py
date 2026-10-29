"""
Beat job: recover ingestion and knowledge-processing runs that nothing will
ever finish.

A run is left behind when the worker running it dies (OOM, restart, deploy),
when a delayed retry message is lost with the broker, or when a queued run's
message never reached a worker. Such runs are queued
again; when they are out of retries they are failed, and the document is
marked FAILED with a reason the user can see.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.core.database import SessionLocal
from app.core.enums import (
    DocumentStatus,
    IngestionRunStatus,
    KnowledgeProcessingRunStatus,
)
from app.infra.celery.app import celery_app

logger = logging.getLogger(__name__)

# Longer than any healthy run can go without updating its row:
# a parse is capped at 5 minutes, OCR included.
INGESTION_STALE_AFTER = timedelta(minutes=15)
# Embedding a large document can take a while between stage updates.
PROCESSING_STALE_AFTER = timedelta(minutes=30)
# A retry that should have started this long ago was lost.
RETRY_LOST_AFTER = timedelta(minutes=3)
# A run that was queued this long ago and never started lost its message.
# Re-queueing one that is merely waiting is harmless: the orchestrator only
# starts a run it can claim, so the second task skips it.
PENDING_LOST_AFTER = timedelta(minutes=10)

WORKER_LOST_MESSAGE = "The worker stopped while processing this document."


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _fail_document(db, document_id: str) -> None:
    from app.knowledge.uploads.models import Document

    document = db.query(Document).filter(Document.document_id == document_id).first()
    if document is not None and document.status == DocumentStatus.ACTIVE:
        document.status = DocumentStatus.FAILED
        document.updated_at = _now()


def recover_ingestion_runs(db) -> int:
    from app.knowledge.uploads.models import IngestionRun
    from app.knowledge.uploads.tasks import run_ingestion_task

    now = _now()
    stuck_running = (
        db.query(IngestionRun)
        .filter(
            IngestionRun.status == IngestionRunStatus.RUNNING,
            IngestionRun.updated_at < now - INGESTION_STALE_AFTER,
        )
        # Rows locked by a task that is still working are alive: skip them
        # instead of waiting for the lock.
        .with_for_update(skip_locked=True)
        .all()
    )
    lost_retries = (
        db.query(IngestionRun)
        .filter(
            IngestionRun.status == IngestionRunStatus.RETRYING,
            (IngestionRun.next_retry_at.is_(None)) | (IngestionRun.next_retry_at < now - RETRY_LOST_AFTER),
        )
        # Rows locked by a task that is still working are alive: skip them
        # instead of waiting for the lock.
        .with_for_update(skip_locked=True)
        .all()
    )

    lost_pending = (
        db.query(IngestionRun)
        .filter(
            IngestionRun.status == IngestionRunStatus.PENDING,
            IngestionRun.started_at.is_(None),
            IngestionRun.updated_at < now - PENDING_LOST_AFTER,
        )
        .with_for_update(skip_locked=True)
        .all()
    )

    to_queue: list[str] = []
    for run in stuck_running:
        if run.retry_count >= run.max_retries:
            run.status = IngestionRunStatus.FAILED
            run.error_code = "WORKER_LOST"
            run.error_message = WORKER_LOST_MESSAGE
            run.next_retry_at = None
            run.updated_at = now
            _fail_document(db, run.document_id)
            continue
        run.retry_count += 1
        run.attempt_number += 1
        run.status = IngestionRunStatus.RETRYING
        run.next_retry_at = now
        run.updated_at = now
        to_queue.append(run.ingestion_run_id)

    for run in lost_retries:
        run.next_retry_at = now
        run.updated_at = now
        to_queue.append(run.ingestion_run_id)

    # updated_at moves on, so a run still waiting is not queued every pass.
    for run in lost_pending:
        run.updated_at = now
        to_queue.append(run.ingestion_run_id)

    db.commit()
    for run_id in to_queue:
        run_ingestion_task.apply_async(kwargs={"ingestion_run_id": run_id})
    return len(stuck_running) + len(lost_retries) + len(lost_pending)


def recover_processing_runs(db) -> int:
    from app.knowledge.processing.services.lifecycle import KnowledgeProcessingLifecycleService
    from app.knowledge.processing.tasks.processing import run_knowledge_processing_task
    from app.knowledge.uploads.models import DocumentVersion, KnowledgeProcessingRun

    now = _now()
    lifecycle = KnowledgeProcessingLifecycleService(db)
    stuck_running = (
        db.query(KnowledgeProcessingRun)
        .filter(
            KnowledgeProcessingRun.status == KnowledgeProcessingRunStatus.RUNNING,
            KnowledgeProcessingRun.updated_at < now - PROCESSING_STALE_AFTER,
        )
        # Rows locked by a task that is still working are alive: skip them
        # instead of waiting for the lock.
        .with_for_update(skip_locked=True)
        .all()
    )
    lost_retries = (
        db.query(KnowledgeProcessingRun)
        .filter(
            KnowledgeProcessingRun.status == KnowledgeProcessingRunStatus.RETRYING,
            (KnowledgeProcessingRun.next_retry_at.is_(None))
            | (KnowledgeProcessingRun.next_retry_at < now - RETRY_LOST_AFTER),
            KnowledgeProcessingRun.updated_at < now - RETRY_LOST_AFTER,
        )
        # Rows locked by a task that is still working are alive: skip them
        # instead of waiting for the lock.
        .with_for_update(skip_locked=True)
        .all()
    )

    to_queue: list[str] = []
    for run in stuck_running:
        if run.retry_count >= run.max_retries:
            run.status = KnowledgeProcessingRunStatus.FAILED
            run.error_code = "WORKER_LOST"
            run.error_message = WORKER_LOST_MESSAGE
            run.next_retry_at = None
            version = db.query(DocumentVersion).filter(
                DocumentVersion.document_version_id == run.document_version_id
            ).first()
            if version is not None:
                _fail_document(db, version.document_id)
            continue
        lifecycle.mark_retrying(
            run=run,
            error_code="WORKER_LOST",
            error_message=WORKER_LOST_MESSAGE,
            next_retry_at=now,
        )
        to_queue.append(run.knowledge_processing_run_id)

    for run in lost_retries:
        run.next_retry_at = now
        run.updated_at = now
        to_queue.append(run.knowledge_processing_run_id)

    db.commit()
    for run_id in to_queue:
        run_knowledge_processing_task.delay(run_id)
    return len(stuck_running) + len(lost_retries)


@celery_app.task(name="knowledge.recover_stuck_runs")
def recover_stuck_runs_task() -> int:
    db = SessionLocal()
    try:
        recovered = recover_ingestion_runs(db) + recover_processing_runs(db)
        if recovered:
            logger.warning("Recovered %d stuck ingestion/processing run(s)", recovered)
        return recovered
    except Exception:
        db.rollback()
        logger.exception("Stuck-run recovery failed")
        raise
    finally:
        db.close()
