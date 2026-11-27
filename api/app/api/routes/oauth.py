"""The browser side of an MCP client's OAuth sign-in: what a waiting request
is, and the user's decision on it. Interactive login only, so a token can
never approve a sign-in that mints another token."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.api.routes.auth import check_token_grant
from app.core.auth import require_interactive_auth
from app.core.capabilities import Capability
from app.core.config import settings
from app.db.database import get_db
from app.models.schemas import (
    OAuthApproval,
    OAuthRedirect,
    OAuthRequestInfo,
)
from app.models.user import User
from app.services.oauth_service import OAuthRequestGone, OAuthService
from app.services.permission_service import require_capability

router = APIRouter()


def _require_oauth(response: Response) -> None:
    if not settings.oauth_active:
        raise HTTPException(status_code=404, detail="Not found")
    # The answers name a client and an address the browser is sent to; they
    # must never be cached.
    response.headers["Cache-Control"] = "no-store"


def _pending(service: OAuthService, request_id: UUID):
    try:
        return service.pending(request_id)
    except OAuthRequestGone as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/requests/{request_id}", response_model=OAuthRequestInfo)
async def get_sign_in_request(
    request_id: UUID,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_interactive_auth),
):
    """The client and redirect address of a sign-in that waits for a decision;
    404 once it was decided or expired."""

    _require_oauth(response)
    service = OAuthService(db)
    pending = _pending(service, request_id)
    effective = require_capability(request, db, current_user, Capability.MCP_CONNECT)
    requested = [
        scope
        for scope in pending.scopes or []
        if scope in Capability._value2member_map_
    ]
    return OAuthRequestInfo(
        id=pending.id,
        client_name=service.client_name(pending.client_id),
        redirect_uri=pending.redirect_uri,
        requested_capabilities=[
            name for name in requested if effective.anywhere(Capability(name))
        ],
        expires_at=pending.expires_at,
    )


@router.post("/requests/{request_id}/approve", response_model=OAuthRedirect)
async def approve_sign_in_request(
    request_id: UUID,
    data: OAuthApproval,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_interactive_auth),
):
    """Approve with the chosen capabilities (a subset of the caller's own) and,
    optionally, projects. redirect_to takes the browser back to the client with
    a single-use code."""

    _require_oauth(response)
    service = OAuthService(db)
    _pending(service, request_id)
    effective = require_capability(request, db, current_user, Capability.MCP_CONNECT)
    check_token_grant(db, current_user, effective, data.permissions, data.project_ids)
    if Capability.MCP_CONNECT.value not in data.permissions:
        raise HTTPException(
            status_code=422,
            detail="An MCP client needs the capability mcp.connect",
        )
    try:
        target = service.approve(
            request_id,
            current_user,
            data.permissions,
            data.project_ids,
        )
    except OAuthRequestGone as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return OAuthRedirect(redirect_to=target)


@router.post("/requests/{request_id}/deny", response_model=OAuthRedirect)
async def deny_sign_in_request(
    request_id: UUID,
    response: Response,
    db: Session = Depends(get_db),
    _user: User = Depends(require_interactive_auth),
):
    """Refuse; redirect_to takes the browser back with error=access_denied."""

    _require_oauth(response)
    try:
        target = OAuthService(db).deny(request_id)
    except OAuthRequestGone as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return OAuthRedirect(redirect_to=target)
