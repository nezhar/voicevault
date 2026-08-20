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
