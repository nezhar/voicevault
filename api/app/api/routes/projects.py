from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_oidc_mode
from app.core.config import AuthMode, settings
from app.db.database import get_db
from app.models.entry import Entry
from app.models.project import AccessRequestStatus, ProjectMember, ProjectRole
from app.models.schemas import (
    AccessRequestCreate,
    AccessRequestDecision,
    AccessRequestResponse,
    ProjectCreate,
    ProjectDetailResponse,
    ProjectMemberAdd,
    ProjectMemberResponse,
    ProjectMemberUpdate,
    ProjectOwnerResponse,
    ProjectPreviewResponse,
    ProjectResponse,
    ProjectUpdate,
)
from app.models.user import User
from app.services.access_request_service import (
    AccessRequestService,
    AlreadyMemberError,
)
from app.services.authz import get_membership, require_project_role
from app.services.project_service import LastOwnerError, ProjectService

router = APIRouter()


def _project_response(item: dict, pending_request_count: int = 0) -> ProjectResponse:
    project = item["project"]
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        created_by=project.created_by,
        created_at=project.created_at,
        updated_at=project.updated_at,
        my_role=item["role"],
        member_count=item["member_count"],
        entry_count=item["entry_count"],
        pending_request_count=pending_request_count,
    )


def _load_project_and_membership(
    db: Session,
    project_id: UUID,
    user: User,
    min_role: ProjectRole,
):
    service = ProjectService(db)
    project = service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    membership = require_project_role(db, project, user, min_role)
    return service, project, membership


@router.post("/", response_model=ProjectResponse)
async def create_project(
    data: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = ProjectService(db)
    project = service.create_project(data.name, data.description, current_user)
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        created_by=project.created_by,
        created_at=project.created_at,
        updated_at=project.updated_at,
        my_role=ProjectRole.OWNER,
        member_count=1,
        entry_count=0,
    )


@router.get("/", response_model=list[ProjectResponse])
async def list_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = ProjectService(db).list_for_user(current_user)
    owned_ids = [
        item["project"].id for item in items if item["role"] == ProjectRole.OWNER
    ]
    counts = AccessRequestService(db).pending_counts(owned_ids)
    return [
        _project_response(item, counts.get(item["project"].id, 0)) for item in items
    ]


@router.get("/{project_id}", response_model=ProjectDetailResponse)
async def get_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service, project, membership = _load_project_and_membership(
        db,
        project_id,
        current_user,
        ProjectRole.VIEWER,
    )
    members = (
        db.query(ProjectMember).filter(ProjectMember.project_id == project.id).all()
    )
    entry_count = db.query(Entry).filter(Entry.project_id == project.id).count()
    pending_count = (
        AccessRequestService(db).pending_counts([project.id]).get(project.id, 0)
        if membership.role == ProjectRole.OWNER
        else 0
    )
    return ProjectDetailResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        created_by=project.created_by,
        created_at=project.created_at,
        updated_at=project.updated_at,
        my_role=membership.role,
        member_count=len(members),
        entry_count=entry_count,
        pending_request_count=pending_count,
        members=[
            ProjectMemberResponse(
                user_id=member.user_id,
                email=member.user.email,
                display_name=member.user.display_name,
                role=member.role,
            )
            for member in members
        ],
    )


