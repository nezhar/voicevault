"""Groups: admin-managed sets of users, optionally mirrored from the IdP.

Membership has two sources. Manual members are added by an admin; IdP
members come from the OIDC groups claim and are reconciled at every login, so
they always match what the IdP last said. The two never touch each other.
"""

from uuid import UUID

from loguru import logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.group import Group, GroupMember, MembershipSource
from app.models.user import User
from app.services.pat_service import LIKE_ESCAPE, escape_like
from app.services.permission_service import PermissionService


class GroupError(ValueError):
    pass


def _normalize_idp_group(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip().lower()
    return value or None


class GroupService:
    def __init__(self, db: Session):
        self.db = db

    def list_groups(
        self,
        search: str | None = None,
        limit: int | None = None,
    ) -> list[Group]:
        query = self.db.query(Group)
        if search and search.strip():
            pattern = f"%{escape_like(search.strip())}%"
            query = query.filter(Group.name.ilike(pattern, escape=LIKE_ESCAPE))
        query = query.order_by(Group.is_builtin.desc(), func.lower(Group.name))
        if limit is not None:
            query = query.limit(limit)
        return query.all()

    def get(self, group_id: UUID) -> Group | None:
        return self.db.get(Group, group_id)

    def member_count(self, group: Group) -> int | None:
        """Distinct members; None for Everyone, which holds every user."""

        if group.is_builtin:
            return None
        return (
            self.db.query(func.count(func.distinct(GroupMember.user_id)))
            .filter(GroupMember.group_id == group.id)
            .scalar()
        )

    def members(self, group: Group) -> list[GroupMember]:
        return (
            self.db.query(GroupMember)
            .filter(GroupMember.group_id == group.id)
            .order_by(GroupMember.added_at)
            .all()
        )

    def _check_unique(
        self,
        name: str | None,
        idp_group: str | None,
        exclude: UUID | None,
    ):
        if name is not None:
            clash = self.db.query(Group).filter(func.lower(Group.name) == name.lower())
            if exclude is not None:
                clash = clash.filter(Group.id != exclude)
            if clash.first() is not None:
                raise GroupError(f'A group named "{name}" already exists')
        if idp_group is not None:
            clash = self.db.query(Group).filter(Group.idp_group == idp_group)
            if exclude is not None:
                clash = clash.filter(Group.id != exclude)
            if clash.first() is not None:
                raise GroupError(
                    f'IdP group "{idp_group}" is already linked to another group',
                )

    def create(
        self,
        name: str,
        description: str | None,
        idp_group: str | None,
    ) -> Group:
        name = name.strip()
        if not name:
            raise GroupError("name cannot be blank")
        idp_group = _normalize_idp_group(idp_group)
        self._check_unique(name, idp_group, None)
        group = Group(name=name, description=description, idp_group=idp_group)
        self.db.add(group)
        self.db.commit()
        self.db.refresh(group)
        return group

    def update(self, group: Group, changes: dict) -> Group:
        if group.is_builtin and ("name" in changes or "idp_group" in changes):
            raise GroupError(
                "The Everyone group cannot be renamed or linked to the IdP",
            )
        name = changes.get("name")
        if name is not None:
            name = name.strip()
            if not name:
                raise GroupError("name cannot be blank")
        idp_group = (
            _normalize_idp_group(changes["idp_group"])
            if "idp_group" in changes
            else None
        )
        self._check_unique(name, idp_group, group.id)
        if name is not None:
            group.name = name
        if "description" in changes:
            group.description = changes["description"]
        if "idp_group" in changes:
            if idp_group != group.idp_group:
                # Members mirrored from the old IdP group no longer belong here.
                self.db.query(GroupMember).filter(
                    GroupMember.group_id == group.id,
                    GroupMember.source == MembershipSource.IDP,
                ).delete(synchronize_session=False)
            group.idp_group = idp_group
        self.db.commit()
        self.db.refresh(group)
        return group

    def delete(self, group: Group) -> None:
        if group.is_builtin:
            raise GroupError("The Everyone group cannot be deleted")
        self.db.delete(group)
        self.db.commit()

    def add_manual_member(self, group: Group, email: str) -> GroupMember:
        if group.is_builtin:
            raise GroupError("Everyone already contains every user")
        user = self.db.query(User).filter(User.email == email.strip().lower()).first()
        if user is None:
            raise LookupError("No user with this email has signed in yet")
        existing = (
            self.db.query(GroupMember)
            .filter(
                GroupMember.group_id == group.id,
                GroupMember.user_id == user.id,
                GroupMember.source == MembershipSource.MANUAL,
            )
            .first()
        )
        if existing is not None:
            return existing
        member = GroupMember(
            group_id=group.id,
            user_id=user.id,
            source=MembershipSource.MANUAL,
        )
        self.db.add(member)
        self.db.commit()
        self.db.refresh(member)
        return member

    def remove_manual_member(self, group: Group, user_id: UUID) -> None:
        deleted = (
            self.db.query(GroupMember)
            .filter(
                GroupMember.group_id == group.id,
                GroupMember.user_id == user_id,
                GroupMember.source == MembershipSource.MANUAL,
            )
            .delete(synchronize_session=False)
        )
        if not deleted:
            raise LookupError("Not a manual member of this group")
        self.db.commit()

    def group_names_for(self, user_id: UUID) -> list[str]:
        ids = PermissionService(self.db).group_ids_for(user_id)
        if not ids:
            return []
        return sorted(
            name
            for (name,) in self.db.query(Group.name).filter(Group.id.in_(ids)).all()
        )

    def sync_idp_memberships(self, user: User, idp_groups: list[str] | None) -> None:
        """Make the user's IdP memberships match the claim exactly.

        None (claim missing) removes them all; unknown IdP groups are ignored.
        Manual memberships are left alone.
        """

        if idp_groups is None:
            logger.warning(
                "OIDC groups claim missing for user_id={}; IdP group memberships removed",
                user.id,
            )
            wanted_ids: set[UUID] = set()
        else:
            names = {
                name
                for name in (_normalize_idp_group(value) for value in idp_groups)
                if name
            }
            wanted_ids = (
                {
                    group_id
                    for (group_id,) in self.db.query(Group.id)
                    .filter(Group.idp_group.in_(names))
                    .all()
                }
                if names
                else set()
            )
        current = {
            member.group_id: member
            for member in self.db.query(GroupMember)
            .filter(
                GroupMember.user_id == user.id,
                GroupMember.source == MembershipSource.IDP,
            )
            .all()
        }
        for group_id, member in current.items():
            if group_id not in wanted_ids:
                self.db.delete(member)
        for group_id in wanted_ids - set(current):
            self.db.add(
                GroupMember(
                    group_id=group_id,
                    user_id=user.id,
                    source=MembershipSource.IDP,
                ),
            )
        self.db.commit()
