from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import or_
from app.project.models import Project
from app.project.schemas import (
    ProjectCreateRequest,
    ProjectCreateResponse,
    ProjectUpdateRequest,
    ProjectUpdateResponse,
    ProjectResponse,
    ProjectListResponse,

)
from app.core.schemas import MessageResponse
from app.project.utils import (
    get_next_project_sequence,
    generate_project_id,
)

from app.auth.models import User
from app.knowledge.uploads.models import Document, DocumentVersion, UploadJob
from app.knowledge.uploads.services import purge_stored_files, stored_objects
from app.retrieval.models import RetrievalRequest

from fastapi import HTTPException, status

# helper function for fetching project 
def _get_project_or_404(db: Session, project_id: str, current_user: User,)-> Project:
    project = (db.query(Project).filter(Project.project_id == project_id).first())

    if project is None: 
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    if project.user_id != current_user.user_id:
        raise HTTPException(status_code= status.HTTP_403_FORBIDDEN,
                            detail="You do not have perimission to access this project.",)

    return project


#services function 
def create_project(db:Session, current_user: User, request: ProjectCreateRequest)-> ProjectCreateResponse:
    existings_project = (db.query(Project).filter(
        Project.user_id == current_user.user_id,
        Project.name == request.name,
    ).first())

    if existings_project:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project with this name already exists.",
        )

    try: 
        sequence = get_next_project_sequence(db)
        project_id = generate_project_id(sequence)

        project = Project(
            project_id = project_id,
            user_id = current_user.user_id,
            tenant_id = current_user.tenant_id,
            name = request.name,
            description = request.description,
            status=request.status,
        )

        db.add(project)
        db.commit()
        db.refresh(project)

        return ProjectCreateResponse(message="Project created successfully.",
                                     project=ProjectResponse.model_validate(project),)

    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to create project.",)


def get_project_by_id(db:Session,project_id: str, current_user: User,)-> ProjectResponse:

    project = _get_project_or_404(db=db,
                                  project_id=project_id,
                                  current_user=current_user,)

    return ProjectResponse.model_validate(project)


def list_projects(db: Session, current_user: User,)->ProjectListResponse:
    projects= (db.query(Project)
               .filter(Project.user_id==current_user.user_id)
               .order_by(Project.created_at.desc())
               .all())

    return ProjectListResponse(
        total=len(projects),
        projects=[
            ProjectResponse.model_validate(project)
            for project in projects
        ]
    )


def update_project(db:Session,project_id:str,current_user:User,request: ProjectUpdateRequest)->ProjectUpdateResponse:
    project = _get_project_or_404(db=db,
                                  project_id=project_id,
                                  current_user=current_user,)

    # Partial update: only fields the client actually sent are changed.
    # name and status are NOT NULL, so an explicit null leaves them as they are.
    update_data = {
        field: value
        for field, value in request.model_dump(exclude_unset=True).items()
        if value is not None or field == "description"
    }

    if "name" in update_data and update_data["name"] != project.name:
        existing_project=( db.query(Project)
            .filter(
                Project.user_id == current_user.user_id,
                Project.name == request.name,
            )
            .first()
        )

        if existing_project: 
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Project with this name already exists",
            )

    try: 
        for field in ("name", "description", "status"):
            if field in update_data:
                setattr(project, field, update_data[field])

        db.commit()
        db.refresh(project)

        return ProjectUpdateResponse(
            message="Project is updated.",
            project=ProjectResponse.model_validate(project),
        )

    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail= "Failed to update project.",
        )


def delete_project(db:Session,project_id:str,current_user:User)->MessageResponse:
    _get_project_or_404(db=db,
                        project_id=project_id,
                        current_user=current_user,)

    versions = (db.query(DocumentVersion)
                .join(Document, Document.document_id == DocumentVersion.document_id)
                .filter(Document.project_id == project_id)
                .all())
    objects = stored_objects(versions)
    version_ids = [v.document_version_id for v in versions]

    try:
        # Bulk deletes, children first: the project's foreign keys from
        # documents, upload jobs and retrieval requests have no ON DELETE
        # CASCADE. The database cascades the rest (document versions, chunks,
        # embeddings, ingestion runs, target applications).
        db.query(RetrievalRequest).filter(
            RetrievalRequest.project_id == project_id
        ).delete(synchronize_session=False)
        db.query(Document).filter(
            Document.project_id == project_id
        ).delete(synchronize_session=False)
        db.query(UploadJob).filter(
            UploadJob.project_id == project_id
        ).delete(synchronize_session=False)
        db.query(Project).filter(
            Project.project_id == project_id
        ).delete(synchronize_session=False)
        db.commit()

    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to delete project.",)

    # Files and vectors go only once the rows are gone.
    purge_stored_files(objects, version_ids)
    return MessageResponse(message="Project deleted successfully.")
