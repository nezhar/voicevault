from sqlalchemy import (
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.timeutils import utcnow
from enum import Enum
import uuid

from app.db.database import Base


class ProjectRole(str, Enum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    members = relationship(
        "ProjectMember",
        cascade="all, delete-orphan",
        backref="project",
    )


class ProjectMember(Base):
    __tablename__ = "project_members"

    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role = Column(SQLEnum(ProjectRole), nullable=False, default=ProjectRole.VIEWER)
    added_at = Column(DateTime, default=utcnow)

    user = relationship("User", lazy="joined")


class AccessRequestStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


class ProjectAccessRequest(Base):
    """One row per (project, user). A denied user re-requesting resets this row
    to pending rather than inserting a second one, so an owner's list can never
    be flooded by one person."""

    __tablename__ = "project_access_requests"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "user_id",
            name="uq_access_requests_project_user",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    status = Column(
        SQLEnum(AccessRequestStatus),
        nullable=False,
        default=AccessRequestStatus.PENDING,
    )
    message = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    decided_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    decided_at = Column(DateTime, nullable=True)

    # Two FKs point at users, so the join condition must be spelled out or
    # SQLAlchemy raises AmbiguousForeignKeysError when mappers configure.
    user = relationship("User", foreign_keys=[user_id], lazy="joined")
    decider = relationship("User", foreign_keys=[decided_by], lazy="joined")
