"""Document upload and management API endpoints."""
import uuid
from pathlib import Path
from typing import List, Optional
from fastapi import (
    APIRouter, Depends, HTTPException, UploadFile, File,
    Form, status, Query
)
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.config import settings
from app.api.deps import get_current_user
from app.models.user import User
from app.models.document import Document, DocumentStatus, DocumentRole
from app.models.document_group import DocumentGroup
from app.schemas.document import DocumentResponse, DocumentUploadResponse
from app.tasks.processing_tasks import process_document_task

router = APIRouter(prefix="/documents", tags=["Documents"])

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
EXTENSION_TO_TYPE = {
    ".pdf": "pdf",
    ".jpg": "jpg",
    ".jpeg": "jpg",
    ".png": "png",
}


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a PDF or image document for processing",
)
async def upload_document(
    file: UploadFile = File(..., description="PDF, JPG, or PNG file"),
    group_id: Optional[str] = Form(None, description="Optional document group ID"),
    document_role: Optional[str] = Form(
        None,
        description="Role hint: question_paper | answer_key | mixed",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upload a document for asynchronous processing.

    Returns immediately with a `document_id`. Poll `GET /documents/{id}` to
    track processing status. When `status == completed`, use
    `GET /documents/{id}/questions` to retrieve extracted questions.

    **Supported formats:** PDF, JPG/JPEG, PNG

    **Max file size:** configurable via `MAX_FILE_SIZE_MB` env variable (default 50 MB)
    """
    # Validate file extension
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported file type '{suffix}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            ),
        )

    # Read content
    content = await file.read()

    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )

    if len(content) > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum allowed size: {settings.MAX_FILE_SIZE_MB} MB",
        )

    # Resolve document role
    doc_role = DocumentRole.UNKNOWN
    if document_role:
        try:
            doc_role = DocumentRole(document_role)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid document_role '{document_role}'. "
                       f"Use: question_paper, answer_key, mixed",
            )

    # Validate group_id if provided
    group = None
    if group_id:
        group = db.query(DocumentGroup).filter(
            DocumentGroup.id == group_id,
            DocumentGroup.owner_id == current_user.id,
        ).first()
        if not group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document group not found or not owned by you",
            )

    # Save file to disk
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4()}{suffix}"
    file_path = upload_dir / stored_name
    file_path.write_bytes(content)

    file_type = EXTENSION_TO_TYPE.get(suffix, suffix.lstrip("."))

    # Create DB record
    document = Document(
        filename=stored_name,
        original_filename=file.filename or stored_name,
        file_path=str(file_path.resolve()),
        file_type=file_type,
        file_size=len(content),
        status=DocumentStatus.PENDING,
        document_role=doc_role,
        owner_id=current_user.id,
        group_id=group.id if group else None,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    # Dispatch async Celery task
    task = process_document_task.delay(str(document.id))
    document.celery_task_id = task.id
    db.commit()

    return DocumentUploadResponse(
        document_id=document.id,
        message="Document uploaded successfully. Processing started asynchronously.",
        status=document.status,
        celery_task_id=task.id,
    )


@router.get(
    "/",
    response_model=List[DocumentResponse],
    summary="List all documents for the current user",
)
def list_documents(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=100, description="Max records to return"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all documents owned by the current user, newest first."""
    query = db.query(Document).filter(Document.owner_id == current_user.id)
    if status_filter:
        try:
            query = query.filter(Document.status == DocumentStatus(status_filter))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status '{status_filter}'. "
                       f"Use: pending, processing, completed, failed",
            )
    return query.order_by(Document.created_at.desc()).offset(skip).limit(limit).all()


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get document details and processing status",
)
def get_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve a specific document's metadata and current processing status.

    Poll this endpoint until `status == completed` before fetching questions.
    """
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.owner_id == current_user.id,
    ).first()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return document


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document and all its extracted data",
)
def delete_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a document, its questions, warnings, and the stored file."""
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.owner_id == current_user.id,
    ).first()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    # Remove stored file
    try:
        Path(document.file_path).unlink(missing_ok=True)
    except Exception:
        pass
    db.delete(document)
    db.commit()
