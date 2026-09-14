import json

from pydantic import BaseModel, Field, HttpUrl, computed_field, field_validator
from typing import Any
from datetime import datetime, timezone
from uuid import UUID
from .entry import EntryStatus, SourceType
from .project import AccessRequestStatus, ProjectRole
from app.core.timeutils import UTCDatetime, utcnow
from app.services.pat_service import PATPermission


def _normalize_language(value: Any) -> Any:
    """Treat empty / 'auto' as None; otherwise lowercase + strip the ISO code."""
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if not cleaned or cleaned == "auto":
            return None
        return cleaned
    return value


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
    source_url: HttpUrl | None = None
    language: str | None = Field(default=None, max_length=16)
    project_id: UUID | None = None

    model_config = {"from_attributes": True}

    @field_validator("language", mode="before")
    @classmethod
    def _norm_language(cls, value: Any) -> Any:
        return _normalize_language(value)


class EntryTranscriptCreate(BaseModel):
    title: str
    transcript: str = Field(..., min_length=1)
    language: str | None = Field(default=None, max_length=16)
    project_id: UUID | None = None

    model_config = {"from_attributes": True}

    @field_validator("language", mode="before")
    @classmethod
    def _norm_language(cls, value: Any) -> Any:
        return _normalize_language(value)


class EntryUpload(BaseModel):
    title: str
    language: str | None = Field(default=None, max_length=16)

    @field_validator("language", mode="before")
    @classmethod
    def _norm_language(cls, value: Any) -> Any:
        return _normalize_language(value)


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


class EntryOwner(BaseModel):
    id: UUID
    display_name: str

    class Config:
        from_attributes = True


class EntryProjectUpdate(BaseModel):
    project_id: UUID | None = None


class EntryResponse(BaseModel):
    id: UUID
    title: str
    source_type: SourceType
    source_url: str | None = None
    filename: str | None = None
    # Internal storage path — pulled from the ORM so we can derive has_audio,
    # but excluded from API output.
    file_path: str | None = Field(default=None, exclude=True, repr=False)
    status: EntryStatus
    archived: bool = False
    project_id: UUID | None = None
    owner: EntryOwner | None = None
    transcript: str | None = None
    transcript_words: list[TranscriptWord] | None = None
    transcript_segments: list[TranscriptSegment] | None = None
    summary: str | None = None
    speakers: str | None = None
    additional_context: str | None = None
    language: str | None = None
    error_message: str | None = None
    created_at: UTCDatetime
    updated_at: UTCDatetime

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
    title: str | None = Field(default=None, min_length=1, max_length=255)
    speakers: str | None = Field(default=None, max_length=2000)
    additional_context: str | None = Field(default=None, max_length=5000)
    language: str | None = Field(default=None, max_length=16)
    language_set: bool = False
    regenerate_transcript: bool = False

    @field_validator("language", mode="before")
    @classmethod
    def _norm_language(cls, value: Any) -> Any:
        return _normalize_language(value)


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
    timestamp: UTCDatetime | None = None


class ChatRequest(BaseModel):
    message: str
    conversation_history: list[ChatMessage] | None = None


class ChatResponse(BaseModel):
    message: str
    timestamp: UTCDatetime


class SummaryResponse(BaseModel):
    summary: str
    timestamp: UTCDatetime


class PromptTemplateCreate(BaseModel):
    label: str = Field(..., min_length=1, max_length=255)
    preview_text: str | None = Field(default=None, max_length=512)
    body_markdown: str = Field(..., min_length=1)
    sort_order: int = 0
    is_active: bool = True


class PromptTemplateUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=255)
    preview_text: str | None = Field(default=None, max_length=512)
    body_markdown: str | None = Field(default=None, min_length=1)
    sort_order: int | None = None
    is_active: bool | None = None


class PromptTemplateResponse(BaseModel):
    id: UUID
    label: str
    preview_text: str | None = None
    body_markdown: str
    sort_order: int
    is_active: bool
    created_at: UTCDatetime
    updated_at: UTCDatetime

    class Config:
        from_attributes = True


class AuthConfigResponse(BaseModel):
    mode: str  # "none" | "token" | "oidc"
    # Public: lets the UI show MCP connection details only when /mcp answers.
    mcp_enabled: bool = False


class UserResponse(BaseModel):
    id: UUID
    email: str
    display_name: str
    is_admin: bool = False
    is_active: bool = True

    class Config:
        from_attributes = True


