from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.dependencies import get_current_user
from app.auth.models import User

from app.project.schemas import (
    ProjectCreateRequest,
    ProjectUpdateRequest,
    ProjectResponse,
    ProjectListResponse,
    ProjectCreateResponse,
    ProjectUpdateResponse
    
)
from app.core.schemas import MessageResponse
from app.project.services import (
    create_project,
    get_project_by_id,
    list_projects,
    update_project,
    delete_project,
)

router = APIRouter(
    prefix="/projects",
    tags=["Projects"],
)

@router.post(
    "/",
    response_model=ProjectCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_new_project(
    request: ProjectCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return create_project(
        db=db,
        current_user=current_user,
        request=request,
    )

@router.get(
    "/",
    response_model=ProjectListResponse,
)
def get_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return list_projects(
        db=db,
        current_user=current_user,
    )

@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_project_by_id(
        db=db,
        project_id=project_id,
        current_user=current_user,
    )

@router.put(
    "/{project_id}",
    response_model=ProjectUpdateResponse,
)
def edit_project(
    project_id: str,
    request: ProjectUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return update_project(
        db=db,
        project_id=project_id,
        current_user=current_user,
        request=request,
    )

@router.delete(
    "/{project_id}",
    response_model=MessageResponse,
)
def remove_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return delete_project(
        db=db,
        project_id=project_id,
        current_user=current_user,
    )