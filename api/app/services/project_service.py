from uuid import UUID

from sqlalchemy.orm import Session

from app.models.entry import Entry
from app.models.project import Project, ProjectMember, ProjectRole
from app.models.user import User
from app.models.group import Group, ProjectGroupMember
from app.services.authz import get_membership, group_project_ids_select
from app.services.user_service import UserService


class LastOwnerError(Exception):
    """A project must always keep at least one owner."""


GROUP_ROLES = (ProjectRole.VIEWER, ProjectRole.EDITOR)


class ProjectService:
    def __init__(self, db: Session):
        self.db = db

    def create_project(
        self,
        name: str,
        description: str | None,
        creator: User,
    ) -> Project:
        project = Project(name=name, description=description, created_by=creator.id)
        self.db.add(project)
        self.db.flush()  # materialize project.id for the member row
        self.db.add(
            ProjectMember(
                project_id=project.id,
                user_id=creator.id,
                role=ProjectRole.OWNER,
            ),
        )
        self.db.commit()
        self.db.refresh(project)
        return project

    def get_project(self, project_id: UUID) -> Project | None:
        return self.db.query(Project).filter(Project.id == project_id).first()

    def list_for_user(self, user: User) -> list[dict]:
        """Projects the user reaches directly or through a group, with the
        effective (highest) role."""

        direct_ids = {
            row[0]
            for row in self.db.query(ProjectMember.project_id)
            .filter(ProjectMember.user_id == user.id)
            .all()
        }
        group_ids = {
            row[0] for row in self.db.execute(group_project_ids_select(user.id)).all()
        }
        results = []
        for project_id in direct_ids | group_ids:
            membership = get_membership(self.db, project_id, user.id)
            project = self.get_project(project_id)
            if not project or membership is None:
                continue
            member_count = (
                self.db.query(ProjectMember)
                .filter(ProjectMember.project_id == project.id)
                .count()
            )
            entry_count = (
                self.db.query(Entry).filter(Entry.project_id == project.id).count()
            )
            results.append(
                {
                    "project": project,
                    "role": membership.role,
                    "member_count": member_count,
                    "entry_count": entry_count,
                },
            )
        results.sort(key=lambda item: item["project"].name.lower())
        return results

    def update_project(
        self,
        project: Project,
        name: str | None,
        description: str | None,
    ) -> Project:
        if name is not None:
            project.name = name
        if description is not None:
            project.description = description
        self.db.commit()
        self.db.refresh(project)
        return project

    def delete_project(self, project: Project) -> None:
        # Detach entries explicitly instead of relying on ON DELETE SET NULL:
        # databases upgraded via ensure_entry_schema (or created by a worker's
        # create_all) have entries.project_id without the FK constraint.
        self.db.query(Entry).filter(Entry.project_id == project.id).update(
            {Entry.project_id: None},
            synchronize_session=False,
        )
        self.db.delete(project)
        self.db.commit()

    def _get_member(self, project: Project, user_id: UUID) -> ProjectMember | None:
        return (
            self.db.query(ProjectMember)
            .filter(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == user_id,
            )
            .first()
        )

    def _other_owner_count(self, project: Project, user_id: UUID) -> int:
        return (
            self.db.query(ProjectMember)
            .filter(
                ProjectMember.project_id == project.id,
                ProjectMember.role == ProjectRole.OWNER,
                ProjectMember.user_id != user_id,
            )
            .count()
        )

    def add_member(
        self,
        project: Project,
        email: str,
        role: ProjectRole,
    ) -> ProjectMember:
        user = UserService(self.db).get_by_email(email)
        if not user:
            raise LookupError(
                "No user with this email. The user must log in once first.",
            )
        if self._get_member(project, user.id):
            raise ValueError("User is already a member of this project.")

        member = ProjectMember(project_id=project.id, user_id=user.id, role=role)
        self.db.add(member)
        self.db.commit()
        return member

    def update_member_role(
        self,
        project: Project,
        user_id: UUID,
        role: ProjectRole,
    ) -> ProjectMember:
        member = self._get_member(project, user_id)
        if not member:
            raise LookupError("Member not found.")
        if (
            member.role == ProjectRole.OWNER
            and role != ProjectRole.OWNER
            and self._other_owner_count(project, user_id) == 0
        ):
            raise LastOwnerError("A project needs at least one owner.")

        member.role = role
        self.db.commit()
        return member

    def remove_member(self, project: Project, user_id: UUID) -> None:
        member = self._get_member(project, user_id)
        if not member:
            raise LookupError("Member not found.")
        if (
            member.role == ProjectRole.OWNER
            and self._other_owner_count(project, user_id) == 0
        ):
            raise LastOwnerError("A project needs at least one owner.")

        self.db.delete(member)
        self.db.commit()

    # -- sharing with groups ------------------------------------------------

    def list_groups(self, project: Project) -> list[ProjectGroupMember]:
        return (
            self.db.query(ProjectGroupMember)
            .filter(ProjectGroupMember.project_id == project.id)
            .all()
        )

    def _get_group_share(
        self,
        project: Project,
        group_id: UUID,
    ) -> ProjectGroupMember | None:
        return (
            self.db.query(ProjectGroupMember)
            .filter(
                ProjectGroupMember.project_id == project.id,
                ProjectGroupMember.group_id == group_id,
            )
            .first()
        )

    @staticmethod
    def _check_group_role(role: ProjectRole) -> None:
        if role not in GROUP_ROLES:
            raise ValueError(
                "Groups can be viewers or editors; owners are added directly.",
            )

    def add_group(
        self,
        project: Project,
        group_id: UUID,
        role: ProjectRole,
        actor: User,
    ) -> ProjectGroupMember:
        self._check_group_role(role)
        if self.db.get(Group, group_id) is None:
            raise LookupError("Group not found.")
        if self._get_group_share(project, group_id) is not None:
            raise FileExistsError("The project is already shared with this group.")
        share = ProjectGroupMember(
            project_id=project.id,
            group_id=group_id,
            role=role,
            added_by=actor.id,
        )
        self.db.add(share)
        self.db.commit()
        self.db.refresh(share)
        return share

    def update_group(
        self,
        project: Project,
        group_id: UUID,
        role: ProjectRole,
    ) -> ProjectGroupMember:
        self._check_group_role(role)
        share = self._get_group_share(project, group_id)
        if share is None:
            raise LookupError("The project is not shared with this group.")
        share.role = role
        self.db.commit()
        return share

    def remove_group(self, project: Project, group_id: UUID) -> None:
        share = self._get_group_share(project, group_id)
        if share is None:
            raise LookupError("The project is not shared with this group.")
        self.db.delete(share)
        self.db.commit()
