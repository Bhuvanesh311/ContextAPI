from typing import Any

from sqlalchemy.orm import Session

from app.core.enums import (
    KnowledgeProcessingRunStatus,
    KnowledgeProcessingStage,
)
from app.knowledge.cancellation import raise_if_cancelled
from app.knowledge.processing.context import KnowledgeProcessingContext
from app.knowledge.processing.exceptions import KnowledgeProcessingStateError
from app.knowledge.processing.services.lifecycle import (
    KnowledgeProcessingLifecycleService,
)
from app.knowledge.processing.stages.base import (
    BaseKnowledgeProcessingStage,
)
from app.knowledge.processing.stages.registry import (
    KnowledgeProcessingStageRegistry,
)
from app.knowledge.uploads.models import DocumentVersion


class KnowledgeProcessingOrchestrator:
    def __init__(
        self,
        *,
        db: Session,
        lifecycle: KnowledgeProcessingLifecycleService,
        stage_registry: KnowledgeProcessingStageRegistry,
    ) -> None:
        self.db = db
        self.lifecycle = lifecycle
        self.stage_registry = stage_registry

    def run(
        self,
        *,
        knowledge_processing_run_id: str,
    ) -> KnowledgeProcessingRunStatus:
        run = self.lifecycle.get_run(knowledge_processing_run_id)

        if run.status == KnowledgeProcessingRunStatus.COMPLETED:
            return run.status

        if run.status == KnowledgeProcessingRunStatus.CANCELLED:
            return run.status

        raise_if_cancelled(run.document_version_id)

        document_version = self._get_document_version(
            run.document_version_id
        )

        self._validate_permanent_artifact(document_version)

        self.lifecycle.start_run(run)

        checkpoint_data: dict[str, Any] = dict(
            run.checkpoint_data or {}
        )

        chunks_object_key = self._get_chunks_object_key(
            document_version=document_version,
        )

        embeddings_object_key = self._get_embeddings_object_key(
            document_version=document_version,
        )

        while True:
            current_stage = run.current_stage

            # Stopped by the user (the task records the run as CANCELLED).
            raise_if_cancelled(document_version.document_version_id)

            if current_stage == KnowledgeProcessingStage.COMPLETED:
                self.lifecycle.complete_run(run)
                break

            stage: BaseKnowledgeProcessingStage = (
                self.stage_registry.get(current_stage)
            )

            context = KnowledgeProcessingContext(
                knowledge_processing_run_id=run.knowledge_processing_run_id,
                document_id=document_version.document_id,
                document_version_id=document_version.document_version_id,
                permanent_bucket=document_version.permanent_bucket,
                permanent_object_key=document_version.permanent_object_key,
                chunks_object_key=chunks_object_key,
                embeddings_object_key=embeddings_object_key,
                current_stage=current_stage,
                checkpoint_data=checkpoint_data,
            )

            updated_context = stage.execute(context)

            checkpoint_data = dict(
                updated_context.checkpoint_data
            )

            self.lifecycle.update_checkpoint(
                run=run,
                checkpoint_data=checkpoint_data,
            )

            self.lifecycle.advance_stage(run)
            self.db.commit()

        return run.status

    def _get_document_version(
        self,
        document_version_id: str,
    ) -> DocumentVersion:
        document_version = (
            self.db.query(DocumentVersion)
            .filter(
                DocumentVersion.document_version_id
                == document_version_id
            )
            .first()
        )

        if document_version is None:
            raise KnowledgeProcessingStateError(
                "Document version not found: "
                f"{document_version_id}"
            )

        return document_version

    @staticmethod
    def _validate_permanent_artifact(
        document_version: DocumentVersion,
    ) -> None:
        if not document_version.permanent_bucket:
            raise KnowledgeProcessingStateError(
                "Document version has no permanent storage bucket"
            )

        if not document_version.permanent_object_key:
            raise KnowledgeProcessingStateError(
                "Document version has no permanent storage object key"
            )

    @staticmethod
    def _get_chunks_object_key(
        *,
        document_version: DocumentVersion,
    ) -> str:
        return (
            f"projects/{document_version.document.project_id}"
            f"/documents/{document_version.document_id}"
            f"/versions/{document_version.document_version_id}"
            "/chunks.ndjson"
        )

    @staticmethod
    def _get_embeddings_object_key(
        *,
        document_version: DocumentVersion,
    ) -> str:
        return (
            f"projects/{document_version.document.project_id}"
            f"/documents/{document_version.document_id}"
            f"/versions/{document_version.document_version_id}"
            "/embeddings.ndjson"
        )