"""Groups, capability grants and the capability catalog.

admin_router (/api/admin): manage groups, members and grants; interactive
login only, admins (or holders of admin.view / admin.manage) only, 404 for
everyone else like the rest of the admin area.
router (/api/groups): the group picker for project owners.
catalog_router (/api/capabilities): the catalog, open to every signed-in user.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import (
    get_current_user,
    is_admin_user,
    require_admin_manage,
    require_admin_view,
    require_interactive_auth,
)
from app.core.capabilities import (
    CATALOG,
    ROUTE_POLICY,
    TOOL_POLICY,
    Capability,
)
from app.db.database import get_db
from app.models.project import Project
from app.models.schemas import (
    CapabilityInfoResponse,
    EffectiveGrantResponse,
    GrantItem,
    GrantSet,
    GroupCreate,
    GroupDetailResponse,
    GroupMemberAdd,
    GroupMemberResponse,
    GroupResponse,
    GroupUpdate,
    ProjectRef,
    UserPermissionsResponse,
)
from app.models.user import User
from app.services.group_service import GroupError, GroupService
from app.services.pat_service import LIKE_ESCAPE, escape_like
from app.services.permission_service import (
    GrantError,
    GrantSpec,
    PermissionService,
    capability_snapshot,
    current_effective,
)

admin_router = APIRouter()
router = APIRouter()
catalog_router = APIRouter()


# -- catalog ----------------------------------------------------------------


@catalog_router.get("", response_model=list[CapabilityInfoResponse])
async def list_capabilities(_user: User = Depends(get_current_user)):
    """Every capability with what it unlocks; drives the permission editors."""

    result = []
    for cap, info in CATALOG.items():
        result.append(
            CapabilityInfoResponse(
                name=cap.value,
                label=info.label,
                area=info.area,
                description=info.description,
                project_scoped=info.project_scoped,
                routes=sorted(
                    f"{method} {path}"
                    for (method, path), rule in ROUTE_POLICY.items()
                    if rule == cap
                ),
                tools=sorted(name for name, rule in TOOL_POLICY.items() if rule == cap),
            ),
        )
    return result


# -- group picker for project owners ----------------------------------------


@router.get("/", response_model=list[GroupResponse])
async def search_groups(
    request: Request,
    search: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Groups a project owner can share a project with."""

    effective = current_effective(request, db, current_user)
    if not effective.anywhere(Capability.PROJECTS_MANAGE):
        raise HTTPException(
            status_code=403,
            detail="Missing capability projects.manage (Manage projects)",
        )
    service = GroupService(db)
    return [
        GroupResponse(
            id=group.id,
            name=group.name,
            description=group.description,
            is_builtin=group.is_builtin,
            member_count=service.member_count(group),
        )
        for group in service.list_groups(search, limit)
    ]


# -- admin: groups ----------------------------------------------------------


def _group_response(service: GroupService, group) -> GroupResponse:
    return GroupResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        idp_group=group.idp_group,
        is_builtin=group.is_builtin,
        member_count=service.member_count(group),
    )


def _group_detail(service: GroupService, group) -> GroupDetailResponse:
    return GroupDetailResponse(
        **_group_response(service, group).model_dump(),
        members=[
            GroupMemberResponse(
                user_id=member.user_id,
                email=member.user.email,
                display_name=member.user.display_name,
                source=member.source.value,
            )
            for member in service.members(group)
        ],
    )


def _load_group(service: GroupService, group_id: UUID):
    group = service.get(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


@admin_router.get("/groups", response_model=list[GroupResponse])
async def admin_list_groups(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin_view),
    _interactive: User = Depends(require_interactive_auth),
):
    service = GroupService(db)
    PermissionService(db).everyone()  # make sure the baseline is listed
    db.commit()
    return [_group_response(service, group) for group in service.list_groups()]


@admin_router.post("/groups", response_model=GroupDetailResponse, status_code=201)
async def admin_create_group(
    data: GroupCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin_manage),
    _interactive: User = Depends(require_interactive_auth),
):
    service = GroupService(db)
    try:
        group = service.create(data.name, data.description, data.idp_group)
    except GroupError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _group_detail(service, group)


@admin_router.get("/groups/{group_id}", response_model=GroupDetailResponse)
async def admin_get_group(
    group_id: UUID,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin_view),
    _interactive: User = Depends(require_interactive_auth),
):
    service = GroupService(db)
    return _group_detail(service, _load_group(service, group_id))


@admin_router.put("/groups/{group_id}", response_model=GroupDetailResponse)
async def admin_update_group(
    group_id: UUID,
    data: GroupUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin_manage),
    _interactive: User = Depends(require_interactive_auth),
):
    service = GroupService(db)
    group = _load_group(service, group_id)
    try:
        group = service.update(group, data.changes())
    except GroupError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _group_detail(service, group)


