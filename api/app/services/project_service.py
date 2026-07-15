from uuid import UUID

from sqlalchemy.orm import Session

from app.models.entry import Entry
from app.models.project import Project, ProjectMember, ProjectRole
from app.models.user import User
from app.services.user_service import UserService


class LastOwnerError(Exception):
    """A project must always keep at least one owner."""


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
        memberships = (
            self.db.query(ProjectMember).filter(ProjectMember.user_id == user.id).all()
        )
        results = []
        for membership in memberships:
            project = self.get_project(membership.project_id)
            if not project:
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
