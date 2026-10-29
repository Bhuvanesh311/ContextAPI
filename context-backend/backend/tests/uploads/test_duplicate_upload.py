from pathlib import Path

from app.knowledge.security.stage_1.context import ValidationContext
from app.knowledge.security.stage_1.phase_b.duplicate import check_duplicate_file


def _context() -> ValidationContext:
    return ValidationContext(
        upload_id="UPL1",
        project_id="P1",
        document_id="DOC2",
        file_path=Path("python.pdf"),
        original_filename="python.pdf",
        sha256="ab" * 32,
    )


def test_same_file_uploaded_again_is_accepted():
    context = _context()

    check_duplicate_file(context, lambda project, document, sha: "DOC1")

    assert context.duplicate is True
    assert context.duplicate_document_id == "DOC1"


def test_new_file_is_not_marked_duplicate():
    context = _context()

    check_duplicate_file(context, lambda project, document, sha: None)

    assert context.duplicate is False
    assert context.duplicate_document_id is None
