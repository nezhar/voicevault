from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from app.core.timeutils import utcnow

from app.db.database import Base


class AuthSession(Base):
    __tablename__ = "sessions"

    id = Column(String(128), primary_key=True)  # sha256 hex of the opaque token
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime, default=utcnow)
    expires_at = Column(DateTime, nullable=False)
