"""OAuth sign-in for MCP clients: registered clients, pending sign-ins, codes.

The MCP SDK serves the protocol endpoints and checks PKCE, redirect URIs and
code expiry; this module only stores and decides. An approved sign-in ends in
an ordinary personal access token (source="oauth"), so everything that holds
for tokens - capabilities cut to the owner, project limits, revocation under
API Tokens - holds for OAuth clients too. No refresh tokens are issued.
"""

import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from loguru import logger
from mcp.server.auth.provider import construct_redirect_uri
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timeutils import utcnow
from app.models.oauth import OAuthAuthorizationRequest, OAuthClient
from app.models.personal_access_token import PersonalAccessToken
from app.models.user import User
from app.services.pat_service import PATService

REQUEST_TTL = timedelta(minutes=10)
CODE_TTL = timedelta(minutes=5)
STALE_CLIENT_AGE = timedelta(days=30)
CODE_MARKER = "vvoac_"
LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")
CONSENT_PATH = "/oauth/consent"


class OAuthRequestGone(LookupError):
    """Unknown, expired or already decided."""


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def is_loopback_redirect(uri: str) -> bool:
    """A redirect to the machine the browser runs on, where native clients listen."""

    parts = urlsplit(uri)
    return parts.scheme == "http" and parts.hostname in LOOPBACK_HOSTS


def normalize_address(uri: str) -> str:
    """https://client.example and https://client.example/ are the same address."""

    parts = urlsplit(uri)
    return urlunsplit(parts._replace(path=parts.path or "/"))


def redirect_allowed(uri: str) -> bool:
    if is_loopback_redirect(uri):
        return True
    allowed = {normalize_address(item) for item in settings.oauth_redirect_uris_list}
    return normalize_address(uri) in allowed


def consent_url(request_id: UUID) -> str:
    # The id travels in the fragment, which never reaches a server log.
    return f"{settings.public_base_url.rstrip('/')}{CONSENT_PATH}#{request_id}"


