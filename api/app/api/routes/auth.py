from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from loguru import logger
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from authlib.integrations.base_client.errors import MismatchingStateError, OAuthError

from app.core.auth import get_current_user, require_oidc_mode, verify_access_token
from app.core.config import settings
from app.db.database import get_db
from app.models.schemas import AuthConfigResponse, UserResponse
from app.models.user import User
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

    return AuthConfigResponse(mode=settings.effective_auth_mode.value)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse.from_orm(current_user)


@router.post("/logout")
async def logout(request: Request, db: Session = Depends(get_db)):
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        SessionService(db).delete_session(session_id)

    response = JSONResponse({"message": "Logged out"})
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@router.get("/oidc/login")
async def oidc_login(request: Request):
    require_oidc_mode()
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

    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        max_age=settings.session_lifetime_hours * 3600,
    )
    return response
