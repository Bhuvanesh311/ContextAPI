"""
Request-state behaviour against real Postgres: cancel races between the API
and the worker (two sessions = two connections), worker claim, and deadline.
"""

import threading
import time
from datetime import datetime, timedelta, timezone

from app.core.database import RetrievalSessionLocal, SessionLocal
from app.core.enums import RequestSourceType, RetrievalRequestStatus as S
from app.retrieval.canonical.schemas import RetrievalContract
from app.retrieval.models import RetrievalRequest
from app.retrieval.schemas import ActorModel, LifecycleContext
from app.retrieval.service import cancel_if_active, commit_unless_cancelled, run_retrieval

from tests.integration.conftest import read_row


def _load(db, request_id):
    return db.query(RetrievalRequest).filter_by(request_id=request_id).one()


def test_cancel_committed_during_run_wins_and_discards_results(make_request):
    request_id = make_request(status=S.RUNNING)
    worker, api = RetrievalSessionLocal(), SessionLocal()
    try:
        w_req = _load(worker, request_id)
        w_req.status = S.COMPLETED
        w_req.results = [{"rank": 1}]

        assert cancel_if_active(api, _load(api, request_id).id) is True
        assert commit_unless_cancelled(worker, w_req) is False
    finally:
        worker.close()
        api.close()

    row = read_row(request_id)
    assert row.status == S.CANCELLED
    assert row.results is None
    assert row.cancelled_at is not None


def test_cancel_arriving_during_final_commit_waits_then_noops(make_request):
    request_id = make_request(status=S.RUNNING)
    worker, api = RetrievalSessionLocal(), SessionLocal()
    outcome = {}
    try:
        w_req = _load(worker, request_id)
        pk = w_req.id
        w_req.status = S.COMPLETED
        # Same lock commit_unless_cancelled takes, held open so the cancel
        # can be started while the worker is mid-finalize.
        with worker.no_autoflush:
            worker.query(RetrievalRequest.status).filter(
                RetrievalRequest.id == pk
            ).with_for_update().scalar()

        t = threading.Thread(target=lambda: outcome.setdefault("ok", cancel_if_active(api, pk)))
        t.start()
        time.sleep(0.5)
        assert t.is_alive(), "cancel should block on the worker's row lock"

        worker.commit()
        t.join(timeout=10)
        assert not t.is_alive()
    finally:
        worker.close()
        api.close()

    assert outcome["ok"] is False
    assert read_row(request_id).status == S.COMPLETED


def test_cancel_on_finished_request_is_noop(make_request):
    request_id = make_request(status=S.COMPLETED)
    api = SessionLocal()
    try:
        assert cancel_if_active(api, _load(api, request_id).id) is False
    finally:
        api.close()
    assert read_row(request_id).status == S.COMPLETED


def test_worker_does_not_overwrite_cancel_with_running(make_request):
    request_id = make_request(status=S.CANCELLED)
    db = RetrievalSessionLocal()
    try:
        run_retrieval(db, _load(db, request_id), canonical=None)
    finally:
        db.close()
    row = read_row(request_id)
    assert row.status == S.CANCELLED
    assert row.started_at is None


def test_deadline_already_passed_fails_through_task(make_request):
    from app.retrieval.tasks import run_retrieval_task

    request_id = make_request(status=S.PENDING)
    canonical = RetrievalContract(
        request_id=request_id,
        query="what is the refund policy",
        source_type=RequestSourceType.USER,
        actor=ActorModel(actor_type="USER", actor_id="nobody"),
        lifecycle=LifecycleContext(
            request_id=request_id,
            deadline=datetime.now(timezone.utc) - timedelta(seconds=5),
        ),
    )

    run_retrieval_task(request_id=request_id, canonical_dict=canonical.model_dump(mode="json"))

    row = read_row(request_id)
    assert row.status == S.FAILED
    assert row.error_code == "DEADLINE_EXCEEDED"
    assert row.started_at is not None


def test_statement_timeout_applies_to_retrieval_sessions():
    from sqlalchemy import text
    from app.core.config import settings

    db = RetrievalSessionLocal()
    try:
        value = db.execute(text("SHOW statement_timeout")).scalar()
    finally:
        db.close()
    assert value in (f"{settings.RETRIEVAL_DB_STATEMENT_TIMEOUT_MS}ms",
                     f"{settings.RETRIEVAL_DB_STATEMENT_TIMEOUT_MS // 1000}s")


def test_stale_pending_and_running_requests_are_failed(make_request):
    from datetime import timedelta as td
    from app.retrieval.service import fail_stale_requests

    old_pending = make_request(status=S.PENDING)
    old_running = make_request(status=S.RUNNING)
    fresh_pending = make_request(status=S.PENDING)

    long_ago = datetime.now(timezone.utc).replace(tzinfo=None) - td(hours=1)
    db = SessionLocal()
    try:
        db.query(RetrievalRequest).filter_by(request_id=old_pending).update({"created_at": long_ago})
        db.query(RetrievalRequest).filter_by(request_id=old_running).update({"started_at": long_ago})
        db.commit()
        assert fail_stale_requests(db) >= 2
    finally:
        db.close()

    assert (read_row(old_pending).status, read_row(old_pending).error_code) == (S.FAILED, "QUEUE_TIMEOUT")
    assert (read_row(old_running).status, read_row(old_running).error_code) == (S.FAILED, "WORKER_LOST")
    assert read_row(fresh_pending).status == S.PENDING


def test_searchable_documents_query_runs_against_real_schema():
    from app.retrieval.security.resolver import _searchable_documents

    db = SessionLocal()
    try:
        assert _searchable_documents(db, "PROJ_DOES_NOT_EXIST", {}) == []
    finally:
        db.close()
