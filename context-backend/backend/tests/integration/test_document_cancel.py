"""Stopping a document's processing (real Postgres and Redis)."""

import pytest
from fastapi import HTTPException

from app.core.database import SessionLocal
from app.core.enums import DocumentStatus, IngestionRunStatus, KnowledgeProcessingRunStatus
from app.infra.celery.app import celery_app
from app.infra.redis.client import redis_client
from app.knowledge import cancellation
from app.knowledge.processing.tasks.processing import run_knowledge_processing_task
from app.knowledge.uploads import services
from app.knowledge.uploads.ingestion_orchestrator import IngestionOrchestrator
from app.knowledge.uploads.mapper import map_document_response
from app.knowledge.uploads.models import Document, DocumentVersion, IngestionRun, KnowledgeProcessingRun

from .knowledge_rows import add_document, new_id, project  # noqa: F401  (fixture)


@pytest.fixture
def celery_calls(monkeypatch):
    """Records revokes and sent tasks instead of talking to the workers."""
    calls = {"revoke": [], "send_task": []}
    monkeypatch.setattr(
        celery_app.control, "revoke",
        lambda task_id, **kwargs: calls["revoke"].append((task_id, kwargs)),
    )
    monkeypatch.setattr(
        celery_app, "send_task",
        lambda name, **kwargs: calls["send_task"].append(name),
    )
    monkeypatch.setattr(services, "purge_stored_files", lambda objects, version_ids: None)
    return calls


@pytest.fixture
def flags():
    """Removes the Redis keys a test leaves behind."""
    keys = []
    yield keys
    if keys:
        redis_client.delete(*keys)


def _cancel(user, document_id):
    db = SessionLocal()
    try:
        return services.cancel_document(db=db, current_user=user, document_id=document_id)
    finally:
        db.close()


def test_stopping_a_running_ingestion_kills_its_task(project, test_user, celery_calls, flags):
    db = SessionLocal()
    doc_id, run_id, version_id = add_document(db, project, status=IngestionRunStatus.RUNNING)
    db.commit()
    db.close()
    cancellation.remember_task(run_id, "task-123")
    flags += [f"contextapi:task:{run_id}", f"contextapi:cancelled:{version_id}"]

    _cancel(test_user, doc_id)

    # The worker process is killed, and its parser sandbox cleaned up.
    assert celery_calls["revoke"] == [("task-123", {"terminate": True, "signal": "SIGKILL"})]
    assert celery_calls["send_task"] == ["knowledge.cleanup_sandboxes"]
    assert cancellation.is_cancelled(version_id)

    db = SessionLocal()
    try:
        run = db.get(IngestionRun, run_id)
        assert run.status == IngestionRunStatus.CANCELLED
        assert run.error_message == "Stopped by user."
        document = db.get(Document, doc_id)
        assert document.status == DocumentStatus.FAILED

        db.get(Document, doc_id).current_version_id = version_id
        db.flush()
        shown = map_document_response(db.get(Document, doc_id))
        assert (shown.indexing_status, shown.status_reason) == ("CANCELLED", "Stopped by user.")
        db.rollback()
    finally:
        db.close()


def test_stopping_an_archive_stops_members_in_progress_only(project, test_user, celery_calls, flags):
    db = SessionLocal()
    archive_id, _, _ = add_document(db, project, status=IngestionRunStatus.COMPLETED)
    done_id, _, done_version = add_document(db, project, parent=archive_id, status=IngestionRunStatus.COMPLETED)
    db.add(KnowledgeProcessingRun(
        knowledge_processing_run_id=new_id("KT"),
        document_version_id=done_version,
        status=KnowledgeProcessingRunStatus.COMPLETED,
    ))
    busy_id, busy_run, busy_version = add_document(db, project, parent=archive_id, status=IngestionRunStatus.PENDING)
    db.commit()
    db.close()
    flags += [f"contextapi:cancelled:{v}" for v in (done_version, busy_version)]

    _cancel(test_user, archive_id)

    # A queued run has no task yet: nothing to kill, it never starts.
    assert celery_calls["revoke"] == []

    db = SessionLocal()
    try:
        assert db.get(IngestionRun, busy_run).status == IngestionRunStatus.CANCELLED
        assert db.get(Document, busy_id).status == DocumentStatus.FAILED
        # Already indexed members stay searchable.
        assert db.get(Document, done_id).status == DocumentStatus.ACTIVE
        assert db.get(Document, archive_id).status == DocumentStatus.ACTIVE
    finally:
        db.close()


def test_stopping_indexing_revokes_without_killing_the_thread(project, test_user, celery_calls, flags):
    db = SessionLocal()
    doc_id, _, version_id = add_document(db, project, status=IngestionRunStatus.COMPLETED)
    processing_id = new_id("KT")
    db.add(KnowledgeProcessingRun(
        knowledge_processing_run_id=processing_id,
        document_version_id=version_id,
        status=KnowledgeProcessingRunStatus.RUNNING,
    ))
    db.commit()
    db.close()
    cancellation.remember_task(processing_id, "embed-1")
    flags += [f"contextapi:task:{processing_id}", f"contextapi:cancelled:{version_id}"]

    _cancel(test_user, doc_id)

    assert celery_calls["revoke"] == [("embed-1", {})]
    assert celery_calls["send_task"] == []
    db = SessionLocal()
    try:
        assert db.get(KnowledgeProcessingRun, processing_id).status == KnowledgeProcessingRunStatus.CANCELLED
        assert db.get(Document, doc_id).status == DocumentStatus.FAILED
    finally:
        db.close()


def test_nothing_to_stop_is_a_conflict(project, test_user, celery_calls):
    db = SessionLocal()
    doc_id, _, _ = add_document(db, project, status=IngestionRunStatus.COMPLETED)
    db.commit()
    db.close()

    with pytest.raises(HTTPException) as error:
        _cancel(test_user, doc_id)
    assert error.value.status_code == 409


def test_queued_ingestion_of_a_stopped_document_does_not_run(project, flags):
    db = SessionLocal()
    _, run_id, version_id = add_document(db, project)
    db.commit()
    cancellation.mark_cancelled([version_id])
    flags.append(f"contextapi:cancelled:{version_id}")

    try:
        run = IngestionOrchestrator(db=db).run(ingestion_run_id=run_id)
        assert run.status == IngestionRunStatus.CANCELLED
        assert run.current_stage.value == "UPLOAD_RECEIVED"  # no stage ran
    finally:
        db.close()


def test_indexing_task_of_a_stopped_document_records_the_stop(project, flags):
    db = SessionLocal()
    _, _, version_id = add_document(db, project, status=IngestionRunStatus.COMPLETED)
    processing_id = new_id("KT")
    db.add(KnowledgeProcessingRun(
        knowledge_processing_run_id=processing_id,
        document_version_id=version_id,
        status=KnowledgeProcessingRunStatus.PENDING,
    ))
    db.commit()
    db.close()
    cancellation.mark_cancelled([version_id])
    flags.append(f"contextapi:cancelled:{version_id}")

    # Runs inline: stops without retrying.
    run_knowledge_processing_task.run(processing_id)

    db = SessionLocal()
    try:
        run = db.get(KnowledgeProcessingRun, processing_id)
        assert run.status == KnowledgeProcessingRunStatus.CANCELLED
        assert run.error_message == "Stopped by user."
    finally:
        db.close()
