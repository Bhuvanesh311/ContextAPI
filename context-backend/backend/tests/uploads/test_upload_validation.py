"""
POST /upload/ rejects bad requests before storing anything: a project the
caller does not own, too many files, and files ingestion would reject anyway.
"""

import io
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, UploadFile

from app.knowledge.uploads import services
from app.knowledge.uploads.constants import MAX_FILE_SIZE, MAX_FILES_PER_UPLOAD

USER = SimpleNamespace(user_id="USR1")


def _db(owns_project=True):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = object() if owns_project else None
    return db


def _file(name, data=b"hello", size=None):
    f = UploadFile(file=io.BytesIO(data), filename=name)
    if size is not None:
        f.size = size
    return f


def _reject(files, owns_project=True):
    with pytest.raises(HTTPException) as exc:
        services._validate_upload(_db(owns_project), USER, "PROJ1", files)
    return exc.value


def test_valid_files_pass():
    services._validate_upload(_db(), USER, "PROJ1", [_file("a.pdf"), _file("b.png"), _file("c.zip"), _file("d.tar.gz")])


def test_someone_elses_project_is_not_found():
    err = _reject([_file("a.pdf")], owns_project=False)
    assert err.status_code == 404 and err.detail == "Project not found."


def test_too_many_files():
    err = _reject([_file(f"{i}.txt") for i in range(MAX_FILES_PER_UPLOAD + 1)])
    assert err.status_code == 400 and f"at most {MAX_FILES_PER_UPLOAD}" in err.detail


@pytest.mark.parametrize("name,expected", [
    ("setup.exe", "not allowed"),
    ("photo.heic", "not a supported file type"),
    ("README", "not a supported file type (no extension)"),
])
def test_bad_file_types(name, expected):
    assert expected in _reject([_file(name)]).detail


def test_empty_file():
    assert "'empty.txt' is empty" in _reject([_file("empty.txt", b"")]).detail


def test_file_over_size_limit():
    err = _reject([_file("big.pdf", size=MAX_FILE_SIZE + 1)])
    assert "the limit is 500 MB" in err.detail


def test_all_problems_reported_together():
    detail = _reject([_file("a.exe"), _file("b.txt", b""), _file("ok.pdf")]).detail
    assert "a.exe" in detail and "b.txt" in detail and "ok.pdf" not in detail


def test_nothing_is_stored_when_validation_fails(monkeypatch):
    store = MagicMock()
    monkeypatch.setattr(services, "_create_upload_job", store)
    with pytest.raises(HTTPException):
        services.upload_documents(_db(), USER, SimpleNamespace(project_id="PROJ1"), [_file("a.exe")])
    store.assert_not_called()