def _normalize_pat_name(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("name cannot be blank")
    return value


def _normalize_pat_expiry(value: datetime | None) -> datetime | None:
    """Normalize to naive UTC (how the database stores it) and reject the past."""

    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    if value <= utcnow():
        raise ValueError("expires_at must be in the future")
    return value


class PersonalAccessTokenCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    permissions: list[PATPermission] = Field(..., min_length=1)
    expires_at: datetime | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return _normalize_pat_name(value)

    @field_validator("permissions")
    @classmethod
    def unique_permissions(cls, value: list[PATPermission]) -> list[PATPermission]:
        if len(value) != len(set(value)):
            raise ValueError("permissions must not contain duplicates")
        return value

    @field_validator("expires_at")
    @classmethod
    def expires_in_the_future(cls, value: datetime | None) -> datetime | None:
        return _normalize_pat_expiry(value)


class PersonalAccessTokenUpdate(BaseModel):
    """Rename and/or change expiry. Omitted fields are left alone; an explicit
    ``"expires_at": null`` removes the expiry. Permissions are immutable: widening
    a token's scope after the fact would defeat the point of scoping it."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    expires_at: datetime | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return None if value is None else _normalize_pat_name(value)

    @field_validator("expires_at")
    @classmethod
    def expires_in_the_future(cls, value: datetime | None) -> datetime | None:
        return _normalize_pat_expiry(value)

    def changes(self) -> dict:
        """Only the fields the client actually sent."""

        return self.model_dump(exclude_unset=True)


class PersonalAccessTokenResponse(BaseModel):
    id: UUID
    name: str
    token_prefix: str
    permissions: list[PATPermission]
    created_at: UTCDatetime
    expires_at: UTCDatetime | None
    last_used_at: UTCDatetime | None
    revoked_at: UTCDatetime | None

    class Config:
        from_attributes = True


class PersonalAccessTokenCreated(PersonalAccessTokenResponse):
    token: str

    @classmethod
    def from_pat(cls, pat, token: str) -> "PersonalAccessTokenCreated":
        """The one response that carries the secret; built from the ORM row plus the raw token."""

        return cls(
            **PersonalAccessTokenResponse.model_validate(pat).model_dump(),
            token=token,
        )


class PATUserResponse(BaseModel):
    id: UUID
    email: str
    display_name: str
    is_active: bool

    class Config:
        from_attributes = True


class AdminPersonalAccessTokenResponse(PersonalAccessTokenResponse):
    user: PATUserResponse

    @classmethod
    def from_row(cls, pat, user) -> "AdminPersonalAccessTokenResponse":
        return cls(
            **PersonalAccessTokenResponse.model_validate(pat).model_dump(),
            user=PATUserResponse.model_validate(user),
        )


class AdminPersonalAccessTokenListResponse(BaseModel):
    tokens: list[AdminPersonalAccessTokenResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


class UserActivationUpdate(BaseModel):
    is_active: bool


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)


class ProjectMemberAdd(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    role: ProjectRole = ProjectRole.VIEWER


class ProjectMemberUpdate(BaseModel):
    role: ProjectRole


class ProjectMemberResponse(BaseModel):
    user_id: UUID
    email: str
    display_name: str
    role: ProjectRole


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    created_by: UUID
    created_at: UTCDatetime
    updated_at: UTCDatetime
    my_role: ProjectRole
    member_count: int
    entry_count: int
    # Only non-zero for owners; other roles never see the badge.
    pending_request_count: int = 0


class ProjectDetailResponse(ProjectResponse):
    members: list[ProjectMemberResponse]


class ProjectOwnerResponse(BaseModel):
    display_name: str
    email: str


class ProjectPreviewResponse(BaseModel):
    """Everything a permalink reveals to someone who is not a member."""

    id: UUID
    name: str
    owners: list[ProjectOwnerResponse]
    my_role: ProjectRole | None = None
    request_status: AccessRequestStatus | None = None
    request_id: UUID | None = None
    can_request: bool = False


class AccessRequestCreate(BaseModel):
    message: str | None = Field(default=None, max_length=500)


class AccessRequestDecision(BaseModel):
    role: ProjectRole = ProjectRole.VIEWER


class AccessRequestResponse(BaseModel):
    id: UUID
    project_id: UUID
    user_id: UUID
    email: str
    display_name: str
    status: AccessRequestStatus
    message: str | None = None
    created_at: UTCDatetime
    decided_at: UTCDatetime | None = None
    decided_by_name: str | None = None


class AdminSystemStatsResponse(BaseModel):
    users_total: int
    users_active_30d: int
    users_new_30d: int
    entries_total: int
    entries_archived: int
    entries_by_status: dict[str, int]
    entries_by_source: dict[str, int]
    storage_bytes_total: int
    duration_seconds_total: float
    words_total: int
    projects_total: int
    # Entries whose metrics are unknown, so the dashboard can say the totals
    # are a lower bound rather than silently under-reporting.
    entries_missing_metrics: int
    # Entries with no owner (user_id IS NULL). They are inside the totals above
    # but cannot appear in any per-user row, so the dashboard says so instead of
    # leaving the two views quietly disagreeing.
    entries_unassigned: int


class AdminUserStatsResponse(BaseModel):
    id: UUID
    email: str
    display_name: str
    is_admin: bool
    is_system: bool
    is_active: bool
    created_at: UTCDatetime | None
    last_login_at: UTCDatetime | None
    entry_count: int
    storage_bytes: int
    duration_seconds: float
    word_count: int
    error_count: int
    project_count: int


class AdminUserListResponse(BaseModel):
    total: int
    users: list[AdminUserStatsResponse]
