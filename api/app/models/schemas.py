from pydantic import BaseModel, Field, HttpUrl
from typing import Optional
from datetime import datetime
from uuid import UUID
from .entry import EntryStatus, SourceType

class EntryCreate(BaseModel):
    title: str
    source_url: Optional[HttpUrl] = None

    model_config = {"from_attributes": True}

class EntryUpload(BaseModel):
    title: str

class EntryResponse(BaseModel):
    id: UUID
    title: str
    source_type: SourceType
    source_url: Optional[str] = None
    filename: Optional[str] = None
    status: EntryStatus
    archived: bool = False
    transcript: Optional[str] = None
    summary: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class EntryStatusUpdate(BaseModel):
    status: EntryStatus

class EntryArchiveUpdate(BaseModel):
    archived: bool

class EntryList(BaseModel):
    entries: list[EntryResponse]
    total: int
    page: int
    per_page: int
    total_pages: int
    has_next: bool
    has_previous: bool

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    timestamp: Optional[datetime] = None

class ChatRequest(BaseModel):
    message: str
    conversation_history: Optional[list[ChatMessage]] = None

class ChatResponse(BaseModel):
    message: str
    timestamp: datetime
    
class SummaryResponse(BaseModel):
    summary: str
    timestamp: datetime


class PromptTemplateCreate(BaseModel):
    label: str = Field(..., min_length=1, max_length=255)
    preview_text: Optional[str] = Field(default=None, max_length=512)
    body_markdown: str = Field(..., min_length=1)
    sort_order: int = 0
    is_active: bool = True


class PromptTemplateUpdate(BaseModel):
    label: Optional[str] = Field(default=None, min_length=1, max_length=255)
    preview_text: Optional[str] = Field(default=None, max_length=512)
    body_markdown: Optional[str] = Field(default=None, min_length=1)
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class PromptTemplateResponse(BaseModel):
    id: UUID
    label: str
    preview_text: Optional[str] = None
    body_markdown: str
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