@admin_router.delete("/groups/{group_id}", status_code=204)
async def admin_delete_group(
    group_id: UUID,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin_manage),
    _interactive: User = Depends(require_interactive_auth),
):
    service = GroupService(db)
    group = _load_group(service, group_id)
    try:
        service.delete(group)
    except GroupError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@admin_router.post(
    "/groups/{group_id}/members",
    response_model=GroupDetailResponse,
    status_code=201,
)
async def admin_add_group_member(
    group_id: UUID,
    data: GroupMemberAdd,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin_manage),
    _interactive: User = Depends(require_interactive_auth),
):
    service = GroupService(db)
    group = _load_group(service, group_id)
    try:
        service.add_manual_member(group, data.email)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except GroupError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _group_detail(service, group)


@admin_router.delete("/groups/{group_id}/members/{user_id}", status_code=204)
async def admin_remove_group_member(
    group_id: UUID,
    user_id: UUID,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin_manage),
    _interactive: User = Depends(require_interactive_auth),
):
    service = GroupService(db)
    group = _load_group(service, group_id)
    try:
        service.remove_manual_member(group, user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# -- admin: projects for the grant editor ----------------------------------


@admin_router.get("/projects", response_model=list[ProjectRef])
async def admin_search_projects(
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin_view),
    _interactive: User = Depends(require_interactive_auth),
):
    """Project names for per-project grants; no content, no members."""

    query = db.query(Project)
    if search and search.strip():
        pattern = f"%{escape_like(search.strip())}%"
        query = query.filter(Project.name.ilike(pattern, escape=LIKE_ESCAPE))
    projects = query.order_by(func.lower(Project.name)).limit(limit).all()
    return [ProjectRef(id=project.id, name=project.name) for project in projects]


# -- admin: grants ----------------------------------------------------------


def _subject(db: Session, user_id: UUID | None, group_id: UUID | None):
    if (user_id is None) == (group_id is None):
        raise HTTPException(
            status_code=400,
            detail="Pass exactly one of user_id or group_id",
        )
    if user_id is not None and db.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    if group_id is not None and GroupService(db).get(group_id) is None:
        raise HTTPException(status_code=404, detail="Group not found")


def _project_names(db: Session, ids) -> dict:
    ids = {pid for pid in ids if pid is not None}
    if not ids:
        return {}
    return {
        project.id: project.name
        for project in db.query(Project).filter(Project.id.in_(ids)).all()
    }


def _grant_items(db: Session, grants) -> list[GrantItem]:
    names = _project_names(db, [grant.project_id for grant in grants])
    return [
        GrantItem(
            capability=grant.capability,
            project_id=grant.project_id,
            project_name=names.get(grant.project_id),
        )
        for grant in grants
    ]


@admin_router.get("/grants", response_model=list[GrantItem])
async def admin_get_grants(
    user_id: UUID | None = None,
    group_id: UUID | None = None,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin_view),
    _interactive: User = Depends(require_interactive_auth),
):
    """The grants given directly to one user or group."""

    _subject(db, user_id, group_id)
    grants = PermissionService(db).grants_for(user_id=user_id, group_id=group_id)
    return _grant_items(db, grants)


@admin_router.put("/grants", response_model=list[GrantItem])
async def admin_replace_grants(
    data: GrantSet,
    user_id: UUID | None = None,
    group_id: UUID | None = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin_manage),
    _interactive: User = Depends(require_interactive_auth),
):
    """Replace every grant of one user or group in one transaction."""

    _subject(db, user_id, group_id)
    try:
        specs = [
            GrantSpec(Capability(item.capability), item.project_id)
            for item in data.grants
        ]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    try:
        grants = PermissionService(db).replace_grants(
            user_id=user_id,
            group_id=group_id,
            grants=specs,
            actor=admin,
        )
    except GrantError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _grant_items(db, grants)


@admin_router.get("/users/{user_id}/effective", response_model=UserPermissionsResponse)
async def admin_user_permissions(
    user_id: UUID,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin_view),
    _interactive: User = Depends(require_interactive_auth),
):
    """What a user may do, and where each capability comes from."""

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    service = PermissionService(db)
    capabilities, project_capabilities = capability_snapshot(service.effective(user))
    rows = service.explain(user)
    names = _project_names(db, [row["project_id"] for row in rows])
    return UserPermissionsResponse(
        user_id=user.id,
        is_admin=is_admin_user(user),
        capabilities=capabilities,
        project_capabilities=project_capabilities,
        grants=[
            EffectiveGrantResponse(
                capability=row["capability"],
                project_id=row["project_id"],
                project_name=names.get(row["project_id"]),
                source=row["source"] or "unknown",
            )
            for row in rows
        ],
        groups=GroupService(db).group_names_for(user.id),
    )
