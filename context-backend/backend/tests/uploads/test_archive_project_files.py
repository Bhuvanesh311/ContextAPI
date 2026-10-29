import zipfile
from pathlib import Path

import pytest

from app.knowledge.security.stage_1.context import ValidationContext
from app.knowledge.security.stage_1.phase_b.Compatibility import validate_file_compatibility
from app.knowledge.security.stage_2.constants import ArchiveType
from app.knowledge.security.stage_2.context import ArchiveValidationContext
from app.knowledge.security.stage_2.phase_c.extraction import extract_archive_securely
from app.knowledge.security.stage_2.phase_c.ignore import is_ignored_member


@pytest.mark.parametrize("name", [
    ".git/HEAD",
    "repo/.git/hooks/commit-msg.sample",
    "crm/target/classes/App.class",
    "crm/target/maven-status/maven-compiler-plugin/compile/default-compile/createdFiles.lst",
    "web/node_modules/react/index.js",
    "app/__pycache__/main.cpython-313.pyc",
    "crm/.gitignore",
    "crm/mvnw",
    "crm/mvnw.cmd",
    "__MACOSX/._report.pdf",
    "lib/helper.jar",
])
def test_project_noise_is_ignored(name):
    assert is_ignored_member(name)


@pytest.mark.parametrize("name", [
    "crm/src/main/java/com/crm/NotificationClient.java",
    "crm/pom.xml",
    "crm/src/main/resources/application.properties",
    "docs/Build guide.pdf",
    "README.md",
])
def test_project_content_is_kept(name):
    assert not is_ignored_member(name)


def test_zip_extraction_skips_noise_and_keeps_sources(tmp_path: Path):
    archive = tmp_path / "Incubation_crm.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("crm/src/App.java", "class App {}")
        zf.writestr("crm/pom.xml", "<project/>")
        zf.writestr("crm/.git/HEAD", "ref: refs/heads/main")
        zf.writestr("crm/target/classes/App.class", b"\xca\xfe\xba\xbe")
        zf.writestr("crm/mvnw", "#!/bin/sh")
    workspace = tmp_path / "ws"
    workspace.mkdir()
    context = ArchiveValidationContext(
        document_id="DOC1", upload_id="UP1", project_id="P1",
        original_filename=archive.name, file_path=archive,
        archive_type=ArchiveType.ZIP, extraction_workspace=workspace,
    )

    paths = extract_archive_securely(context)

    assert sorted(p.relative_to(workspace.resolve()).as_posix() for p in paths) == [
        "crm/pom.xml", "crm/src/App.java",
    ]
    assert sorted(context.skipped_entries) == [
        "crm/.git/HEAD", "crm/mvnw", "crm/target/classes/App.class",
    ]


def _compat(filename, extension, mime):
    context = ValidationContext(
        upload_id="UP1", project_id="P1", document_id="DOC1",
        file_path=Path(filename), original_filename=filename,
        extension=extension, detected_mime=mime,
    )
    validate_file_compatibility(context)
    return context.mime_signature_match


def test_java_misdetected_as_cpp_is_accepted():
    # libmagic reads Java with generics as C++.
    assert _compat("NotificationClient.java", ".java", "text/x-c++") is True


def test_source_extension_still_rejects_binary_content():
    from app.knowledge.security.stage_1.exceptions import MimeSignatureMismatchError

    with pytest.raises(MimeSignatureMismatchError):
        _compat("App.java", ".java", "application/x-executable")
