"""Rows for knowledge-pipeline integration tests: a project and its documents."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.database import SessionLocal
from app.core.enums import IngestionRunStatus
from app.knowledge.uploads.models import Document, DocumentVersion, IngestionRun, UploadJob
from app.project.models import Project


def new_id(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:14]}"


def naive_utc(delta=timedelta()) -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None) + delta


@pytest.fixture
def project(test_user):
    """A project with an upload; everything under it is removed afterwards."""
    project_id, upload_id = new_id("PT"), new_id("UT")
    db = SessionLocal()
    db.add(Project(project_id=project_id, user_id=test_user.user_id, name=project_id))
    db.flush()
    db.add(UploadJob(upload_id=upload_id, project_id=project_id, user_id=test_user.user_id))
    db.commit()
    db.close()

    yield {"project_id": project_id, "upload_id": upload_id, "user_id": test_user.user_id}

    db = SessionLocal()
    db.query(Document).filter(Document.project_id == project_id).delete(synchronize_session=False)
    db.query(UploadJob).filter(UploadJob.project_id == project_id).delete(synchronize_session=False)
    db.query(Project).filter(Project.project_id == project_id).delete(synchronize_session=False)
    db.commit()
    db.close()


def add_document(db, project, parent=None, status=IngestionRunStatus.PENDING, updated_at=None):
    """
    A document with one version and one ingestion run (flushed, not
    committed). Returns (document_id, ingestion_run_id, document_version_id).
    """
    doc_id, version_id, run_id = new_id("DT"), new_id("VT"), new_id("IT")
    db.add(Document(
        document_id=doc_id,
        project_id=project["project_id"],
        user_id=project["user_id"],
        upload_id=project["upload_id"],
        parent_document_id=parent,
        name=f"{doc_id}.txt",
        original_filename=f"{doc_id}.txt",
        mime_type="text/plain",
    ))
    db.flush()
    db.add(DocumentVersion(
        document_version_id=version_id,
        document_id=doc_id,
        version_number=1,
        file_name=f"{doc_id}.txt",
        mime_type="text/plain",
        file_size=1,
        sha256_hash="ab" * 32,
        source_type="UPLOAD",
    ))
    db.flush()
    run = IngestionRun(
        ingestion_run_id=run_id,
        document_id=doc_id,
        document_version_id=version_id,
        status=status,
    )
    if updated_at is not None:
        run.updated_at = updated_at
    db.add(run)
    db.flush()
    return doc_id, run_id, version_id
