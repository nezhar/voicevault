from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.timeutils import utcnow
from app.models.project import (
    AccessRequestStatus,
    Project,
    ProjectAccessRequest,
    ProjectMember,
    ProjectRole,
)
from app.models.user import User
from app.services.authz import get_membership


class AlreadyMemberError(Exception):
    """The requesting user already belongs to the project."""


class AccessRequestService:
    def __init__(self, db: Session):
        self.db = db

    def get_request(
        self,
        project_id: UUID,
        request_id: UUID,
    ) -> ProjectAccessRequest | None:
        return (
            self.db.query(ProjectAccessRequest)
            .filter(
                ProjectAccessRequest.id == request_id,
                ProjectAccessRequest.project_id == project_id,
            )
            .first()
        )

    def get_for_user(
        self,
        project_id: UUID,
        user_id: UUID,
    ) -> ProjectAccessRequest | None:
        return (
            self.db.query(ProjectAccessRequest)
            .filter(
                ProjectAccessRequest.project_id == project_id,
                ProjectAccessRequest.user_id == user_id,
            )
            .first()
        )

    def create_or_reopen(
        self,
        project: Project,
        user: User,
        message: str | None,
    ) -> ProjectAccessRequest:
        if get_membership(self.db, project.id, user.id) is not None:
            raise AlreadyMemberError("You are already a member of this project.")

        existing = self.get_for_user(project.id, user.id)
        if existing is not None:
            existing.status = AccessRequestStatus.PENDING
            existing.message = message
            existing.decided_by = None
            existing.decided_at = None
            self.db.commit()
            return existing

        request = ProjectAccessRequest(
            project_id=project.id,
            user_id=user.id,
            status=AccessRequestStatus.PENDING,
            message=message,
        )
        self.db.add(request)
        self.db.commit()
        return request

    def cancel(self, project_id: UUID, request_id: UUID, user: User) -> None:
        request = self.get_request(project_id, request_id)
        if request is None or request.user_id != user.id:
            raise LookupError("Access request not found.")
        if request.status != AccessRequestStatus.PENDING:
            raise ValueError("Only a pending request can be cancelled.")

        self.db.delete(request)
        self.db.commit()

    def list_for_project(
        self,
        project: Project,
        status: AccessRequestStatus | None = AccessRequestStatus.PENDING,
    ) -> list[ProjectAccessRequest]:
        query = self.db.query(ProjectAccessRequest).filter(
            ProjectAccessRequest.project_id == project.id,
        )
        if status is not None:
            query = query.filter(ProjectAccessRequest.status == status)
        return query.order_by(ProjectAccessRequest.created_at.desc()).all()

    def approve(
        self,
        project: Project,
        request_id: UUID,
        decider: User,
        role: ProjectRole = ProjectRole.VIEWER,
    ) -> ProjectAccessRequest:
        """Grant membership and settle the request in one transaction.

        Idempotent on purpose: two owners clicking Approve at the same moment
        should end with a settled request, not a 500.
        """

        request = self.get_request(project.id, request_id)
        if request is None:
            raise LookupError("Access request not found.")
        if request.status == AccessRequestStatus.APPROVED:
            return request

        if get_membership(self.db, project.id, request.user_id) is None:
            self.db.add(
                ProjectMember(
                    project_id=project.id,
                    user_id=request.user_id,
                    role=role,
                ),
            )

        request.status = AccessRequestStatus.APPROVED
        request.decided_by = decider.id
        request.decided_at = utcnow()
        self.db.commit()
        return request

    def deny(
        self,
        project: Project,
        request_id: UUID,
        decider: User,
    ) -> ProjectAccessRequest:
        request = self.get_request(project.id, request_id)
        if request is None:
            raise LookupError("Access request not found.")
        if request.status == AccessRequestStatus.DENIED:
            return request

        request.status = AccessRequestStatus.DENIED
        request.decided_by = decider.id
        request.decided_at = utcnow()
        self.db.commit()
        return request

    def pending_counts(self, project_ids: list[UUID]) -> dict[UUID, int]:
        """One grouped query for every project, so the sidebar badge costs
        nothing per project."""

        if not project_ids:
            return {}

        rows = (
            self.db.query(
                ProjectAccessRequest.project_id,
                func.count(ProjectAccessRequest.id),
            )
            .filter(
                ProjectAccessRequest.project_id.in_(project_ids),
                ProjectAccessRequest.status == AccessRequestStatus.PENDING,
            )
            .group_by(ProjectAccessRequest.project_id)
            .all()
        )
        return dict(rows)

    def preview(self, project_id: UUID, user: User) -> dict:
        """Minimal disclosure for a permalink: name, owners, and where the
        caller stands. Deliberately does not expose description or counts."""

        project = self.db.query(Project).filter(Project.id == project_id).first()
        if project is None:
            raise LookupError("Project not found.")

        owners = (
            self.db.query(ProjectMember)
            .filter(
                ProjectMember.project_id == project.id,
                ProjectMember.role == ProjectRole.OWNER,
            )
            .all()
        )
        membership = get_membership(self.db, project.id, user.id)
        return {
            "project": project,
            "owners": [member.user for member in owners],
            "role": membership.role if membership else None,
            "request": self.get_for_user(project.id, user.id),
        }
