"""
API smoke test: POST -> 202 PENDING -> worker task -> terminal status -> GET
-> cancel. Uses real Postgres and Redis (rate limiter). The Celery broker is
replaced by calling the task inline with the exact kwargs the router enqueued.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.enums import RetrievalRequestStatus as S


@pytest.fixture
def client(test_user):
    from app.auth.dependencies import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_retrieval_request_round_trip(client, test_user):
    from app.retrieval.tasks import run_retrieval_task

    with patch.object(run_retrieval_task, "apply_async") as enqueue:
        resp = client.post(
            "/api/v1/retrieval/requests",
            json={"instruction": "what is the refund policy", "profile": "FAST"},
        )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == S.PENDING.value
    enqueue.assert_called_once()
    kwargs = enqueue.call_args.kwargs["kwargs"]
    assert kwargs["request_id"] == body["request_id"]

    run_retrieval_task(**kwargs)

    status_resp = client.get(f"/api/v1/retrieval/requests/{body['request_id']}/status")
    assert status_resp.status_code == 200
    final = status_resp.json()["status"]
    assert final not in (S.PENDING.value, S.RUNNING.value)

    cancel_resp = client.post(f"/api/v1/retrieval/requests/{body['request_id']}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == final


def test_other_users_request_is_not_visible(client, make_request):
    request_id = make_request(user_id=None)
    resp = client.get(f"/api/v1/retrieval/requests/{request_id}")
    assert resp.status_code == 404


def test_unknown_project_gets_generic_error(client):
    from app.retrieval.tasks import run_retrieval_task

    with patch.object(run_retrieval_task, "apply_async") as enqueue:
        resp = client.post(
            "/api/v1/retrieval/requests",
            json={"instruction": "what is the refund policy", "project_id": "PROJ999999"},
        )
    assert resp.status_code == 202, resp.text
    run_retrieval_task(**enqueue.call_args.kwargs["kwargs"])

    body = client.get(f"/api/v1/retrieval/requests/{resp.json()['request_id']}").json()
    assert body["status"] == S.FAILED.value
    assert body["error_code"] == "PROJECT_NOT_FOUND_OR_DENIED"
    assert "PROJ999999" not in (body["error_message"] or "")


def test_broker_down_marks_request_failed_not_pending(client):
    from app.retrieval.tasks import run_retrieval_task

    with patch.object(run_retrieval_task, "apply_async", side_effect=ConnectionError("broker down")):
        resp = client.post(
            "/api/v1/retrieval/requests",
            json={"instruction": "what is the refund policy"},
        )
    assert resp.status_code == 503, resp.text
    assert resp.json()["status"] == S.FAILED.value
    assert resp.json()["error_code"] == "QUEUE_UNAVAILABLE"


def test_idempotency_key_is_scoped_per_user(client, test_user, make_user):
    import uuid
    from app.auth.dependencies import get_current_user
    from app.main import app
    from app.retrieval.tasks import run_retrieval_task

    key = f"key-{uuid.uuid4().hex[:8]}"

    def post(request_id):
        return client.post(
            "/api/v1/retrieval/requests",
            json={
                "instruction": "what is the refund policy",
                "lifecycle": {"request_id": request_id, "idempotency_key": key},
            },
        )

    with patch.object(run_retrieval_task, "apply_async"):
        first = post(f"IT{uuid.uuid4().hex[:16]}")
        assert first.status_code == 202, first.text

        # Same user, same key, new request id -> the original request (200).
        again = post(f"IT{uuid.uuid4().hex[:16]}")
        assert again.status_code == 200
        assert again.json()["request_id"] == first.json()["request_id"]

        # Another user with the same key is not blocked.
        other = make_user()
        app.dependency_overrides[get_current_user] = lambda: other
        second = post(f"IT{uuid.uuid4().hex[:16]}")
        assert second.status_code == 202, second.text
        assert second.json()["request_id"] != first.json()["request_id"]


def test_budget_is_accepted_and_request_id_is_server_issued(client):
    from app.retrieval.tasks import run_retrieval_task
    from tests.integration.conftest import read_row

    with patch.object(run_retrieval_task, "apply_async"):
        resp = client.post(
            "/api/v1/retrieval/requests",
            json={
                "instruction": "what is the refund policy",
                "max_latency_ms": 5000,
                "max_tokens": 200,
                "max_cost": 0.01,
                "lifecycle": {"request_id": "client-chosen-1"},
            },
        )
    assert resp.status_code == 202, resp.text
    request_id = resp.json()["request_id"]
    assert request_id.startswith("req_") and request_id != "client-chosen-1"

    row = read_row(request_id)
    assert (row.max_latency_ms, row.max_tokens, float(row.max_cost)) == (5000, 200, 0.01)


@pytest.mark.parametrize("field,value", [("max_latency_ms", 10), ("max_tokens", 0), ("max_cost", -1)])
def test_invalid_budget_is_rejected(client, field, value):
    resp = client.post("/api/v1/retrieval/requests", json={"instruction": "q", field: value})
    assert resp.status_code == 422
