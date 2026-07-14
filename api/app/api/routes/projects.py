from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.database import get_db
from app.models.entry import Entry
from app.models.project import ProjectMember, ProjectRole
from app.models.schemas import (
    ProjectCreate,
    ProjectDetailResponse,
    ProjectMemberAdd,
    ProjectMemberResponse,
    ProjectMemberUpdate,
    ProjectResponse,
    ProjectUpdate,
)
from app.models.user import User
from app.services.authz import get_membership, require_project_role
from app.services.project_service import LastOwnerError, ProjectService

router = APIRouter()


def _project_response(item: dict) -> ProjectResponse:
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
    return [
        _project_response(item)
        for item in ProjectService(db).list_for_user(current_user)
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
