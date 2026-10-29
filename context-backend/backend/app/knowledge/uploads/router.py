from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    UploadFile,
    Query,
    status,
    Response,
)

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.schemas import SuccessResponse,MessageResponse

from app.knowledge.uploads.schemas import (
    UploadRequest,
    UploadResponse,
    DocumentListResponse,
    PaginationMeta,
    DocumentDetailResponse,
    UploadDetailResponse,
    UpdateDocumentRequest,
    PaginatedUploadResponse,
)

from app.knowledge.uploads.mapper import (
    map_upload_response,
    map_document_response,
    map_document_detail_response,
    map_upload_history_response,
    map_upload_detail_response,
)

from app.knowledge.uploads.services import (
    upload_documents,
    list_documents,
    get_document,
    rename_document,
    delete_document,
    cancel_document,
    list_uploads,
    get_upload_details,
)

from app.core.enums import DocumentStatus
from app.auth.dependencies import get_current_user

from  app.auth.models import User

router = APIRouter(
    prefix="/upload",
    tags=["Knowledge Upload"],
)


@router.post(
    "/",
    response_model=SuccessResponse[UploadResponse],
    status_code=201,
)
def upload_files(
    project_id: str = Form(...),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    request = UploadRequest(
        project_id=project_id,
    )

    upload_job = upload_documents(
        db=db,
        current_user=current_user,
        request=request,
        files=files,
    )

    return SuccessResponse(
        message="Documents uploaded successfully.",
        data=map_upload_response(upload_job),
    )


@router.get(
    "/uploads",
    response_model=SuccessResponse[PaginatedUploadResponse],
    summary="List Uploads",
)
def get_uploads(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    uploads, pagination = list_uploads(
        db=db,
        current_user=current_user,
        page=page,
        page_size=page_size,
    )

    return SuccessResponse(
        message="Uploads retrieved successfully.",
        data=PaginatedUploadResponse(
            uploads=[
                map_upload_history_response(upload)
                for upload in uploads
            ],
            pagination=pagination,
        ),
    )


@router.get(
    "/uploads/{upload_id}",
    response_model=SuccessResponse[UploadDetailResponse],
    summary="Get Upload Details",
)
def get_upload_by_id(
    upload_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    upload, documents = get_upload_details(
        db=db,
        current_user=current_user,
        upload_id=upload_id,
    )

    return SuccessResponse(
        message="Upload details retrieved successfully.",
        data=map_upload_detail_response(
            upload,
            documents,
        ),
    )


@router.get(
    "/documents",
    response_model=SuccessResponse[DocumentListResponse],
    status_code=status.HTTP_200_OK,
    summary="List Documents",
    description="Retrieve all documents belonging to the authenticated user.",
)
def get_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    project_id: str | None = Query(None),
    status_filter: DocumentStatus | None = Query(None),
    sort_by: str = Query("created_at"),
    order: str = Query("desc"),

    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    documents, pagination = list_documents(
        db=db,
        current_user=current_user,
        page=page,
        page_size=page_size,
        search=search,
        project_id=project_id,
        status_filter=status_filter,
        sort_by=sort_by,
        order=order,
    )

    return SuccessResponse(
        message="Documents retrieved successfully.",
        data=DocumentListResponse(
            documents=[
                map_document_response(document)
                for document in documents
            ],
            pagination=pagination,
        ),
    )


@router.get(
    "/documents/{document_id}",
    response_model=SuccessResponse[DocumentDetailResponse],
    status_code=status.HTTP_200_OK,
    summary="Get Document",
    description="Retrieve details of a specific document belonging to the authenticated user.",
)
def get_document_by_id(
    document_id: str,

    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    document = get_document(
        db=db,
        current_user=current_user,
        document_id=document_id,
    )

    return SuccessResponse(
        message="Document retrieved successfully.",
        data=map_document_detail_response(document),
    )


@router.patch(
    "/documents/{document_id}",
    response_model=SuccessResponse[DocumentDetailResponse],
    status_code=status.HTTP_200_OK,
    summary="Rename Document",
)
def rename_document_by_id(
    document_id: str,
    request: UpdateDocumentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    document = rename_document(
        db=db,
        current_user=current_user,
        document_id=document_id,
        request=request,
    )

    return SuccessResponse(
        message="Document renamed successfully.",
        data=map_document_detail_response(document),
    )


@router.post(
    "/documents/{document_id}/cancel",
    response_model=SuccessResponse[DocumentDetailResponse],
    status_code=status.HTTP_200_OK,
    summary="Stop Processing a Document",
    description=(
        "Stops the document's ingestion and indexing immediately (for an "
        "archive, every member still in progress). Its status becomes "
        "CANCELLED; delete it or upload it again. 409 when nothing is running."
    ),
)
def cancel_document_by_id(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    document = cancel_document(
        db=db,
        current_user=current_user,
        document_id=document_id,
    )

    return SuccessResponse(
        message="Document processing stopped.",
        data=map_document_detail_response(document),
    )


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Document",
)
def delete_document_by_id(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    delete_document(
        db=db,
        current_user=current_user,
        document_id=document_id,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)

