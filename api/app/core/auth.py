import secrets

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import AuthMode, settings
from app.db.database import get_db
from app.models.user import User
from app.services.session_service import SESSION_COOKIE_NAME, SessionService
from app.services.user_service import UserService

security = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Authentication required",
    headers={"WWW-Authenticate": "Bearer"},
)


def verify_access_token(provided: str) -> bool:
    """Constant-time comparison against the configured access token."""

    return secrets.compare_digest(
        provided.encode(),
        settings.access_token.encode(),
    )


def require_oidc_mode() -> None:
    """404 outside OIDC mode.

    The none and token modes share a single local user, so per-user features
    like access requests have no meaning there — and 404 leaks less than 403.
    """

    if settings.effective_auth_mode != AuthMode.OIDC:
        raise HTTPException(status_code=404, detail="Not found")


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(security),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the acting user for all three auth modes.

    none  -> shared system user
    token -> global bearer token, then the shared system user
    oidc  -> session cookie backed by the sessions table
    """

    mode = settings.effective_auth_mode

    if mode == AuthMode.NONE:
        return UserService(db).get_or_create_system_user()

    if mode == AuthMode.TOKEN:
        if not credentials or not verify_access_token(credentials.credentials):
            raise _UNAUTHORIZED
        return UserService(db).get_or_create_system_user()

    # AuthMode.OIDC
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        raise _UNAUTHORIZED

    auth_session = SessionService(db).get_valid_session(session_id)
    if not auth_session:
        raise _UNAUTHORIZED

    user = db.query(User).filter(User.id == auth_session.user_id).first()
    if not user:
        raise _UNAUTHORIZED
    return user


def is_admin_email(email: str | None) -> bool:
    """True when the address is listed in ADMIN_EMAILS.

    Only meaningful in OIDC mode, the one mode with distinct identities to
    list. The none and token modes grant admin by way of the shared local
    user instead - see is_admin_user.
    """

    if settings.effective_auth_mode != AuthMode.OIDC:
        return False
    if not email:
        return False
    return email.strip().lower() in settings.admin_emails_list


def is_admin_user(user) -> bool:
    """True when this identity may read /api/admin.

    OIDC has real users, so admin is whoever ADMIN_EMAILS lists. The none and
    token modes have a single shared local user, and whoever reaches the API
    there already holds full access to every entry and transcript - the
    dashboard only aggregates data they can already read, so withholding it
    protects nothing and the local user is the operator.

    Accepts a User or any per-user row exposing .email and .is_system, so the
    admin user table labels rows by the same rule the gate enforces.
    """

    if settings.effective_auth_mode == AuthMode.OIDC:
        return is_admin_email(getattr(user, "email", None))
    # is_system rather than an unconditional True: a database that once ran in
    # OIDC mode still holds real user rows, and those are not the operator.
    return bool(getattr(user, "is_system", False))


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Gate for /api/admin.

    404 rather than 403: a non-admin should not learn that an admin area
    exists.
    """

    if not is_admin_user(current_user):
        raise HTTPException(status_code=404, detail="Not found")
    return current_user
