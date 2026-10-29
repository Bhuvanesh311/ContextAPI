from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db

from app.auth.dependencies import get_current_user
from app.auth.models import User

from app.core.schemas import MessageResponse
from app.target_application.schemas import (
    TargetApplicationCreate,
    TargetApplicationUpdate,
    TargetApplicationCreateResponse,
    TargetApplicationUpdateResponse,
    TargetApplicationDetailResponse,
    TargetApplicationListResponse,
)

from app.target_application.services import (
    create_target_application,
    get_target_application,
    get_target_applications,
    update_target_application,
    delete_target_application,
)

router = APIRouter(
    prefix="/projects/{project_id}/target-applications",
    tags=["Target Applications"],
)


@router.post(
    "/",
    response_model=TargetApplicationCreateResponse,
    status_code=201,
)
def create(project_id: str,request: TargetApplicationCreate,db: Session = Depends(get_db),current_user: User = Depends(get_current_user),):
    return create_target_application(
        db=db,
        current_user=current_user,
        project_id=project_id,
        request=request,
    )

"""@router.get(
    "/",
    response_model=TargetApplicationListResponse,
)
def list_all(project_id: str,db: Session = Depends(get_db),current_user: User = Depends(get_current_user),):
    return get_target_applications(
        db=db,
        current_user=current_user,
        project_id=project_id,
    )"""

@router.get(
    "/{target_application_id}",
    response_model=TargetApplicationDetailResponse,
)
def detail(project_id: str,target_application_id: str,db: Session = Depends(get_db),current_user: User = Depends(get_current_user),):
    return get_target_application(
        db=db,
        current_user=current_user,
        project_id=project_id,
        target_application_id=target_application_id,
    )


@router.put(
    "/{target_application_id}",
    response_model=TargetApplicationUpdateResponse,
)
def update(project_id: str,target_application_id: str,request: TargetApplicationUpdate,db: Session = Depends(get_db),current_user: User = Depends(get_current_user),):
    return update_target_application(
        db=db,
        current_user=current_user,
        project_id=project_id,
        target_application_id=target_application_id,
        request=request,
    )


@router.delete(
    "/{target_application_id}",
    response_model=MessageResponse,
)
def delete(project_id: str,target_application_id: str,db: Session = Depends(get_db),current_user: User = Depends(get_current_user),):
    return delete_target_application(
        db=db,
        current_user=current_user,
        project_id=project_id,
        target_application_id=target_application_id,
    )