from enum import Enum
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.entry import Entry
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


def get_membership(
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


def visible_entries_filter(user: User):
    """Filter clause: own entries OR entries in projects the user is a member of."""

    member_projects = select(ProjectMember.project_id).where(
        ProjectMember.user_id == user.id,
    )
    return or_(Entry.user_id == user.id, Entry.project_id.in_(member_projects))


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
) -> ProjectMember:
    membership = get_membership(db, project.id, user.id)
    if membership is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if ROLE_ORDER[membership.role] < ROLE_ORDER[min_role]:
        raise _FORBIDDEN
    return membership