@router.get("/{project_id}/preview", response_model=ProjectPreviewResponse)
async def preview_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Permalink landing data. Unlike GET /{id}, this does not 404 for
    non-members — revealing name and owners to whoever holds the UUID is the
    whole point of a shareable link."""

    try:
        preview = AccessRequestService(db).preview(project_id, current_user)
    except LookupError:
        raise HTTPException(status_code=404, detail="Project not found")

    request = preview["request"]
    return ProjectPreviewResponse(
        id=preview["project"].id,
        name=preview["project"].name,
        owners=[
            ProjectOwnerResponse(
                display_name=owner.display_name,
                email=owner.email,
            )
            for owner in preview["owners"]
        ],
        my_role=preview["role"],
        request_status=request.status if request else None,
        request_id=request.id if request else None,
        can_request=(
            settings.effective_auth_mode == AuthMode.OIDC and preview["role"] is None
        ),
    )


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    data: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service, project, membership = _load_project_and_membership(
        db,
        project_id,
        current_user,
        ProjectRole.OWNER,
    )
    project = service.update_project(project, data.name, data.description)
    member_count = (
        db.query(ProjectMember).filter(ProjectMember.project_id == project.id).count()
    )
    entry_count = db.query(Entry).filter(Entry.project_id == project.id).count()
    return _project_response(
        {
            "project": project,
            "role": membership.role,
            "member_count": member_count,
            "entry_count": entry_count,
        },
    )


@router.delete("/{project_id}")
async def delete_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service, project, _ = _load_project_and_membership(
        db,
        project_id,
        current_user,
        ProjectRole.OWNER,
    )
    service.delete_project(project)
    return {"message": "Project deleted; entries reverted to private"}


@router.post("/{project_id}/members", response_model=ProjectMemberResponse)
async def add_member(
    project_id: UUID,
    data: ProjectMemberAdd,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service, project, _ = _load_project_and_membership(
        db,
        project_id,
        current_user,
        ProjectRole.OWNER,
    )
    try:
        member = service.add_member(project, data.email, data.role)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return ProjectMemberResponse(
        user_id=member.user_id,
        email=member.user.email,
        display_name=member.user.display_name,
        role=member.role,
    )


@router.put("/{project_id}/members/{user_id}", response_model=ProjectMemberResponse)
async def update_member(
    project_id: UUID,
    user_id: UUID,
    data: ProjectMemberUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service, project, _ = _load_project_and_membership(
        db,
        project_id,
        current_user,
        ProjectRole.OWNER,
    )
    try:
        member = service.update_member_role(project, user_id, data.role)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except LastOwnerError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return ProjectMemberResponse(
        user_id=member.user_id,
        email=member.user.email,
        display_name=member.user.display_name,
        role=member.role,
    )


@router.delete("/{project_id}/members/{user_id}")
async def remove_member(
    project_id: UUID,
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = ProjectService(db)
    project = service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Members may remove themselves (leave); everything else is owner-only
    if user_id == current_user.id:
        if not get_membership(db, project.id, current_user.id):
            raise HTTPException(status_code=404, detail="Project not found")
    else:
        require_project_role(db, project, current_user, ProjectRole.OWNER)

    try:
        service.remove_member(project, user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except LastOwnerError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"message": "Member removed"}


def _access_request_response(request) -> AccessRequestResponse:
    return AccessRequestResponse(
        id=request.id,
        project_id=request.project_id,
        user_id=request.user_id,
        email=request.user.email,
        display_name=request.user.display_name,
        status=request.status,
        message=request.message,
        created_at=request.created_at,
        decided_at=request.decided_at,
        decided_by_name=request.decider.display_name if request.decider else None,
    )


@router.post("/{project_id}/access-requests", response_model=AccessRequestResponse)
async def request_access(
    project_id: UUID,
    data: AccessRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_oidc_mode()
    project = ProjectService(db).get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        request = AccessRequestService(db).create_or_reopen(
            project,
            current_user,
            data.message,
        )
    except AlreadyMemberError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _access_request_response(request)


@router.delete("/{project_id}/access-requests/{request_id}")
async def cancel_access_request(
    project_id: UUID,
    request_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # cancel() checks that the request belongs to the caller, so a stranger
    # passing someone else's id gets the same 404 as an unknown one.
    require_oidc_mode()
    try:
        AccessRequestService(db).cancel(project_id, request_id, current_user)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"message": "Access request cancelled"}


def _parse_status_filter(status: str) -> AccessRequestStatus | None:
    if status == "all":
        return None
    try:
        return AccessRequestStatus(status)
    except ValueError:
        raise HTTPException(status_code=422, detail="Unknown status filter")


@router.get(
    "/{project_id}/access-requests",
    response_model=list[AccessRequestResponse],
)
async def list_access_requests(
    project_id: UUID,
    status: str = Query("pending"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_oidc_mode()
    _, project, _ = _load_project_and_membership(
        db,
        project_id,
        current_user,
        ProjectRole.OWNER,
    )
    requests = AccessRequestService(db).list_for_project(
        project,
        _parse_status_filter(status),
    )
    return [_access_request_response(request) for request in requests]


@router.post(
    "/{project_id}/access-requests/{request_id}/approve",
    response_model=AccessRequestResponse,
)
async def approve_access_request(
    project_id: UUID,
    request_id: UUID,
    data: AccessRequestDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_oidc_mode()
    _, project, _ = _load_project_and_membership(
        db,
        project_id,
        current_user,
        ProjectRole.OWNER,
    )
    try:
        request = AccessRequestService(db).approve(
            project,
            request_id,
            current_user,
            data.role,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _access_request_response(request)


@router.post(
    "/{project_id}/access-requests/{request_id}/deny",
    response_model=AccessRequestResponse,
)
async def deny_access_request(
    project_id: UUID,
    request_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_oidc_mode()
    _, project, _ = _load_project_and_membership(
        db,
        project_id,
        current_user,
        ProjectRole.OWNER,
    )
    try:
        request = AccessRequestService(db).deny(project, request_id, current_user)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _access_request_response(request)
