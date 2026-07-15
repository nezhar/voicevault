from authlib.integrations.starlette_client import OAuth

from app.core.config import settings


class OIDCError(Exception):
    """OIDC flow failure with a stable, URL-safe error code."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code


_oauth: OAuth | None = None


def get_oauth() -> OAuth:
    """Lazy singleton so the discovery URL is only fetched when first needed."""

    global _oauth
    if _oauth is None:
        _oauth = OAuth()
        _oauth.register(
            name="oidc",
            client_id=settings.oidc_client_id,
            client_secret=settings.oidc_client_secret,
            server_metadata_url=settings.oidc_discovery_url,
            client_kwargs={
                "scope": settings.oidc_scopes,
                "code_challenge_method": "S256",  # PKCE
            },
        )
    return _oauth


def redirect_uri() -> str:
    base = (settings.public_base_url or "").rstrip("/")
    return f"{base}/api/auth/oidc/callback"


def _display_name(claims: dict) -> str | None:
    """Compose from given/family name parts; the combined name claim is the
    fallback, so IdPs that emit only e.g. a domain login as `name` still get a
    human-readable display name from the parts."""

    parts = [
        claims.get(settings.oidc_claim_given_name),
        claims.get(settings.oidc_claim_family_name),
    ]
    composed = " ".join(
        str(part).strip() for part in parts if part and str(part).strip()
    )
    return composed or claims.get(settings.oidc_claim_name) or None


def extract_claims(claims: dict) -> dict:
    """Map raw ID-token claims to our identity fields via the configurable mapping."""

    subject = claims.get(settings.oidc_claim_subject)
    email = claims.get(settings.oidc_claim_email)
    issuer = claims.get("iss")

    missing = []
    if not issuer:
        missing.append("iss")
    if not subject:
        missing.append(settings.oidc_claim_subject)
    if not email:
        missing.append(settings.oidc_claim_email)
    if missing:
        raise OIDCError(
            "missing_claim",
            f"Required claim(s) missing from ID token: {', '.join(missing)}. "
            "Check the OIDC_CLAIM_* environment variables.",
        )

    return {
        "issuer": issuer,
        "subject": str(subject),
        "email": str(email),
        "display_name": _display_name(claims),
    }
