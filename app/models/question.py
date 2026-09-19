"""Question and ExtractionWarning ORM models."""
import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, Float, Integer, Boolean, DateTime,
    ForeignKey, Enum as SAEnum
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.core.database import Base


class QuestionType(str, enum.Enum):
    MCQ = "mcq"
    SHORT_ANSWER = "short_answer"
    LONG_ANSWER = "long_answer"
    TRUE_FALSE = "true_false"
    FILL_BLANK = "fill_in_the_blank"
    UNKNOWN = "unknown"


class ReviewStatus(str, enum.Enum):
    OK = "ok"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


class AnswerSource(str, enum.Enum):
    SAME_DOCUMENT = "same_document"
    LINKED_DOCUMENT = "linked_document"
    UNMATCHED = "unmatched"
    UNKNOWN = "unknown"


class WarningSeverity(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class Question(Base):
    __tablename__ = "questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Question content
    question_number = Column(String(50), nullable=True)   # "1", "Q.2", "(iii)", or null
    question_text = Column(Text, nullable=False)
    options = Column(JSONB, nullable=True)                # [{"label": "A", "text": "..."}]
    question_type = Column(SAEnum(QuestionType), default=QuestionType.UNKNOWN)
    has_image = Column(Boolean, default=False)
    has_table = Column(Boolean, default=False)

    # Answer info
    answer = Column(Text, nullable=True)
    answer_source = Column(SAEnum(AnswerSource), default=AnswerSource.UNKNOWN)
    answer_confidence = Column(Float, default=0.0)

    # Extraction quality metadata
    confidence = Column(Float, default=0.0)               # 0.0 to 1.0
    review_status = Column(SAEnum(ReviewStatus), default=ReviewStatus.NEEDS_REVIEW)
    source_pages = Column(JSONB, default=list)            # [1, 2] page numbers
    raw_extracted_text = Column(Text, nullable=True)
    extraction_warnings = Column(JSONB, default=list)     # list of warning strings

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    document = relationship("Document", back_populates="questions")


class ExtractionWarning(Base):
    """Records issues encountered during document processing."""

    __tablename__ = "extraction_warnings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_id = Column(
        UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="SET NULL"),
        nullable=True,
    )
    page_number = Column(Integer, nullable=True)
    warning_type = Column(String(100), nullable=False)   # low_confidence, ocr_error, etc.
    message = Column(Text, nullable=False)
    severity = Column(SAEnum(WarningSeverity), default=WarningSeverity.WARNING)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    document = relationship("Document", back_populates="warnings")
