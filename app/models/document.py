"""Document ORM model with status and role tracking."""
import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, Integer, DateTime, ForeignKey, Enum as SAEnum
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class DocumentStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentRole(str, enum.Enum):
    QUESTION_PAPER = "question_paper"
    ANSWER_KEY = "answer_key"
    MIXED = "mixed"       # Contains both questions and answers
    UNKNOWN = "unknown"


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255), nullable=False)            # stored filename on disk
    original_filename = Column(String(255), nullable=False)   # as uploaded by user
    file_path = Column(String(1024), nullable=False)
    file_type = Column(String(50), nullable=False)            # pdf, jpg, png
    file_size = Column(Integer, nullable=False)               # bytes
    page_count = Column(Integer, nullable=True)
    status = Column(
        SAEnum(DocumentStatus), default=DocumentStatus.PENDING, nullable=False
    )
    document_role = Column(
        SAEnum(DocumentRole), default=DocumentRole.UNKNOWN, nullable=False
    )
    error_message = Column(Text, nullable=True)
    celery_task_id = Column(String(255), nullable=True)
    owner_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    group_id = Column(
        UUID(as_uuid=True),
        ForeignKey("document_groups.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    owner = relationship("User", back_populates="documents")
    group = relationship("DocumentGroup", back_populates="documents")
    questions = relationship(
        "Question", back_populates="document", cascade="all, delete-orphan"
    )
    warnings = relationship(
        "ExtractionWarning", back_populates="document", cascade="all, delete-orphan"
    )
