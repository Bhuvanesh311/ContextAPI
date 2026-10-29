from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from fastapi import HTTPException, status

from app.project.models import Project
from app.target_application.models import TargetApplication

from app.core.schemas import MessageResponse
from app.target_application.schemas import (
    TargetApplicationCreate,
    TargetApplicationUpdate,
    TargetApplicationResponse,
    TargetApplicationCreateResponse,
    TargetApplicationUpdateResponse,
    TargetApplicationDetailResponse,
    TargetApplicationListResponse,
)

from app.target_application.utils import (
    get_next_target_sequence,
    generate_target_application_id,
)
from app.auth.models import User
from app.project.services import _get_project_or_404


def _get_target_application_or_404(db: Session,project_id: str,target_application_id: str,) -> TargetApplication:

    target_application = (db.query(TargetApplication)
        .filter(
            TargetApplication.target_application_id == target_application_id,
            TargetApplication.project_id == project_id,
        )
        .first())

    if not target_application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target application not found.",
        )

    return target_application


def create_target_application(db: Session,current_user: User,project_id: str,request: TargetApplicationCreate,) -> TargetApplicationCreateResponse:
    project = _get_project_or_404(db=db,project_id=project_id,current_user=current_user,)

    existing_target = (
    db.query(TargetApplication)
    .filter(
        TargetApplication.project_id == project.project_id,
        TargetApplication.base_url == str(request.base_url),
    )
    .first()
    )

    if existing_target:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Target application with this Base URL already exists.",
        )
    
    try:
        sequence = get_next_target_sequence(db)
        target_application_id = generate_target_application_id(sequence)

        target_application = TargetApplication(
            target_application_id=target_application_id,
            project_id=project.project_id,
            base_url=str(request.base_url),
            environment=request.environment,
            api_version=request.api_version,
        )

        db.add(target_application)
        db.commit()
        db.refresh(target_application)

        return TargetApplicationCreateResponse(
            message="Target application created successfully.",
            target_application=TargetApplicationResponse.model_validate(
                target_application
            ),
        )

    except SQLAlchemyError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create target application.",
        )


def get_target_application(db: Session,current_user: User,project_id: str,target_application_id: str,) -> TargetApplicationDetailResponse:
    project = _get_project_or_404(db=db,project_id=project_id,current_user=current_user,)
    target_application = _get_target_application_or_404(db=db,project_id=project.project_id,target_application_id=target_application_id,)

    return TargetApplicationDetailResponse(
    target_application=TargetApplicationResponse.model_validate(target_application)
    )

def get_target_applications(db: Session,current_user: User,project_id: str,) -> TargetApplicationListResponse:
    project = _get_project_or_404(db=db,project_id=project_id,current_user=current_user,)
    target_applications = (db.query(TargetApplication)
    .filter(
        TargetApplication.project_id == project.project_id
    )
    .order_by(TargetApplication.created_at.desc()).all()
    )
    return TargetApplicationListResponse(
        target_applications=[
            TargetApplicationResponse.model_validate(target_application)
            for target_application in target_applications
        ] )


def update_target_application(db: Session,current_user: User,project_id: str,target_application_id: str,request: TargetApplicationUpdate,) -> TargetApplicationUpdateResponse:
    project = _get_project_or_404(db=db,project_id=project_id,current_user=current_user,)
    target_application = _get_target_application_or_404(db=db,project_id=project.project_id,target_application_id=target_application_id,)

    
    if (
    request.base_url
    and str(request.base_url) != target_application.base_url):
        existing_target = (
            db.query(TargetApplication)
            .filter(
                TargetApplication.project_id == project.project_id,
                TargetApplication.base_url == str(request.base_url),
                TargetApplication.target_application_id != target_application_id,
            )
            .first()
        )

        if existing_target:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Target application with this Base URL already exists.",
            )
    update_data = request.model_dump(
    exclude_unset=True,)

    editable_fields = {
    "base_url",
    "environment",
    "api_version",}

    for field, value in update_data.items():
        if field not in editable_fields:
            continue

        if field == "base_url":
            value = str(value)

        setattr(target_application, field, value)

    try:
        db.commit()
        db.refresh(target_application)

    except SQLAlchemyError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update target application.",
        )
    return TargetApplicationUpdateResponse(
    message="Target application updated successfully.",
    target_application=TargetApplicationResponse.model_validate(
        target_application
    ),)

def delete_target_application(db: Session,current_user: User,project_id: str,target_application_id: str,) -> MessageResponse:
    project = _get_project_or_404(db=db,project_id=project_id,current_user=current_user,)

    target_application = _get_target_application_or_404(db=db,project_id=project.project_id,target_application_id=target_application_id,)

    try:
        db.delete(target_application)
        db.commit()

    except SQLAlchemyError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete target application.",
        )

    return MessageResponse(    message="Target application deleted successfully.",)