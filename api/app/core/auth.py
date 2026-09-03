import secrets

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger
from sqlalchemy.orm import Session

from app.core.config import AuthMode, settings
from app.db.database import get_db
from app.models.user import User
from app.services.pat_service import (
    PAT_MARKER,
    PATPermission,
    PATService,
    safe_token_prefix,
)
from app.services.session_service import SESSION_COOKIE_NAME, SessionService
from app.services.user_service import UserService

security = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Authentication required",
    headers={"WWW-Authenticate": "Bearer"},
)


def _log_auth_failure(request: Request, reason: str, token: str | None = None) -> None:
    logger.warning(
        "authentication_failed reason={} method={} path={} client_ip={} token_prefix={}",
        reason,
        request.method,
        request.url.path,
        request.client.host if request.client else "unknown",
        safe_token_prefix(token) if token else None,
    )


def _set_auth_state(request: Request, method: str, pat=None) -> None:
    request.state.auth_method = method
    request.state.pat = pat


# Routes a PAT may call without any scope: it only reveals the token's own owner.
_PAT_UNSCOPED_ROUTES = frozenset({("GET", "/api/auth/me")})

# Prefix -> (read scope, write scope). Anything not listed is denied to PATs, so
# a new router cannot become PAT-callable by accident. Admin has no write scope:
# every admin mutation manages credentials or accounts and requires interactive
# authentication, so PATs are refused there outright.
_PAT_SCOPES: dict[str, tuple[PATPermission, PATPermission | None]] = {
    "/api/entries": (PATPermission.ENTRIES_READ, PATPermission.ENTRIES_WRITE),
    "/api/projects": (PATPermission.PROJECTS_READ, PATPermission.PROJECTS_WRITE),
    "/api/prompt-templates": (
        PATPermission.TEMPLATES_READ,
        PATPermission.TEMPLATES_WRITE,
    ),
    "/api/admin": (PATPermission.ADMIN_READ, None),
}
_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Admin reads that manage credentials rather than report on them. Their routes
# depend on require_interactive_auth, so a PAT can never satisfy them; listing
# them here refuses the call while resolving the token instead of after, which
# keeps a denied probe out of the token's usage record.
_PAT_INTERACTIVE_ONLY = ("/api/admin/pats", "/api/admin/pat-users")


class _PATDenied(Exception):
    """The route is not available to PATs at all (no scope could grant it)."""


def _required_pat_permission(method: str, path: str) -> str | None:
    """Scope a PAT needs for this request; None when no scope is required.

    Raises _PATDenied for routes PATs may never call (unmapped prefixes and
    admin mutations).
    """

    if (method, path.rstrip("/")) in _PAT_UNSCOPED_ROUTES:
        return None
    for prefix in _PAT_INTERACTIVE_ONLY:
        if path == prefix or path.startswith(prefix + "/"):
            raise _PATDenied()
    for prefix, (read_scope, write_scope) in _PAT_SCOPES.items():
        if path == prefix or path.startswith(prefix + "/"):
            is_read = method in _READ_METHODS or (
                method == "POST" and prefix == "/api/entries" and path.endswith("/chat")
            )
            if is_read:
                return read_scope.value
            if write_scope is None:
                raise _PATDenied()
            return write_scope.value
    raise _PATDenied()


def _enforce_pat_permission(request: Request, pat, user) -> None:
    method = request.method.upper()
    path = request.url.path
    try:
        required = _required_pat_permission(method, path)
    except _PATDenied:
        required = None
        allowed = False
    else:
        allowed = required is None or required in set(pat.permissions or [])
        # A scope never outranks its owner. require_admin would refuse this
        # anyway, but only after get_current_user has already recorded the call
        # as usage - and admin:read can be attached to any user's token.
        if allowed and path.startswith("/api/admin") and not is_admin_user(user):
            allowed = False
    if allowed:
        return

    logger.warning(
        "authorization_denied user_id={} pat_id={} required_permission={} method={} path={}",
        pat.user_id,
        pat.id,
        required,
        method,
        path,
    )
    # Keep the admin area undiscoverable: a non-admin's token gets the same
    # 404 that require_admin would have produced, whatever its scopes.
    if path.startswith("/api/admin") and not is_admin_user(user):
        raise HTTPException(status_code=404, detail="Not found")
    raise HTTPException(status_code=403, detail="Insufficient token permissions")


def verify_access_token(provided: str) -> bool:
    """Constant-time comparison against the configured access token."""

    configured = settings.access_token
    return bool(
        configured and secrets.compare_digest(provided.encode(), configured.encode()),
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
    """Resolve a development user, legacy token, OIDC session, or user PAT."""

    mode = settings.effective_auth_mode
    provided = credentials.credentials if credentials else None

    # PATs identify a real user in every mode. AUTH_MODE=none remains bypassable
    # by design and is documented as unsuitable for permission enforcement.
    if provided and provided.startswith(PAT_MARKER):
        service = PATService(db)
        result = service.validate(provided)
        if result.failure is not None or result.token is None or result.user is None:
            reason = result.failure.value if result.failure else "invalid"
            _log_auth_failure(request, reason, provided)
            raise _UNAUTHORIZED
        _set_auth_state(request, "pat", result.token)
        _enforce_pat_permission(request, result.token, result.user)
        # Only successful, authorized requests count as usage.
        service.touch_last_used(result.token)
        return result.user

    if mode == AuthMode.NONE:
        user = UserService(db).get_or_create_system_user()
        _set_auth_state(request, "development")
        return user

    if mode == AuthMode.TOKEN:
        if not provided:
            reason = "malformed" if request.headers.get("authorization") else "missing"
            _log_auth_failure(request, reason)
            raise _UNAUTHORIZED
        if not verify_access_token(provided):
            _log_auth_failure(request, "invalid")
            raise _UNAUTHORIZED
        user = UserService(db).get_or_create_system_user()
        if not user.is_active:
            _log_auth_failure(request, "inactive_user")
            raise _UNAUTHORIZED
        _set_auth_state(request, "legacy_token")
        return user

    # AuthMode.OIDC: only PATs are accepted as bearer credentials. Any other
    # Authorization header is ignored in favour of the session cookie - the
    # browser client may still carry a stale token-mode credential, and a proxy
    # may inject its own header - but automation without a cookie still fails.
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        _log_auth_failure(
            request,
            "malformed" if request.headers.get("authorization") else "missing",
        )
        raise _UNAUTHORIZED
    auth_session = SessionService(db).get_valid_session(session_id)
    if not auth_session:
        _log_auth_failure(request, "invalid_session")
        raise _UNAUTHORIZED
    user = db.query(User).filter(User.id == auth_session.user_id).first()
    if not user or not user.is_active:
        _log_auth_failure(request, "inactive_user" if user else "invalid_session")
        raise _UNAUTHORIZED
    _set_auth_state(request, "session")
    return user


def require_interactive_auth(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> User:
    """PATs cannot mint or manage credentials, including themselves."""

    if request.state.auth_method == "pat":
        raise HTTPException(
            status_code=403,
            detail="Interactive authentication required",
        )
    return current_user


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
    """Gate for /api/admin and for writes to /api/prompt-templates.

    404 rather than 403: a non-admin should not learn that an admin area
    exists.
    """

    if not is_admin_user(current_user):
        raise HTTPException(status_code=404, detail="Not found")
    return current_user
