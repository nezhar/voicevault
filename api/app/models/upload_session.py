import uuid
from enum import Enum

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID

from app.core.timeutils import utcnow
from app.db.database import Base


class UploadState(str, Enum):
    PENDING = "pending"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    EXPIRED = "expired"


class UploadSession(Base):
    """A single-use link that turns one uploaded file into an entry.

    The entry only exists once the bytes have arrived, so abandoned links never
    show up as entries. project_id, pat_id and entry_id are plain references:
    each is re-checked when the link is used, and deleting the project, token
    or resulting entry must not be blocked by an old upload link.
    """

    __tablename__ = "upload_sessions"
    __table_args__ = (
        Index("ix_upload_sessions_user_created_at", "user_id", "created_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # The PAT that created the link, if any: revoking it also revokes the link.
    pat_id = Column(UUID(as_uuid=True), nullable=True)
    token_hash = Column(String(64), nullable=False, unique=True)
    title = Column(String(255), nullable=True)
    filename = Column(String(255), nullable=True)
    language = Column(String(16), nullable=True)
    project_id = Column(UUID(as_uuid=True), nullable=True)
    expected_size_bytes = Column(BigInteger, nullable=True)
    expected_sha256 = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    expires_at = Column(DateTime, nullable=False)
    # Set while the received file is being stored; cleared again on failure.
    claimed_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    entry_id = Column(UUID(as_uuid=True), nullable=True)
