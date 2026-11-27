import uuid
from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.timeutils import utcnow
from app.db.database import Base
from app.models.project import ProjectRole

EVERYONE_GROUP_NAME = "Everyone"


class MembershipSource(str, Enum):
    MANUAL = "manual"
    IDP = "idp"


class Group(Base):
    """A set of users that capabilities and project access can be given to.

    The built-in Everyone group (is_builtin) has no member rows: every user
    belongs to it implicitly.
    """

    __tablename__ = "groups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    # Group name as the IdP sends it in the groups claim, stored lowercased.
    idp_group = Column(String(255), nullable=True, unique=True)
    is_builtin = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=utcnow)

    members = relationship(
        "GroupMember",
        cascade="all, delete-orphan",
        backref="group",
    )


class GroupMember(Base):
    __tablename__ = "group_members"

    group_id = Column(
        UUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    source = Column(SQLEnum(MembershipSource), primary_key=True)
    added_at = Column(DateTime, default=utcnow)

    user = relationship("User", lazy="joined")


class ProjectGroupMember(Base):
    """A project shared with a whole group. Roles: viewer or editor only."""

    __tablename__ = "project_group_members"

    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    group_id = Column(
        UUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role = Column(SQLEnum(ProjectRole), nullable=False, default=ProjectRole.VIEWER)
    added_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    added_at = Column(DateTime, default=utcnow)

    group = relationship("Group", lazy="joined")
