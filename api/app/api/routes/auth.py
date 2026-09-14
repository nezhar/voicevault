from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from loguru import logger
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from authlib.integrations.base_client.errors import MismatchingStateError, OAuthError

from app.core.auth import (
    get_current_user,
    is_admin_user,
    require_oidc_mode,
    verify_access_token,
)
from app.core.config import settings
from app.db.database import get_db
from app.models.schemas import AuthConfigResponse, UserResponse
from app.models.user import User
from app.core.auth import require_interactive_auth
from app.models.schemas import (
    PersonalAccessTokenCreate,
    PersonalAccessTokenCreated,
    PersonalAccessTokenResponse,
    PersonalAccessTokenUpdate,
)
from app.services.pat_service import PATNotEditable, PATService
from app.services.oidc_service import OIDCError, extract_claims, get_oauth, redirect_uri
from app.services.session_service import SESSION_COOKIE_NAME, SessionService
from app.services.user_service import UserService

router = APIRouter()


class LoginRequest(BaseModel):
    token: str


class LoginResponse(BaseModel):
    message: str
    token: str


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    Simple token-based login for PoC

    In production: Replace with proper JWT authentication
    """

    # If no access token is configured, accept any token (development mode)
    if not settings.access_token:
        return LoginResponse(
            message="Authentication disabled (development mode)",
            token=request.token,
        )

    # Verify the token
    if not verify_access_token(request.token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
        )

    return LoginResponse(
        message="Login successful",
        token=request.token,
    )


@router.post("/verify")
async def verify_token(request: LoginRequest):
    """Verify if a token is valid"""

    # If no access token is configured, accept any token
    if not settings.access_token:
        return {"valid": True, "message": "Authentication disabled"}

    # Verify the token
    if not verify_access_token(request.token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
        )

    return {"valid": True, "message": "Token is valid"}


@router.get("/config", response_model=AuthConfigResponse)
async def get_auth_config():
    """Public: which login the UI should render."""

    return AuthConfigResponse(
        mode=settings.effective_auth_mode.value,
        mcp_enabled=settings.mcp_enabled,
    )


def build_user_response(user: User) -> UserResponse:
    """is_admin is derived from config on every request, never persisted."""

    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_admin=is_admin_user(user),
        is_active=user.is_active,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return build_user_response(current_user)


@router.post("/pats", response_model=PersonalAccessTokenCreated, status_code=201)
async def create_pat(
    data: PersonalAccessTokenCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_interactive_auth),
):
    pat, raw_token = PATService(db).create(
        user_id=current_user.id,
        name=data.name,
        permissions=[permission.value for permission in data.permissions],
        expires_at=data.expires_at,
    )
    return PersonalAccessTokenCreated.from_pat(pat, raw_token)


@router.get("/pats", response_model=list[PersonalAccessTokenResponse])
async def list_pats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_interactive_auth),
):
    return PATService(db).list_for_user(current_user.id)


@router.patch("/pats/{token_id}", response_model=PersonalAccessTokenResponse)
async def update_pat(
    token_id: UUID,
    data: PersonalAccessTokenUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_interactive_auth),
):
    """Rename or change the expiry of an own, active token."""

    try:
        pat = PATService(db).update(token_id, current_user.id, data.changes())
    except PATNotEditable:
        raise HTTPException(status_code=409, detail="Only active tokens can be edited")
    if pat is None:
        raise HTTPException(status_code=404, detail="Personal access token not found")
    return pat


@router.delete("/pats/{token_id}", status_code=204)
async def revoke_pat(
    token_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_interactive_auth),
):
    if not PATService(db).revoke(token_id, current_user.id):
        raise HTTPException(status_code=404, detail="Personal access token not found")


@router.post("/logout")
async def logout(request: Request, db: Session = Depends(get_db)):
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        SessionService(db).delete_session(session_id)

    response = JSONResponse({"message": "Logged out"})
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


_REDIRECT_SESSION_KEY = "post_login_redirect"
_MAX_NEXT_LENGTH = 512


def safe_next_path(value: str | None) -> str:
    """Only same-origin absolute paths survive.

    Everything else — scheme-relative //host, absolute URLs, javascript:,
    backslash variants — collapses to "/" so this cannot become an open
    redirect off the back of the login flow.
    """

    if not value or len(value) > _MAX_NEXT_LENGTH:
        return "/"
    if not value.startswith("/") or value.startswith("//"):
        return "/"
    if "\\" in value:
        return "/"
    return value


@router.get("/oidc/login")
async def oidc_login(request: Request, next: str | None = None):
    require_oidc_mode()
    # Stored server-side rather than round-tripped through the IdP, so the
    # target cannot be tampered with between the two requests.
    request.session[_REDIRECT_SESSION_KEY] = safe_next_path(next)
    oauth = get_oauth()
    return await oauth.oidc.authorize_redirect(request, redirect_uri())


def _error_redirect(code: str) -> RedirectResponse:
    return RedirectResponse(url=f"/?auth_error={code}", status_code=302)


@router.get("/oidc/callback")
async def oidc_callback(request: Request, db: Session = Depends(get_db)):
    require_oidc_mode()
    oauth = get_oauth()

    try:
        token = await oauth.oidc.authorize_access_token(request)
    except MismatchingStateError:
        logger.error("OIDC callback with mismatching/expired state")
        return _error_redirect("invalid_state")
    except OAuthError as exc:  # IdP returned an error response (e.g. access_denied)
        logger.error(f"OIDC IdP error: {exc}")
        return _error_redirect("idp_error")
    except Exception as exc:  # network failure, token endpoint unreachable, ...
        logger.error(f"OIDC token exchange failed: {exc}")
        return _error_redirect("token_exchange_failed")

    try:
        raw_claims = token.get("userinfo") or {}
        identity = extract_claims(raw_claims)
    except OIDCError as exc:
        logger.error(f"OIDC claim extraction failed: {exc}")
        return _error_redirect(exc.code)

    user_service = UserService(db)
    # Refuse before provisioning: provisioning records a successful login
    # (last_login_at), which a deactivated account must not accumulate.
    existing = user_service.find_oidc_user(identity["issuer"], identity["subject"])
    if existing is not None and not existing.is_active:
        logger.warning(
            "authentication_failed reason=inactive_user user_id={}",
            existing.id,
        )
        return _error_redirect("account_inactive")
    try:
        user = user_service.provision_oidc_user(
            issuer=identity["issuer"],
            subject=identity["subject"],
            email=identity["email"],
            display_name=identity["display_name"],
        )
    except IntegrityError:
        # e.g. the IdP account was re-created (new subject, same email) and now
        # collides with the unique email of the old user row
        db.rollback()
        logger.error(
            "OIDC user provisioning conflict for subject "
            f"{identity['subject']} — a user with this email already exists",
        )
        return _error_redirect("provisioning_failed")

    if (
        settings.initial_owner_email
        and user.email == settings.initial_owner_email.strip().lower()
    ):
        user_service.claim_legacy_entries(user)

    _, session_token = SessionService(db).create_session(user.id)

    target = safe_next_path(request.session.pop(_REDIRECT_SESSION_KEY, None))
    response = RedirectResponse(url=target, status_code=302)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        max_age=settings.session_lifetime_hours * 3600,
    )
    return response
