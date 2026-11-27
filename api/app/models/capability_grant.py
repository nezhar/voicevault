import uuid

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID

from app.core.timeutils import utcnow
from app.db.database import Base


class CapabilityGrant(Base):
    """One capability for one user or group, globally (project_id NULL) or in
    one project. Grants only ever add; uniqueness per subject is kept by
    PermissionService, which replaces a subject's grants as a whole."""

    __tablename__ = "capability_grants"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NULL) <> (group_id IS NULL)",
            name="ck_capability_grants_one_subject",
        ),
        Index("ix_capability_grants_user", "user_id"),
        Index("ix_capability_grants_group", "group_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    group_id = Column(
        UUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=True,
    )
    capability = Column(String(64), nullable=False)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
    )
    granted_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, default=utcnow)
