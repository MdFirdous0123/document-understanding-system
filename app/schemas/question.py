"""Pydantic schemas for Question and ExtractionWarning."""
from uuid import UUID
from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel
from app.models.question import QuestionType, ReviewStatus, AnswerSource, WarningSeverity


class OptionSchema(BaseModel):
    label: str   # A, B, C, D or 1, 2, 3
    text: str


class QuestionResponse(BaseModel):
    id: UUID
    document_id: UUID
    question_number: Optional[str]
    question_text: str
    options: Optional[List[Any]]
    question_type: QuestionType
    has_image: bool
    has_table: bool
    answer: Optional[str]
    answer_source: AnswerSource
    answer_confidence: float
    confidence: float
    review_status: ReviewStatus
    source_pages: Optional[List[int]]
    extraction_warnings: Optional[List[str]]
    created_at: datetime

    model_config = {"from_attributes": True}


class ExtractionWarningResponse(BaseModel):
    id: UUID
    document_id: UUID
    question_id: Optional[UUID]
    page_number: Optional[int]
    warning_type: str
    message: str
    severity: WarningSeverity
    created_at: datetime

    model_config = {"from_attributes": True}


class QuestionListResponse(BaseModel):
    total: int
    questions: List[QuestionResponse]


class AnswerKeyResponse(BaseModel):
    total_questions: int
    answered: int
    unanswered: int
    questions: List[QuestionResponse]
