"""Document group management endpoints."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.document_group import DocumentGroup
from app.models.document import Document
from app.schemas.document import DocumentGroupCreate, DocumentGroupResponse, DocumentResponse
from app.tasks.processing_tasks import link_answers_task

router = APIRouter(prefix="/groups", tags=["Document Groups"])


@router.post(
    "/",
    response_model=DocumentGroupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a document group",
)
def create_group(
    group_data: DocumentGroupCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a document group to associate related documents.

    Example use case: link a **Question Paper** PDF with a separate **Answer Key** PDF.
    After both are uploaded with the group_id, call `POST /groups/{id}/link-answers`
    to automatically associate answers with questions.
    """
    group = DocumentGroup(
        name=group_data.name,
        description=group_data.description,
        owner_id=current_user.id,
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


@router.get(
    "/",
    response_model=List[DocumentGroupResponse],
    summary="List all document groups",
)
def list_groups(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all document groups owned by the current user."""
    return (
        db.query(DocumentGroup)
        .filter(DocumentGroup.owner_id == current_user.id)
        .order_by(DocumentGroup.created_at.desc())
        .all()
    )


@router.get(
    "/{group_id}",
    response_model=DocumentGroupResponse,
    summary="Get a document group",
)
def get_group(
    group_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve details of a specific document group."""
    group = db.query(DocumentGroup).filter(
        DocumentGroup.id == group_id,
        DocumentGroup.owner_id == current_user.id,
    ).first()
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document group not found",
        )
    return group


@router.get(
    "/{group_id}/documents",
    response_model=List[DocumentResponse],
    summary="Get all documents in a group",
)
def get_group_documents(
    group_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all documents that belong to a document group."""
    group = db.query(DocumentGroup).filter(
        DocumentGroup.id == group_id,
        DocumentGroup.owner_id == current_user.id,
    ).first()
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document group not found",
        )
    return group.documents


@router.post(
    "/{group_id}/link-answers",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger answer linking across documents in a group",
)
def trigger_answer_linking(
    group_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Manually trigger the answer-linking Celery task for a group.

    This matches answer-key question numbers with question-paper questions
    and updates the `answer` field on matched questions.

    This runs automatically when a document is uploaded to a group, but can
    also be triggered manually after both documents are processed.
    """
    group = db.query(DocumentGroup).filter(
        DocumentGroup.id == group_id,
        DocumentGroup.owner_id == current_user.id,
    ).first()
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document group not found",
        )
    task = link_answers_task.delay(group_id)
    return {
        "message": "Answer linking task dispatched",
        "task_id": task.id,
        "group_id": group_id,
    }