class OAuthService:
    def __init__(self, db: Session):
        self.db = db

    # -- clients ------------------------------------------------------------

    def get_client(self, client_id: str) -> dict | None:
        client = self.db.get(OAuthClient, client_id)
        return dict(client.client_info) if client is not None else None

    def client_name(self, client_id: str) -> str:
        client = self.db.get(OAuthClient, client_id)
        name = (client.client_name if client else None) or "MCP client"
        return name[:80]

    def register_client(self, client_id: str, info: dict) -> None:
        self.db.add(
            OAuthClient(
                client_id=client_id,
                client_name=(info.get("client_name") or None),
                client_info=info,
            ),
        )
        self.db.commit()

    def prune_stale_clients(self) -> int:
        """Drop registrations that never led to a token within STALE_CLIENT_AGE."""

        cutoff = utcnow() - STALE_CLIENT_AGE
        used = {
            client_id
            for (client_id,) in self.db.query(PersonalAccessToken.oauth_client_id)
            .filter(PersonalAccessToken.oauth_client_id.is_not(None))
            .distinct()
            .all()
        }
        stale = [
            client
            for client in self.db.query(OAuthClient)
            .filter(OAuthClient.created_at < cutoff)
            .all()
            if client.client_id not in used
        ]
        for client in stale:
            self.db.delete(client)
        if stale:
            self.db.commit()
            logger.info(f"Removed {len(stale)} unused OAuth client registration(s)")
        return len(stale)

    # -- sign-in requests ---------------------------------------------------

    def create_request(
        self,
        *,
        client_id: str,
        redirect_uri: str,
        redirect_uri_provided_explicitly: bool,
        code_challenge: str,
        state: str | None,
        scopes: list[str] | None,
        resource: str | None,
    ) -> OAuthAuthorizationRequest:
        request = OAuthAuthorizationRequest(
            client_id=client_id,
            redirect_uri=redirect_uri,
            redirect_uri_provided_explicitly=redirect_uri_provided_explicitly,
            code_challenge=code_challenge,
            state=state,
            scopes=scopes,
            resource=resource,
            expires_at=utcnow() + REQUEST_TTL,
        )
        self.db.add(request)
        self.db.commit()
        self.db.refresh(request)
        return request

    def pending(self, request_id: UUID) -> OAuthAuthorizationRequest:
        request = self.db.get(OAuthAuthorizationRequest, request_id)
        if (
            request is None
            or request.status != "pending"
            or request.expires_at <= utcnow()
        ):
            raise OAuthRequestGone(
                "This sign-in request has expired or was already decided.",
            )
        return request

    def approve(
        self,
        request_id: UUID,
        user: User,
        capabilities: list[str],
        project_ids: list[UUID] | None,
    ) -> str:
        """Record the decision and return where the browser goes next."""

        request = self.pending(request_id)
        code = CODE_MARKER + secrets.token_urlsafe(32)
        request.status = "approved"
        request.user_id = user.id
        request.capabilities = sorted(set(capabilities))
        request.project_ids = (
            sorted({str(pid) for pid in project_ids})
            if project_ids is not None
            else None
        )
        request.code_hash = hash_code(code)
        request.code_expires_at = utcnow() + CODE_TTL
        self.db.commit()
        logger.info(
            "oauth_sign_in_approved user_id={} client_id={}",
            user.id,
            request.client_id,
        )
        return construct_redirect_uri(
            request.redirect_uri,
            code=code,
            state=request.state,
        )

    def deny(self, request_id: UUID) -> str:
        request = self.pending(request_id)
        request.status = "denied"
        self.db.commit()
        return construct_redirect_uri(
            request.redirect_uri,
            error="access_denied",
            error_description="The user denied the sign-in",
            state=request.state,
        )

    # -- codes and tokens ---------------------------------------------------

    def load_code(self, client_id: str, code: str) -> OAuthAuthorizationRequest | None:
        request = (
            self.db.query(OAuthAuthorizationRequest)
            .filter(
                OAuthAuthorizationRequest.code_hash == hash_code(code),
                OAuthAuthorizationRequest.client_id == client_id,
                OAuthAuthorizationRequest.status == "approved",
            )
            .first()
        )
        if request is None or request.code_used_at is not None:
            return None
        return request

    def exchange(
        self,
        client_id: str,
        code: str,
    ) -> tuple[PersonalAccessToken, str] | None:
        """Use the code (once) and issue the token. None when the code is
        unknown, used or expired, or its user can no longer sign in."""

        request = self.load_code(client_id, code)
        if request is None or request.code_expires_at <= utcnow():
            return None
        # Claim the code before issuing, so a replay can never get a second token.
        claimed = (
            self.db.query(OAuthAuthorizationRequest)
            .filter(
                OAuthAuthorizationRequest.id == request.id,
                OAuthAuthorizationRequest.code_used_at.is_(None),
            )
            .update(
                {OAuthAuthorizationRequest.code_used_at: utcnow()},
                synchronize_session=False,
            )
        )
        if not claimed:
            self.db.rollback()
            return None
        user = self.db.get(User, request.user_id)
        if user is None or not user.is_active:
            self.db.commit()
            return None
        pat, raw = PATService(self.db).create(
            user_id=user.id,
            name=f"{self.client_name(client_id)} (OAuth)",
            permissions=request.capabilities or [],
            expires_at=utcnow() + timedelta(days=settings.oauth_token_ttl_days),
            project_ids=request.project_ids,
            source="oauth",
            oauth_client_id=client_id,
            commit=False,
        )
        self.db.commit()
        self.db.refresh(pat)
        logger.info(
            "oauth_token_issued user_id={} client_id={} pat_id={}",
            user.id,
            client_id,
            pat.id,
        )
        return pat, raw
