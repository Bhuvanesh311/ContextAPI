"""Deleting a project removes everything under it (real Postgres)."""

import uuid

import pytest

from app.core.database import SessionLocal
from app.core.enums import EnvironmentEnum, RequestSourceType
from app.knowledge.uploads.models import Document, DocumentVersion, UploadJob
from app.project import services as project_services
from app.project.models import Project
from app.retrieval.models import RetrievalRequest
from app.target_application.models import TargetApplication


def _id(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:14]}"


@pytest.fixture
def purged(monkeypatch):
    """Captures what delete_project hands to the storage/vector cleanup."""
    calls = []
    monkeypatch.setattr(
        project_services,
        "purge_stored_files",
        lambda objects, version_ids: calls.append((objects, version_ids)),
    )
    return calls


def _project_with_everything(user_id: str) -> dict:
    ids = {
        "project": _id("PT"),
        "upload": _id("UT"),
        "archive": _id("DT"),
        "member": _id("DT"),
        "archive_v": _id("VT"),
        "member_v": _id("VT"),
        "request": _id("RT"),
        "target": _id("TT"),
    }
    db = SessionLocal()
    db.add(Project(project_id=ids["project"], user_id=user_id, name=ids["project"]))
    db.flush()
    db.add(UploadJob(upload_id=ids["upload"], project_id=ids["project"], user_id=user_id))
    db.flush()

    # An archive and one of its members (a child document).
    for doc, parent in (("archive", None), ("member", ids["archive"])):
        db.add(Document(
            document_id=ids[doc],
            project_id=ids["project"],
            user_id=user_id,
            upload_id=ids["upload"],
            parent_document_id=parent,
            name=f"{doc}.txt",
            original_filename=f"{doc}.txt",
            mime_type="text/plain",
        ))
        db.flush()
        db.add(DocumentVersion(
            document_version_id=ids[f"{doc}_v"],
            document_id=ids[doc],
            version_number=1,
            file_name=f"{doc}.txt",
            mime_type="text/plain",
            file_size=1,
            sha256_hash="ab" * 32,
            source_type="UPLOAD",
            permanent_bucket="knowledge",
            permanent_object_key=f"{doc}/key",
        ))
        db.flush()

    db.add(RetrievalRequest(
        request_id=ids["request"],
        project_id=ids["project"],
        user_id=user_id,
        source_type=RequestSourceType.USER,
    ))
    db.add(TargetApplication(
        target_application_id=ids["target"],
        project_id=ids["project"],
        base_url="https://example.test",
        environment=EnvironmentEnum.TESTING,
    ))
    db.commit()
    db.close()
    return ids


def test_delete_project_with_documents_removes_everything(test_user, purged):
    ids = _project_with_everything(test_user.user_id)

    db = SessionLocal()
    try:
        result = project_services.delete_project(
            db=db, project_id=ids["project"], current_user=test_user,
        )
    finally:
        db.close()

    assert result.message == "Project deleted successfully."

    db = SessionLocal()
    try:
        assert db.get(Project, ids["project"]) is None
        assert db.get(UploadJob, ids["upload"]) is None
        assert db.query(Document).filter(
            Document.document_id.in_([ids["archive"], ids["member"]])
        ).count() == 0
        assert db.query(DocumentVersion).filter(
            DocumentVersion.document_version_id.in_([ids["archive_v"], ids["member_v"]])
        ).count() == 0
        assert db.query(RetrievalRequest).filter(
            RetrievalRequest.request_id == ids["request"]
        ).count() == 0
        assert db.get(TargetApplication, ids["target"]) is None
    finally:
        db.close()

    # Stored files and vectors of both documents are cleaned up afterwards.
    [(objects, version_ids)] = purged
    assert sorted(objects) == [("knowledge", "archive/key"), ("knowledge", "member/key")]
    assert sorted(version_ids) == sorted([ids["archive_v"], ids["member_v"]])


def test_delete_empty_project(test_user, purged):
    project_id = _id("PT")
    db = SessionLocal()
    db.add(Project(project_id=project_id, user_id=test_user.user_id, name=project_id))
    db.commit()

    try:
        project_services.delete_project(db=db, project_id=project_id, current_user=test_user)
        assert db.get(Project, project_id) is None
    finally:
        db.close()

    assert purged == [([], [])]
