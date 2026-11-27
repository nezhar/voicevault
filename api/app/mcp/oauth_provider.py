"""VoiceVault as the OAuth authorization server of its own MCP endpoint.

An MCP client needs nothing but the URL: it registers itself, sends the user to
the consent page, and trades the code it gets back for a token. The SDK serves
/authorize, /token, /register and /revoke and validates PKCE, redirect URIs
and code expiry; this provider only stores and loads, through OAuthService.
"""

from collections.abc import Callable
from datetime import timezone
from typing import Any

import anyio
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    RegistrationError,
    TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from sqlalchemy.orm import Session

from app.core.capabilities import Capability
from app.core.config import settings
from app.services.oauth_service import (
    OAuthService,
    consent_url,
    redirect_allowed,
)
from app.services.pat_service import PATService


class VoiceVaultOAuthProvider:
    def __init__(self, session_factory: Callable[[], Session]):
        self.session_factory = session_factory

    async def _db(self, operation: Callable[[OAuthService], Any]) -> Any:
        def run():
            db = self.session_factory()
            try:
                return operation(OAuthService(db))
            finally:
                db.close()

        return await anyio.to_thread.run_sync(run)

    # -- clients ------------------------------------------------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        info = await self._db(lambda service: service.get_client(client_id))
        return OAuthClientInformationFull.model_validate(info) if info else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        refused = [
            str(uri)
            for uri in client_info.redirect_uris or []
            if not redirect_allowed(str(uri))
        ]
        if refused or not client_info.redirect_uris:
            raise RegistrationError(
                error="invalid_redirect_uri",
                error_description=(
                    "Redirect addresses must be http://localhost (any port) or listed "
                    f"in OAUTH_REDIRECT_URIS; refused: {', '.join(refused) or 'none given'}"
                ),
            )
        info = client_info.model_dump(mode="json", exclude_none=True)
        await self._db(
            lambda service: service.register_client(client_info.client_id, info),
        )

    # -- authorization ------------------------------------------------------

    async def authorize(
        self,
        client: OAuthClientInformationFull,
        params: AuthorizationParams,
    ) -> str:
        def create(service: OAuthService) -> str:
            request = service.create_request(
                client_id=client.client_id,
                redirect_uri=str(params.redirect_uri),
                redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
                code_challenge=params.code_challenge,
                state=params.state,
                scopes=params.scopes,
                resource=params.resource,
            )
            return consent_url(request.id)

        return await self._db(create)

    async def load_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: str,
    ) -> AuthorizationCode | None:
        def load(service: OAuthService):
            request = service.load_code(client.client_id, authorization_code)
            if request is None:
                return None
            return AuthorizationCode(
                code=authorization_code,
                scopes=request.capabilities or [],
                expires_at=_utc_timestamp(request.code_expires_at),
                client_id=client.client_id,
                code_challenge=request.code_challenge,
                redirect_uri=request.redirect_uri,
                redirect_uri_provided_explicitly=request.redirect_uri_provided_explicitly,
                resource=request.resource,
                subject=str(request.user_id),
            )

        return await self._db(load)

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        issued = await self._db(
            lambda service: service.exchange(client.client_id, authorization_code.code),
        )
        if issued is None:
            raise TokenError(
                error="invalid_grant",
                error_description="authorization code is invalid or was already used",
            )
        pat, raw = issued
        return OAuthToken(
            access_token=raw,
            token_type="Bearer",
            expires_in=settings.oauth_token_ttl_days * 86400,
            scope=" ".join(pat.permissions),
        )

    # -- refresh tokens: not issued ----------------------------------------

    async def load_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: str,
    ) -> RefreshToken | None:
        return None

    async def exchange_refresh_token(self, client, refresh_token, scopes) -> OAuthToken:
        raise TokenError(
            error="unsupported_grant_type",
            error_description="VoiceVault issues no refresh tokens; sign in again",
        )

    # -- access tokens ------------------------------------------------------

    async def load_access_token(self, token: str) -> AccessToken | None:
        def load(service: OAuthService):
            result = PATService(service.db).validate(token)
            pat = result.token
            if result.failure is not None or pat is None:
                return None
            return AccessToken(
                token=token,
                client_id=pat.oauth_client_id or "",
                scopes=[
                    name
                    for name in pat.permissions or []
                    if name in Capability._value2member_map_
                ],
                expires_at=int(_utc_timestamp(pat.expires_at))
                if pat.expires_at
                else None,
                subject=str(pat.user_id),
            )

        return await self._db(load)

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        def revoke(service: OAuthService):
            result = PATService(service.db).validate(token.token)
            pat = result.token
            # A client may only revoke what was issued to it.
            if pat is not None and pat.oauth_client_id == token.client_id:
                PATService(service.db).revoke(pat.id)

        await self._db(revoke)


def _utc_timestamp(value) -> float:
    """Naive UTC datetime (how the database stores it) to a Unix timestamp."""

    return value.replace(tzinfo=timezone.utc).timestamp()
