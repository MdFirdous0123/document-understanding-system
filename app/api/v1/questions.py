"""Question retrieval and answer key endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.document import Document
from app.models.question import Question, ExtractionWarning, ReviewStatus
from app.schemas.question import (
    QuestionResponse,
    QuestionListResponse,
    AnswerKeyResponse,
    ExtractionWarningResponse,
)

router = APIRouter(tags=["Questions"])


def _get_owned_document(document_id: str, user: User, db: Session) -> Document:
    """Fetch a document and verify the requesting user owns it."""
    doc = db.query(Document).filter(
        Document.id == document_id,
        Document.owner_id == user.id,
    ).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return doc


@router.get(
    "/documents/{document_id}/questions",
    response_model=QuestionListResponse,
    summary="Get all extracted questions from a document",
)
def get_questions(
    document_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    review_status: Optional[str] = Query(
        None, description="Filter: ok | needs_review | failed"
    ),
    min_confidence: Optional[float] = Query(
        None, ge=0.0, le=1.0, description="Minimum confidence threshold"
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve all questions extracted from a document.

    Supports filtering by:
    - **review_status**: ok, needs_review, failed
    - **min_confidence**: float 0.0–1.0
    """
    _get_owned_document(document_id, current_user, db)
    query = db.query(Question).filter(Question.document_id == document_id)
    if review_status:
        try:
            query = query.filter(Question.review_status == ReviewStatus(review_status))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid review_status '{review_status}'",
            )
    if min_confidence is not None:
        query = query.filter(Question.confidence >= min_confidence)
    total = query.count()
    questions = query.offset(skip).limit(limit).all()
    return QuestionListResponse(total=total, questions=questions)


@router.get(
    "/questions/{question_id}",
    response_model=QuestionResponse,
    summary="Get a single question by ID",
)
def get_question(
    question_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve a specific question with all its details."""
    q = db.query(Question).filter(Question.id == question_id).first()
    if not q:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found",
        )
    _get_owned_document(str(q.document_id), current_user, db)
    return q


@router.get(
    "/documents/{document_id}/answers",
    response_model=AnswerKeyResponse,
    summary="Get answer key summary for a document",
)
def get_answer_key(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return answer key information for all questions in a document.

    Shows how many questions have answers vs. are unmatched.
    """
    _get_owned_document(document_id, current_user, db)
    all_questions = (
        db.query(Question)
        .filter(Question.document_id == document_id)
        .all()
    )
    answered = [q for q in all_questions if q.answer is not None]
    unanswered = [q for q in all_questions if q.answer is None]
    return AnswerKeyResponse(
        total_questions=len(all_questions),
        answered=len(answered),
        unanswered=len(unanswered),
        questions=all_questions,
    )


@router.get(
    "/documents/{document_id}/warnings",
    response_model=List[ExtractionWarningResponse],
    summary="Get extraction warnings and review items for a document",
)
def get_warnings(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve all warnings generated during document processing.

    Warnings indicate issues such as:
    - Low OCR quality
    - Low confidence extractions
    - Questions that need human review
    - Unmatched answers
    """
    _get_owned_document(document_id, current_user, db)
    warnings = (
        db.query(ExtractionWarning)
        .filter(ExtractionWarning.document_id == document_id)
        .order_by(ExtractionWarning.created_at.asc())
        .all()
    )
    return warnings
