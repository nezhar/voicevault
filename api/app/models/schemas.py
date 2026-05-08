import json

from pydantic import BaseModel, Field, HttpUrl, computed_field, field_validator
from typing import Any, List, Optional
from datetime import datetime
from uuid import UUID
from .entry import EntryStatus, SourceType


class TranscriptWord(BaseModel):
    """A single transcribed word with start/end timestamps in seconds (millisecond precision)."""

    word: str
    start: float
    end: float


class TranscriptSegment(BaseModel):
    """A transcribed segment (typically a sentence/phrase) with start/end timestamps in seconds."""

    text: str
    start: float
    end: float

class EntryCreate(BaseModel):
    title: str
    source_url: Optional[HttpUrl] = None

    model_config = {"from_attributes": True}


class EntryTranscriptCreate(BaseModel):
    title: str
    transcript: str = Field(..., min_length=1)

    model_config = {"from_attributes": True}

class EntryUpload(BaseModel):
    title: str

def _parse_json_list(value: Any) -> Any:
    """Decode JSON-encoded list columns into structured data."""
    if value is None or isinstance(value, list):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return None
    return value


class EntryResponse(BaseModel):
    id: UUID
    title: str
    source_type: SourceType
    source_url: Optional[str] = None
    filename: Optional[str] = None
    # Internal storage path — pulled from the ORM so we can derive has_audio,
    # but excluded from API output.
    file_path: Optional[str] = Field(default=None, exclude=True, repr=False)
    status: EntryStatus
    archived: bool = False
    transcript: Optional[str] = None
    transcript_words: Optional[List[TranscriptWord]] = None
    transcript_segments: Optional[List[TranscriptSegment]] = None
    summary: Optional[str] = None
    speakers: Optional[str] = None
    additional_context: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @computed_field
    @property
    def has_audio(self) -> bool:
        """True when the entry has a stored audio file ready to stream."""
        return bool(self.file_path)

    @field_validator("transcript_words", mode="before")
    @classmethod
    def _parse_transcript_words(cls, value: Any) -> Any:
        return _parse_json_list(value)

    @field_validator("transcript_segments", mode="before")
    @classmethod
    def _parse_transcript_segments(cls, value: Any) -> Any:
        return _parse_json_list(value)

class EntryStatusUpdate(BaseModel):
    status: EntryStatus

class EntryArchiveUpdate(BaseModel):
    archived: bool

class EntryMetadataUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    speakers: Optional[str] = Field(default=None, max_length=2000)
    additional_context: Optional[str] = Field(default=None, max_length=5000)
    regenerate_transcript: bool = False

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
