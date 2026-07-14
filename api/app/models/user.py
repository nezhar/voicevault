from sqlalchemy import Boolean, Column, DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.core.timeutils import utcnow
import uuid

from app.db.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("issuer", "subject", name="uq_users_issuer_subject"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    issuer = Column(String(512), nullable=True)  # NULL for the system user
    subject = Column(String(512), nullable=True)
    email = Column(String(320), nullable=False, unique=True)  # stored lowercased
    display_name = Column(String(255), nullable=False)
    is_system = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=utcnow)
    last_login_at = Column(DateTime, nullable=True)
