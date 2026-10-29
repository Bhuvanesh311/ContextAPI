import logging
from io import BytesIO
from datetime import datetime, timezone

from app.core.config import settings
from app.core.enums import IngestionStage, DocumentVersionStatus
from app.infra.storage import storage_service

from app.knowledge.uploads.ingestion.context import IngestionContext
from app.knowledge.uploads.ingestion.result import IngestionStageResult

logger = logging.getLogger(__name__)

class PermanentStorageHandler:
    def execute(self, context: IngestionContext) -> IngestionStageResult:
        run = context.run
        document = context.document
        document_version = context.document_version

        parsed_bucket = document_version.parsed_bucket
        parsed_object_key = document_version.parsed_object_key

        if not parsed_bucket:
            return IngestionStageResult(success=False, error_message="INVALID_ARTIFACT: Parsed artifact bucket is missing.")
        if not parsed_object_key:
            return IngestionStageResult(success=False, error_message="INVALID_ARTIFACT: Parsed artifact object key is missing.")

        if not storage_service.exists(bucket=parsed_bucket, object_key=parsed_object_key):
            return IngestionStageResult(success=False, error_message="ARTIFACT_NOT_FOUND: Canonical parsed artifact does not exist.")

        permanent_bucket = document_version.permanent_bucket or settings.MINIO_DOCUMENT_BUCKET
        permanent_object_key = document_version.permanent_object_key
        if not permanent_object_key:
            permanent_object_key = (
                f"projects/{document.project_id}/"
                f"documents/{document.document_id}/"
                f"versions/{document_version.document_version_id}/"
                f"parsed.json"
            )

        checkpoint = dict(run.checkpoint_data or {})

        # IDEMPOTENT RETRY PATH
        if storage_service.exists(bucket=permanent_bucket, object_key=permanent_object_key):
            logger.info(
                "Permanent artifact already exists; using existing artifact",
                extra={
                    "ingestion_run_id": run.ingestion_run_id,
                    "document_id": document.document_id,
                    "permanent_bucket": permanent_bucket,
                    "permanent_object_key": permanent_object_key,
                }
            )
            document_version.permanent_bucket = permanent_bucket
            document_version.permanent_object_key = permanent_object_key
            context.db.commit()

            checkpoint.update({
                "stage": IngestionStage.PERMANENT_STORAGE.value,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })
            return IngestionStageResult(success=True, checkpoint_data=checkpoint)

        response = None
        try:
            response = storage_service.download(bucket=parsed_bucket, object_key=parsed_object_key)
            raw_bytes = response.read()
        except Exception as exc:
            return IngestionStageResult(success=False, error_message="INVALID_ARTIFACT: Unable to read canonical parsed artifact.")
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass
                try:
                    response.release_conn()
                except Exception:
                    pass

        if not raw_bytes:
            return IngestionStageResult(success=False, error_message="INVALID_ARTIFACT: Canonical parsed artifact is empty.")

        try:
            storage_service.upload(
                bucket=permanent_bucket,
                object_key=permanent_object_key,
                data=BytesIO(raw_bytes),
                size=len(raw_bytes),
                content_type="application/json",
            )
            document_version.permanent_bucket = permanent_bucket
            document_version.permanent_object_key = permanent_object_key
            document_version.status = DocumentVersionStatus.COMPLETED
            document_version.updated_at = datetime.now(timezone.utc)
            context.db.commit()
        except Exception as exc:
            return IngestionStageResult(success=False, error_message="PERMANENT_STORAGE_FAILED: Unable to store permanent artifact.")

        if not storage_service.exists(bucket=permanent_bucket, object_key=permanent_object_key):
            return IngestionStageResult(success=False, error_message="PERMANENT_STORAGE_FAILED: Permanent artifact verification failed.")

        checkpoint.update({
            "stage": IngestionStage.PERMANENT_STORAGE.value,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })

        return IngestionStageResult(
            success=True,
            checkpoint_data=checkpoint
        )
