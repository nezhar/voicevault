from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.routes.auth import build_user_response
from app.core.auth import (
    require_admin_manage,
    require_admin_view,
    require_interactive_auth,
)
from app.db.database import get_db
from app.models.schemas import (
    AdminPersonalAccessTokenListResponse,
    AdminPersonalAccessTokenResponse,
    AdminSystemStatsResponse,
    AdminUserListResponse,
    PATUserResponse,
    UserActivationUpdate,
    UserResponse,
)
from app.models.user import User
from app.services.admin_stats_service import DEFAULT_SORT, AdminStatsService
from app.services.pat_service import LIKE_ESCAPE, PATService, escape_like
from app.services.session_service import SessionService

router = APIRouter()


@router.get("/stats", response_model=AdminSystemStatsResponse)
async def get_system_stats(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin_view),
):
    """Platform-wide totals. Read-only."""

    return AdminStatsService(db).system_stats()


@router.get("/users", response_model=AdminUserListResponse)
async def get_user_stats(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    sort: str = Query(DEFAULT_SORT),
    order: str = Query("desc"),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin_view),
):
    """Per-user consumption. Read-only."""

    return AdminStatsService(db).user_stats(
        skip=skip,
        limit=limit,
        sort=sort,
        order=order,
    )


@router.patch("/users/{user_id}/active", response_model=UserResponse)
async def set_user_active(
    user_id: UUID,
    data: UserActivationUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin_manage),
    _interactive: User = Depends(require_interactive_auth),
):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.is_system:
        raise HTTPException(
            status_code=400,
            detail="The system user cannot be deactivated",
        )
    if user.id == admin.id and not data.is_active:
        raise HTTPException(
            status_code=400,
            detail="You cannot deactivate your own account",
        )

    user.is_active = data.is_active
    if not data.is_active:
        # One transaction: the account flips together with its credentials.
        PATService(db).revoke_all_for_user(user.id, commit=False)
        SessionService(db).delete_all_for_user(user.id, commit=False)
    db.commit()
    return build_user_response(user)


@router.get("/pat-users", response_model=list[PATUserResponse])
async def list_pat_users(
    search: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin_view),
    _interactive: User = Depends(require_interactive_auth),
):
    normalized_search = search.strip()
    if len(normalized_search) < 2:
        return []
    pattern = f"%{escape_like(normalized_search)}%"
    query = db.query(User).filter(
        or_(
            User.email.ilike(pattern, escape=LIKE_ESCAPE),
            User.display_name.ilike(pattern, escape=LIKE_ESCAPE),
        ),
    )
    return query.order_by(User.email).limit(limit).all()


@router.get("/pats", response_model=AdminPersonalAccessTokenListResponse)
async def list_all_pats(
    user_id: UUID | None = None,
    name: str | None = Query(default=None, max_length=100),
    status: str | None = Query(default=None, pattern="^(active|expired|revoked)$"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin_view),
    _interactive: User = Depends(require_interactive_auth),
):
    rows, total = PATService(db).list_all(
        user_id=user_id,
        name=name,
        status=status,
        skip=(page - 1) * per_page,
        limit=per_page,
    )
    tokens = [
        AdminPersonalAccessTokenResponse.from_row(pat, user) for pat, user in rows
    ]
    return AdminPersonalAccessTokenListResponse(
        tokens=tokens,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page,
    )


@router.delete("/pats/{token_id}", status_code=204)
async def revoke_any_pat(
    token_id: UUID,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin_manage),
    _interactive: User = Depends(require_interactive_auth),
):
    if not PATService(db).revoke(token_id):
        raise HTTPException(status_code=404, detail="Personal access token not found")
