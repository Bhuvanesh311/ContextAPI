from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.knowledge.uploads.models import (
    IngestionRun,
    Document,
    DocumentVersion,
)

from app.core.enums import (
    IngestionRunStatus,
    IngestionStage,
)

from app.knowledge.uploads.utils import (
    get_next_ingestion_run_sequence,
    generate_ingestion_run_id,
)


def _get_ingestion_run(
    db: Session,
    ingestion_run_id: str,
) -> IngestionRun:

    run = (
        db.query(IngestionRun)
        .filter(
            IngestionRun.ingestion_run_id == ingestion_run_id
        )
        .first()
    )

    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingestion run not found.",
        )

    return run


def get_ingestion_run(
    db: Session,
    ingestion_run_id: str,
) -> IngestionRun:

    return _get_ingestion_run(
        db=db,
        ingestion_run_id=ingestion_run_id,
    )


def get_active_ingestion_run(
    db: Session,
    document_version_id: str,
) -> IngestionRun | None:

    return (
        db.query(IngestionRun)
        .filter(
            IngestionRun.document_version_id == document_version_id,
            IngestionRun.status.in_(
                [
                    IngestionRunStatus.PENDING,
                    IngestionRunStatus.RUNNING,
                    IngestionRunStatus.RETRYING,
                ]
            ),
        )
        .order_by(
            IngestionRun.created_at.desc()
        )
        .first()
    )


def create_ingestion_run(
    db: Session,
    document: Document,
    document_version: DocumentVersion,
) -> IngestionRun:

    existing_run = get_active_ingestion_run(
        db=db,
        document_version_id=document_version.document_version_id,
    )

    if existing_run is not None:
        return existing_run

    sequence = get_next_ingestion_run_sequence(db)

    ingestion_run_id = generate_ingestion_run_id(sequence)

    now = datetime.now(timezone.utc)

    run = IngestionRun(
        ingestion_run_id=ingestion_run_id,
        document_id=document.document_id,
        document_version_id=document_version.document_version_id,
        status=IngestionRunStatus.PENDING,
        current_stage=IngestionStage.UPLOAD_RECEIVED,
        attempt_number=1,
        retry_count=0,
        max_retries=3,
        next_retry_at=None,
        checkpoint_data=None,
        failed_stage=None,
        error_code=None,
        error_message=None,
        error_details=None,
        started_at=None,
        completed_at=None,
        created_at=now,
        updated_at=now,
    )

    db.add(run)
    db.flush()

    return run


def update_ingestion_stage(
    db: Session,
    ingestion_run_id: str,
    stage: IngestionStage,
) -> IngestionRun:

    run = _get_ingestion_run(
        db=db,
        ingestion_run_id=ingestion_run_id,
    )

    run.current_stage = stage
    run.updated_at = datetime.now(timezone.utc)

    db.flush()

    return run


def update_ingestion_status(
    db: Session,
    ingestion_run_id: str,
    run_status: IngestionRunStatus,
) -> IngestionRun:

    run = _get_ingestion_run(
        db=db,
        ingestion_run_id=ingestion_run_id,
    )

    now = datetime.now(timezone.utc)

    run.status = run_status
    run.updated_at = now

    if run_status == IngestionRunStatus.RUNNING:
        if run.started_at is None:
            run.started_at = now

    elif run_status == IngestionRunStatus.COMPLETED:
        run.completed_at = now
        run.next_retry_at = None

    db.flush()

    return run


def save_ingestion_checkpoint(
    db: Session,
    ingestion_run_id: str,
    checkpoint_data: dict,
) -> IngestionRun:

    run = _get_ingestion_run(
        db=db,
        ingestion_run_id=ingestion_run_id,
    )

    run.checkpoint_data = checkpoint_data
    run.updated_at = datetime.now(timezone.utc)

    db.flush()

    return run


def record_ingestion_failure(
    db: Session,
    ingestion_run_id: str,
    failed_stage: IngestionStage,
    error_code: str,
    error_message: str,
    error_details: dict | None = None,
) -> IngestionRun:

    run = _get_ingestion_run(
        db=db,
        ingestion_run_id=ingestion_run_id,
    )

    now = datetime.now(timezone.utc)

    run.status = IngestionRunStatus.FAILED
    run.failed_stage = failed_stage
    run.error_code = error_code
    run.error_message = error_message
    run.error_details = error_details
    run.updated_at = now

    db.flush()

    return run


def commit_ingestion_run(
    db: Session,
    run: IngestionRun,
) -> IngestionRun:

    try:
        db.commit()
        db.refresh(run)

        return run

    except SQLAlchemyError:
        db.rollback()
        raise