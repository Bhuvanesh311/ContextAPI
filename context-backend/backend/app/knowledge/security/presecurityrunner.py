from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from sqlalchemy.orm import Session

from app.infra.storage import storage_service

from app.knowledge.uploads.models import (
    Document,
    DocumentVersion,
)

from app.knowledge.security.stage_1.runner import (
    run_stage_one_for_document,
)

from app.knowledge.security.stage_2.runner import (
    run_stage_two_for_document,
)

from app.knowledge.security.stage_2.adapters import (
    persist_child,
)

from app.knowledge.security.stage_2.phase_d.context import (
    ChildFileContext,
)

from app.knowledge.security.stage_3.runner import (
    run_stage_three_for_document,
)


ARCHIVE_EXTENSIONS = {
    ".zip",
    ".tar",
}


class PreSecurityResult:

    def __init__(
        self,
        *,
        document_id: str,
        success: bool,
        is_archive: bool,
        stage_one_result: Any = None,
        stage_two_result: Any = None,
        stage_three_result: Any = None,
        child_document_ids: list[str] | None = None,
        detected_format: str | None = None,
    ) -> None:

        self.document_id = document_id
        self.success = success
        self.is_archive = is_archive

        self.stage_one_result = stage_one_result
        self.stage_two_result = stage_two_result
        self.stage_three_result = stage_three_result

        self.child_document_ids = (
            child_document_ids or []
        )

        self.detected_format = detected_format

    def to_dict(self) -> dict[str, Any]:

        return {
            "document_id": self.document_id,
            "success": self.success,
            "is_archive": self.is_archive,
            "child_document_ids": self.child_document_ids,
            "detected_format": self.detected_format,
        }


class PreSecurityRunner:

    def __init__(
        self,
        db: Session,
    ) -> None:

        self.db = db

    def run(
        self,
        *,
        document: Document,
        document_version: DocumentVersion,
    ) -> PreSecurityResult:

        stage_one_result = (
            self._run_stage_one(
                document=document,
                document_version=document_version,
            )
        )

        if self._is_archive_document(
            document_version
        ):

            return self._run_archive_pipeline(
                document=document,
                document_version=document_version,
                stage_one_result=stage_one_result,
            )

        stage_three_result = (
            self._run_stage_three(
                document=document,
                document_version=document_version,
            )
        )

        detected_format = getattr(
            stage_three_result,
            "detected_format",
            None,
        )

        return PreSecurityResult(
            document_id=document.document_id,
            success=True,
            is_archive=False,
            stage_one_result=stage_one_result,
            stage_three_result=stage_three_result,
            detected_format=detected_format,
        )

    def _run_stage_one(
        self,
        *,
        document: Document,
        document_version: DocumentVersion,
    ) -> Any:

        return run_stage_one_for_document(
            db=self.db,
            document=document,
            document_version=document_version,
        )

    def _run_archive_pipeline(
        self,
        *,
        document: Document,
        document_version: DocumentVersion,
        stage_one_result: Any,
    ) -> PreSecurityResult:

        child_document_ids: list[str] = []

        suffix = (
            Path(
                document_version.file_name
            ).suffix
            or document_version.file_extension
            or ".archive"
        )

        with TemporaryDirectory(
            prefix=(
                f"presecurity_stage2_"
                f"{document.document_id}_"
            )
        ) as temp_directory:

            local_archive = (
                Path(temp_directory)
                / f"source{suffix}"
            )

            self._download_document_to_temp(
                document_version=document_version,
                destination=local_archive,
            )

            def persist_callback(
                child: ChildFileContext,
            ) -> str:

                child_document_id = persist_child(
                    self.db,
                    parent_document=document,
                    child=child,
                )

                return child_document_id

            def queue_callback(
                child: ChildFileContext,
            ) -> None:

                if not child.document_id:
                    raise ValueError(
                        "Cannot queue child "
                        "without document_id."
                    )

                child_document_ids.append(
                    child.document_id
                )

            stage_two_result = (
                run_stage_two_for_document(
                    document_id=document.document_id,
                    upload_id=document.upload_id,
                    project_id=document.project_id,
                    original_filename=(
                        document_version.file_name
                    ),
                    file_path=local_archive,
                    archive_depth=0,
                    persist_callback=(
                        persist_callback
                    ),
                    queue_callback=(
                        queue_callback
                    ),
                )
            )

        self.db.flush()

        return PreSecurityResult(
            document_id=document.document_id,
            success=True,
            is_archive=True,
            stage_one_result=stage_one_result,
            stage_two_result=stage_two_result,
            child_document_ids=child_document_ids,
        )

    def _run_stage_three(
        self,
        *,
        document: Document,
        document_version: DocumentVersion,
    ) -> Any:

        suffix = (
            Path(
                document_version.file_name
            ).suffix
            or document_version.file_extension
            or ""
        )

        with TemporaryDirectory(
            prefix=(
                f"presecurity_stage3_"
                f"{document.document_id}_"
            )
        ) as temp_directory:

            local_file = (
                Path(temp_directory)
                / f"source{suffix}"
            )

            self._download_document_to_temp(
                document_version=document_version,
                destination=local_file,
            )

            return run_stage_three_for_document(
                upload_id=document.upload_id,
                project_id=document.project_id,
                document_id=document.document_id,
                parent_document_id=(
                    document.parent_document_id
                ),
                file_path=local_file,
                original_filename=(
                    document_version.file_name
                ),
                extension=(
                    document_version.file_extension
                ),
                mime_type=(
                    document_version.mime_type
                ),
                file_size=(
                    document_version.file_size
                ),
                sha256=(
                    document_version.sha256_hash
                ),
            )

    @staticmethod
    def _is_archive_document(
        document_version: DocumentVersion,
    ) -> bool:

        extension = (
            document_version.file_extension
            or Path(
                document_version.file_name
            ).suffix
            or ""
        ).lower()

        return extension in ARCHIVE_EXTENSIONS

    @staticmethod
    def _download_document_to_temp(
        *,
        document_version: DocumentVersion,
        destination: Path,
    ) -> None:

        response = None

        bucket = (
            document_version.quarantine_bucket
        )

        object_key = (
            document_version.quarantine_object_key
        )

        if not bucket or not object_key:

            raise ValueError(
                "Document version does not have "
                "a quarantine storage location."
            )

        try:

            response = storage_service.download(
                bucket=bucket,
                object_key=object_key,
            )

            destination.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with destination.open(
                "wb"
            ) as file:

                while True:

                    chunk = response.read(
                        1024 * 1024
                    )

                    if not chunk:
                        break

                    file.write(chunk)

        finally:

            if response is not None:

                response.close()

                response.release_conn()