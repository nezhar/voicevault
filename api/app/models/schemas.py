from pydantic import BaseModel, HttpUrl
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
    transcript: Optional[str] = None
    summary: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class EntryStatusUpdate(BaseModel):
    status: EntryStatus

class EntryList(BaseModel):
    entries: list[EntryResponse]
    total: int
    page: int
    per_page: int

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
