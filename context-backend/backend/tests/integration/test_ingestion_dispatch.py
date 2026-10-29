"""
Archive members must never be left PENDING forever (real Postgres):
children are queued only after their runs are committed, a run is claimed by
exactly one task, and recovery re-queues runs whose message was lost.
"""

from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.database import SessionLocal, engine
from app.core.enums import IngestionRunStatus
from app.knowledge import recovery
from app.knowledge.security.presecurityrunner import PreSecurityResult
from app.knowledge.uploads import tasks
from app.knowledge.uploads.ingestion.context import IngestionContext
from app.knowledge.uploads.ingestion.handlers import pre_security_validation
from app.knowledge.uploads.ingestion_orchestrator import IngestionOrchestrator
from app.knowledge.uploads.models import Document, IngestionRun

from .knowledge_rows import add_document, naive_utc, project  # noqa: F401  (fixture)


def test_archive_children_are_queued_only_after_commit(project, monkeypatch):
    queued = []
    monkeypatch.setattr(tasks.run_ingestion_task, "delay", lambda run_id: queued.append(run_id))

    db = SessionLocal()
    try:
        archive_id, archive_run_id, _ = add_document(db, project)
        db.commit()
        # Pre-security extracts the members: their rows are only flushed.
        children = [add_document(db, project, parent=archive_id)[:2] for _ in range(3)]

        class Runner:
            def __init__(self, db):
                pass

            def run(self, document, document_version):
                return PreSecurityResult(
                    document_id=archive_id,
                    success=True,
                    is_archive=True,
                    child_document_ids=[doc_id for doc_id, _ in children],
                )

        monkeypatch.setattr(pre_security_validation, "PreSecurityRunner", Runner)
        context = IngestionContext(
            db=db,
            run=db.get(IngestionRun, archive_run_id),
            document=db.get(Document, archive_id),
            document_version=None,
        )
        pre_security_validation.PreSecurityValidationHandler().execute(context)

        assert queued == []  # a worker could not see these rows yet
        db.commit()
        assert sorted(queued) == sorted(run_id for _, run_id in children)

        # Every queued run is visible to another session (the worker's).
        other = SessionLocal()
        try:
            assert other.query(IngestionRun).filter(
                IngestionRun.ingestion_run_id.in_(queued)
            ).count() == 3
        finally:
            other.close()
    finally:
        db.close()


def test_run_is_claimed_by_one_task_only(project):
    db = SessionLocal()
    try:
        _, run_id, _ = add_document(db, project)
        db.commit()
        first = IngestionOrchestrator(db=db)
        assert first._start_run(db.get(IngestionRun, run_id)) is True
        assert db.get(IngestionRun, run_id).status == IngestionRunStatus.RUNNING
    finally:
        db.close()

    # A duplicate task arriving now skips the run instead of processing it again.
    db = SessionLocal()
    try:
        result = IngestionOrchestrator(db=db).run(ingestion_run_id=run_id)
        assert result.status == IngestionRunStatus.RUNNING
        assert result.current_stage.value == "UPLOAD_RECEIVED"
    finally:
        db.close()


def test_recovery_requeues_pending_runs_that_never_started(project, monkeypatch):
    queued = []
    monkeypatch.setattr(
        tasks.run_ingestion_task,
        "apply_async",
        lambda kwargs, **_: queued.append(kwargs["ingestion_run_id"]),
    )

    # Recovery scans every run in the database: keep its changes inside a
    # transaction that is rolled back, so other data is never touched.
    connection = engine.connect()
    outer = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        _, lost, _ = add_document(db, project, updated_at=naive_utc(-timedelta(minutes=30)))
        _, waiting, _ = add_document(db, project)  # queued just now
        db.commit()

        recovery.recover_ingestion_runs(db)

        assert lost in queued
        assert waiting not in queued

        # Re-queued once, not again on the next pass.
        queued.clear()
        recovery.recover_ingestion_runs(db)
        assert lost not in queued
    finally:
        db.close()
        outer.rollback()
        connection.close()
