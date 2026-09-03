from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import require_admin
from app.db.database import get_db
from app.models.schemas import AdminSystemStatsResponse, AdminUserListResponse
from app.models.user import User
from app.services.admin_stats_service import DEFAULT_SORT, AdminStatsService

router = APIRouter()


@router.get("/stats", response_model=AdminSystemStatsResponse)
async def get_system_stats(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
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
    _admin: User = Depends(require_admin),
):
    """Per-user consumption. Read-only."""

    return AdminStatsService(db).user_stats(
        skip=skip,
        limit=limit,
        sort=sort,
        order=order,
    )
