import re
import secrets

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger
from sqlalchemy.orm import Session

from app.core.config import AuthMode, settings
from app.db.database import get_db
from app.models.user import User
from app.core.capabilities import ROUTE_POLICY, Capability, Marker, route_rule
from app.services.pat_service import (
    PAT_MARKER,
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


_TEMPLATE_PATTERNS: list[tuple[re.Pattern, str]] = []


def _route_path(request: Request) -> str | None:
    """The matched route template, e.g. /api/entries/{entry_id}.

    Set by FastAPI once routing has happened; matched against the rule book
    otherwise (requests built outside the router)."""

    scope = getattr(request, "scope", None) or {}
    route = scope.get("route")
    if route is not None and getattr(route, "path_format", None):
        return route.path_format
    if not _TEMPLATE_PATTERNS:
        for _, template in ROUTE_POLICY:
            pattern = re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(template))
            _TEMPLATE_PATTERNS.append((re.compile(f"^{pattern}$"), template))
    path = request.url.path
    for pattern, template in _TEMPLATE_PATTERNS:
        if pattern.match(path):
            return template
    return None


def _enforce_pat_permission(request: Request, pat, user, db: Session) -> None:
    """Refuse a token before its use is recorded when no capability could let it
    through. Project-level checks happen in the routes, which know the project.

    Routes missing from ROUTE_POLICY, interactive-only routes and upload-link
    routes are never token-callable, so a new route cannot become
    token-callable by accident.
    """

    from app.services.permission_service import PermissionService, token_capabilities

    method = request.method.upper()
    path = request.url.path
    path_format = _route_path(request)
    rule = route_rule(method, path_format) if path_format else None
    required = rule.value if rule is not None else None

    service = PermissionService(db)
    owner = service.effective(user)
    effective = service.for_token(owner, pat)
    request.state.effective = effective
    request.state.effective_user = user.id
    # Whether the owner may see the admin area at all, whatever the token holds.
    hidden_admin = path.startswith("/api/admin") and not owner.has(
        Capability.ADMIN_VIEW,
    )

    if isinstance(rule, Capability):
        allowed = rule in token_capabilities(pat) and effective.anywhere(rule)
    else:
        allowed = rule == Marker.OPEN
    if allowed and not hidden_admin:
        return

    logger.warning(
        "authorization_denied user_id={} pat_id={} required_permission={} method={} path={}",
        pat.user_id,
        pat.id,
        required,
        method,
        path,
    )
    # Keep the admin area undiscoverable: a token whose owner may not see it
    # gets the same 404 that the admin gate would have produced.
    if hidden_admin:
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
        _enforce_pat_permission(request, result.token, result.user, db)
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


def _require_admin_capability(
    request: Request,
    db: Session,
    user: User,
    capability: Capability,
) -> User:
    """Admins (ADMIN_EMAILS / the local user) and holders of the capability.

    404 rather than 403: a non-admin should not learn that an admin area
    exists.
    """

    from app.services.permission_service import current_effective

    if not current_effective(request, db, user).has(capability):
        raise HTTPException(status_code=404, detail="Not found")
    return user


def require_admin_view(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Gate for /api/admin reads."""

    return _require_admin_capability(request, db, current_user, Capability.ADMIN_VIEW)


def require_admin_manage(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Gate for /api/admin writes."""

    return _require_admin_capability(
        request,
        db,
        current_user,
        Capability.ADMIN_MANAGE,
    )


def require_templates_manage(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Gate for writes to /api/prompt-templates (404 like the admin area)."""

    return _require_admin_capability(
        request,
        db,
        current_user,
        Capability.TEMPLATES_MANAGE,
    )
