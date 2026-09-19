"""Pydantic schemas for Document and DocumentGroup."""
from uuid import UUID
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from app.models.document import DocumentStatus, DocumentRole


class DocumentGroupCreate(BaseModel):
    name: str
    description: Optional[str] = None


class DocumentGroupResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    owner_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentResponse(BaseModel):
    id: UUID
    filename: str
    original_filename: str
    file_type: str
    file_size: int
    page_count: Optional[int]
    status: DocumentStatus
    document_role: DocumentRole
    error_message: Optional[str]
    celery_task_id: Optional[str]
    group_id: Optional[UUID]
    owner_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentUploadResponse(BaseModel):
    document_id: UUID
    message: str
    status: DocumentStatus
    celery_task_id: Optional[str] = None
