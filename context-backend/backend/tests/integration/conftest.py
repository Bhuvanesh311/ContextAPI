"""
Integration tests: real Postgres (and Redis for the API test), as started by
dev.py / docker compose. Skipped automatically when Postgres is unreachable.

    python -m pytest tests/integration -q
"""

import uuid

import pytest
from sqlalchemy import text

from app.core.database import SessionLocal, engine
import app.core.models  # noqa: F401  -- register every mapped table for FKs


def _postgres_up() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


_PG_UP = _postgres_up()


def pytest_collection_modifyitems(config, items):
    if _PG_UP:
        return
    skip = pytest.mark.skip(reason="Postgres not reachable; start infra with dev.py")
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(skip)


def _uid(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:16]}"


@pytest.fixture
def make_user():
    """Create users on demand; they and their retrieval requests are removed after the test."""
    from app.auth.models import User
    from app.retrieval.models import RetrievalRequest

    created: list[str] = []

    def _make():
        user_id = _uid("IT")
        db = SessionLocal()
        db.add(User(
            user_id=user_id,
            email=f"{user_id.lower()}@integration.test",
            username=user_id.lower(),
            password_hash="x",
            is_verified=True,
        ))
        db.commit()
        user = db.get(User, user_id)
        db.expunge(user)
        db.close()
        created.append(user_id)
        return user

    yield _make

    db = SessionLocal()
    db.query(RetrievalRequest).filter(RetrievalRequest.user_id.in_(created)).delete(synchronize_session=False)
    db.query(User).filter(User.user_id.in_(created)).delete(synchronize_session=False)
    db.commit()
    db.close()


@pytest.fixture
def test_user(make_user):
    return make_user()


@pytest.fixture
def make_request():
    """Insert a retrieval_requests row; returns its request_id. Rows are cleaned up."""
    from app.core.enums import RequestSourceType, RetrievalRequestStatus
    from app.retrieval.models import RetrievalRequest

    created: list[str] = []

    def _make(status=RetrievalRequestStatus.PENDING, user_id=None) -> str:
        request_id = _uid("IT")
        db = SessionLocal()
        db.add(RetrievalRequest(
            request_id=request_id,
            source_type=RequestSourceType.USER,
            query="integration test",
            user_id=user_id,
            status=status,
        ))
        db.commit()
        db.close()
        created.append(request_id)
        return request_id

    yield _make

    db = SessionLocal()
    db.query(RetrievalRequest).filter(RetrievalRequest.request_id.in_(created)).delete(
        synchronize_session=False
    )
    db.commit()
    db.close()


def read_row(request_id: str):
    from app.retrieval.models import RetrievalRequest

    db = SessionLocal()
    row = db.query(RetrievalRequest).filter_by(request_id=request_id).one()
    db.expunge(row)
    db.close()
    return row
