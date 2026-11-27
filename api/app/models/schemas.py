import json
from enum import Enum

from pydantic import BaseModel, Field, HttpUrl, computed_field, field_validator
from typing import Any, Literal
from datetime import datetime, timezone
from uuid import UUID
from .entry import EntryStatus, SourceType
from .project import AccessRequestStatus, ProjectRole
from .upload_session import UploadState
from app.core.timeutils import UTCDatetime, utcnow
from app.core.capabilities import normalize_token_capabilities


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


class SubtitleFormat(str, Enum):
    SRT = "srt"


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
    # Effective capabilities of the caller (cut down to the token for a PAT):
    # global ones, and per project the ones that hold there in addition.
    capabilities: list[str] = []
    project_capabilities: dict[str, list[str]] = {}

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
    # Capability names; the old scope names (entries:read, ...) are converted.
    permissions: list[str] = Field(..., min_length=1)
    # Limit the token to these projects; omitted = every project the owner reaches.
    project_ids: list[UUID] | None = None
    expires_at: datetime | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return _normalize_pat_name(value)

    @field_validator("permissions")
    @classmethod
    def known_permissions(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("permissions must not contain duplicates")
        return normalize_token_capabilities(value)

    @field_validator("project_ids")
    @classmethod
    def unique_projects(cls, value: list[UUID] | None) -> list[UUID] | None:
        if value is None:
            return None
        if not value:
            raise ValueError("project_ids must not be empty; omit it for all projects")
        return sorted(set(value), key=str)

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
    permissions: list[str]
    project_ids: list[UUID] | None = None
    source: str = "manual"
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


class ProjectGroupResponse(BaseModel):
    group_id: UUID
    name: str
    role: ProjectRole
    member_count: int | None = None  # None for Everyone: every user
    is_builtin: bool = False


class ProjectGroupAdd(BaseModel):
    group_id: UUID
    role: ProjectRole = ProjectRole.VIEWER


class ProjectGroupUpdate(BaseModel):
    role: ProjectRole


class ProjectDetailResponse(ProjectResponse):
    members: list[ProjectMemberResponse]
    groups: list[ProjectGroupResponse] = []
    # Groups the caller's access comes through (empty: direct membership only).
    my_access_via: list[str] = []


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


class UploadSessionCreate(BaseModel):
    """An upload link; every field is optional and checked again on upload."""

    title: str | None = Field(default=None, max_length=255)
    filename: str | None = Field(default=None, max_length=255)
    size_bytes: int | None = Field(default=None, ge=1)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    language: str | None = Field(default=None, max_length=16)
    project_id: UUID | None = None

    @field_validator("language", mode="before")
    @classmethod
    def _norm_language(cls, value: Any) -> Any:
        return _normalize_language(value)

    @field_validator("title", "filename", mode="before")
    @classmethod
    def _blank_is_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value.strip() if isinstance(value, str) else value


class UploadSessionResponse(BaseModel):
    id: UUID
    state: UploadState
    title: str | None = None
    filename: str | None = None
    language: str | None = None
    project_id: UUID | None = None
    expected_size_bytes: int | None = None
    max_bytes: int
    created_at: UTCDatetime
    expires_at: UTCDatetime
    completed_at: UTCDatetime | None = None
    entry_id: UUID | None = None


class UploadSessionCreated(UploadSessionResponse):
    # Shown once: the link's secret, as a bearer token and inside browser_url.
    token: str
    upload_url: str
    browser_url: str


class UploadLinkInfo(UploadSessionResponse):
    """What the browser upload page needs to know about its link."""

    supported_formats: list[str]


class UploadCompleted(BaseModel):
    status: Literal["uploaded"] = "uploaded"
    upload_id: UUID
    entry: EntryResponse


class CapabilityInfoResponse(BaseModel):
    name: str
    label: str
    area: str
    description: str
    project_scoped: bool
    routes: list[str]
    tools: list[str]


class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    idp_group: str | None = Field(default=None, max_length=255)


class GroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    idp_group: str | None = Field(default=None, max_length=255)

    def changes(self) -> dict:
        return self.model_dump(exclude_unset=True)


class GroupMemberResponse(BaseModel):
    user_id: UUID
    email: str
    display_name: str
    source: str  # manual | idp


class GroupResponse(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    idp_group: str | None = None
    is_builtin: bool = False
    member_count: int | None = None  # None for Everyone


class GroupDetailResponse(GroupResponse):
    members: list[GroupMemberResponse] = []


class GroupMemberAdd(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)


class ProjectRef(BaseModel):
    id: UUID
    name: str


class GrantItem(BaseModel):
    capability: str
    project_id: UUID | None = None
    project_name: str | None = None


class GrantSet(BaseModel):
    grants: list[GrantItem]


class EffectiveGrantResponse(BaseModel):
    capability: str
    project_id: UUID | None = None
    project_name: str | None = None
    source: str  # "user", "admin" or a group name


class UserPermissionsResponse(BaseModel):
    user_id: UUID
    is_admin: bool
    capabilities: list[str]
    project_capabilities: dict[str, list[str]]
    grants: list[EffectiveGrantResponse]
    groups: list[str]


class OAuthRequestInfo(BaseModel):
    id: UUID
    client_name: str
    redirect_uri: str
    # Capabilities the client asked for (as OAuth scopes) that the user holds.
    requested_capabilities: list[str]
    expires_at: UTCDatetime


class OAuthApproval(BaseModel):
    permissions: list[str] = Field(..., min_length=1)
    project_ids: list[UUID] | None = None

    @field_validator("permissions")
    @classmethod
    def known_permissions(cls, value: list[str]) -> list[str]:
        return normalize_token_capabilities(value)

    @field_validator("project_ids")
    @classmethod
    def unique_projects(cls, value: list[UUID] | None) -> list[UUID] | None:
        if value is None:
            return None
        if not value:
            raise ValueError("project_ids must not be empty; omit it for all projects")
        return sorted(set(value), key=str)


class OAuthRedirect(BaseModel):
    redirect_to: str
