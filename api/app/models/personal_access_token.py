import uuid

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID

from app.core.timeutils import utcnow
from app.db.database import Base


class PersonalAccessToken(Base):
    __tablename__ = "personal_access_tokens"
    __table_args__ = (
        Index("ix_personal_access_tokens_created_at", "created_at"),
        Index("ix_personal_access_tokens_user_created_at", "user_id", "created_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # No single-column index on user_id: ix_personal_access_tokens_user_created_at
    # covers every user_id lookup as its leading column.
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(100), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    token_prefix = Column(String(24), nullable=False)
    permissions = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    expires_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    # Capability names (column name kept from the scope era).
    # project_ids: NULL = every project the owner can reach; otherwise only
    # these, and the owner's personal entries are out of reach.
    project_ids = Column(JSON, nullable=True)
    source = Column(String(16), nullable=False, default="manual")  # manual | oauth
    oauth_client_id = Column(String(64), nullable=True)
