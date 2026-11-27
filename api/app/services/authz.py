from dataclasses import dataclass, field
from enum import Enum
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.entry import Entry
from app.models.group import Group, GroupMember, ProjectGroupMember
from app.models.project import ProjectMember, ProjectRole
from app.models.user import User


class AccessLevel(str, Enum):
    VIEW = "view"
    EDIT = "edit"
    OWNER = "owner"


ROLE_ORDER = {
    ProjectRole.VIEWER: 0,
    ProjectRole.EDITOR: 1,
    ProjectRole.OWNER: 2,
}

_NOT_FOUND = HTTPException(status_code=404, detail="Entry not found")
_FORBIDDEN = HTTPException(status_code=403, detail="Insufficient permissions")


@dataclass
class Membership:
    """A user's standing in a project: the highest role of their direct
    membership and of every group the project is shared with."""

    user_id: UUID
    role: ProjectRole
    direct: ProjectMember | None = None
    via_groups: list[str] = field(default_factory=list)


def user_group_ids_select(user_id: UUID):
    """Groups the user belongs to, including the built-in Everyone group."""

    return (
        select(GroupMember.group_id)
        .where(GroupMember.user_id == user_id)
        .union(select(Group.id).where(Group.is_builtin.is_(True)))
    )


def group_project_ids_select(user_id: UUID):
    return select(ProjectGroupMember.project_id).where(
        ProjectGroupMember.group_id.in_(user_group_ids_select(user_id)),
    )


def get_direct_membership(
    db: Session,
    project_id: UUID,
    user_id: UUID,
) -> ProjectMember | None:
    return (
        db.query(ProjectMember)
        .filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
        .first()
    )


def get_membership(
    db: Session,
    project_id: UUID,
    user_id: UUID,
) -> Membership | None:
    direct = get_direct_membership(db, project_id, user_id)
    shares = (
        db.query(ProjectGroupMember)
        .filter(
            ProjectGroupMember.project_id == project_id,
            ProjectGroupMember.group_id.in_(user_group_ids_select(user_id)),
        )
        .all()
    )
    if direct is None and not shares:
        return None
    roles = [share.role for share in shares]
    if direct is not None:
        roles.append(direct.role)
    return Membership(
        user_id=user_id,
        role=max(roles, key=lambda role: ROLE_ORDER[role]),
        direct=direct,
        via_groups=sorted(share.group.name for share in shares),
    )


def require_project_editor(db: Session, project_id: UUID, user: User) -> None:
    """Adding an entry to a project needs at least the editor role there."""

    membership = get_membership(db, project_id, user.id)
    if membership is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if ROLE_ORDER[membership.role] < ROLE_ORDER[ProjectRole.EDITOR]:
        raise HTTPException(
            status_code=403,
            detail="Editor role required to add entries to this project",
        )


def visible_entries_filter(user: User):
    """Filter clause: own entries OR entries in projects the user reaches,
    directly or through a group."""

    member_projects = select(ProjectMember.project_id).where(
        ProjectMember.user_id == user.id,
    )
    return or_(
        Entry.user_id == user.id,
        Entry.project_id.in_(member_projects),
        Entry.project_id.in_(group_project_ids_select(user.id)),
    )


def require_entry_access(
    db: Session,
    entry: Entry,
    user: User,
    level: AccessLevel,
) -> None:
    """Enforce the spec's role matrix. 404 when invisible, 403 when role too low.

    Principle: the entry owner always keeps full control; project roles never
    allow permanent deletion of someone else's entry.
    """

    if entry.user_id == user.id:
        return  # entry owner: every level

    membership = (
        get_membership(db, entry.project_id, user.id) if entry.project_id else None
    )
    if membership is None:
        raise _NOT_FOUND  # invisible: no existence leak

    if level == AccessLevel.VIEW:
        return
    if level == AccessLevel.EDIT:
        if ROLE_ORDER[membership.role] >= ROLE_ORDER[ProjectRole.EDITOR]:
            return
        raise _FORBIDDEN
    # AccessLevel.OWNER: only the entry owner may delete — no project role suffices
    raise _FORBIDDEN


def require_project_role(
    db: Session,
    project,
    user: User,
    min_role: ProjectRole,
) -> Membership:
    membership = get_membership(db, project.id, user.id)
    if membership is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if ROLE_ORDER[membership.role] < ROLE_ORDER[min_role]:
        raise _FORBIDDEN
    return membership
