import json
import os
from enum import Enum
from urllib.parse import urlsplit

from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class AuthMode(str, Enum):
    NONE = "none"
    TOKEN = "token"
    OIDC = "oidc"


class Settings(BaseSettings):
    # Database
    database_url: str = (
        "postgresql://voicevault_user:your_password_here@localhost:5432/voicevault"
    )

    # LLM Configuration: any OpenAI-compatible chat completions endpoint.
    # No defaults - validate_llm_settings() fails startup when these are unset.
    llm_base_url: str | None = None  # e.g. https://api.groq.com/openai/v1
    llm_api_key: str | None = None  # optional: keyless local servers (Ollama)
    llm_model: str | None = None
    # Optional tuning. Unset keeps the built-in reply limits (1024 tokens for
    # chat, 512 for summaries); reasoning models need far more because their
    # thinking counts against the same limit.
    llm_max_tokens: int | None = Field(default=None, gt=0)
    # JSON object merged into every chat completions request body, for
    # endpoint-specific options such as
    # {"chat_template_kwargs": {"enable_thinking": false}} (Qwen3 on vLLM).
    llm_extra_body: dict[str, Any] | None = None

    # Authentication
    access_token: str | None = None  # Global access token (token mode)
    auth_mode: AuthMode | None = None  # none | token | oidc; derived when unset

    @field_validator(
        "auth_mode",
        "llm_base_url",
        "llm_api_key",
        "llm_model",
        "llm_max_tokens",
        mode="before",
    )
    @classmethod
    def _blank_value_is_unset(cls, value):
        # docker compose forwards unset variables as empty strings, and a
        # value made up of only whitespace (e.g. a stray newline from a
        # secrets manager) is just as unset in practice - both should
        # become None rather than survive as a truthy string that later
        # reaches something like AsyncOpenAI(base_url="   "). auth_mode may
        # be passed an AuthMode enum member (this runs in mode="before"),
        # so only strings are stripped.
        if isinstance(value, str):
            value = value.strip()
        return None if value == "" else value

    @field_validator("llm_extra_body", mode="before")
    @classmethod
    def _parse_extra_body(cls, value):
        # pydantic-settings already decodes valid JSON; a string arriving here
        # failed that, most often a Python dict repr ('single quotes', True)
        # rendered by a deployment template.
        if not isinstance(value, str):
            return value
        value = value.strip()
        if value == "":
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            raise ValueError(
                "LLM_EXTRA_BODY must be a JSON object: double quotes around keys "
                "and strings, lowercase true/false, e.g. "
                '{"chat_template_kwargs": {"enable_thinking": false}}',
            ) from None

    # MCP is opt-in and always PAT-only, including AUTH_MODE=none.
    mcp_enabled: bool = False
    mcp_allowed_hosts: str = "localhost,localhost:*,127.0.0.1,127.0.0.1:*"

    @property
    def mcp_allowed_hosts_list(self) -> list[str]:
        hosts = [
            host.strip() for host in self.mcp_allowed_hosts.split(",") if host.strip()
        ]
        if self.public_base_url:
            hosts.append(urlsplit(self.public_base_url).netloc)
        return hosts

    # OIDC (required only for AUTH_MODE=oidc)
    oidc_discovery_url: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_scopes: str = "openid profile email"
    oidc_claim_subject: str = "sub"
    oidc_claim_email: str = "email"  # ADFS: upn
    oidc_claim_name: str = "name"  # fallback when no given/family parts are present
    oidc_claim_given_name: str = "given_name"  # ADFS: firstname
    oidc_claim_family_name: str = "family_name"  # ADFS: lastname
    public_base_url: str | None = None  # e.g. https://voicevault.example.com
    initial_owner_email: str | None = None  # takes over legacy entries on first login
    admin_emails: str = ""  # comma-separated; grants /api/admin access (OIDC only)

    # Sessions & CORS
    session_secret: str | None = None  # signs the OIDC handshake cookie
    session_lifetime_hours: int = 12
    session_cookie_secure: bool = True  # set false only for local HTTP dev
    cors_origins: str = "http://localhost:3000"  # comma-separated

    @property
    def effective_auth_mode(self) -> AuthMode:
        if self.auth_mode is not None:
            return self.auth_mode
        return AuthMode.TOKEN if self.access_token else AuthMode.NONE

    @property
    def cors_origins_list(self) -> list[str]:
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]

    @property
    def admin_emails_list(self) -> list[str]:
        """Normalised to match how User.email is stored (stripped, lowercased)."""

        return [
            email.strip().lower()
            for email in self.admin_emails.split(",")
            if email.strip()
        ]

    # File Storage
    upload_dir: str = "uploads"
    max_upload_size: int = 500 * 1024 * 1024  # 500MB (chunking allows large files)
    max_file_size: int = (
        26214400  # This gets overridden by MAX_FILE_SIZE env var (25MB chunk limit)
    )

    # Maintenance
    # Fills in consumption metrics for entries predating them, in the
    # background on startup. Idempotent; set false to run it only by hand.
    backfill_metrics_on_startup: bool = True

    # S3 Configuration
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket_name: str = "voicevault"

    # Supported file types (with audio conversion to MP3 for Groq compatibility)
    # FFmpeg can convert most audio/video formats to MP3 for Groq processing
    supported_audio_formats: list[str] = [
        "mp3",
        "wav",
        "m4a",
        "flac",
        "aac",
        "ogg",
        "wma",
    ]
    supported_video_formats: list[str] = [
        "mp4",
        "avi",
        "mov",
        "mkv",
        "webm",
        "mpeg",
        "mpg",
    ]

    # Processing
    processing_timeout: int = 3600  # 1 hour

    # Development
    debug: bool = False
    log_level: str = "info"

    class Config:
        env_file = ".env"


settings = Settings()


def validate_auth_settings() -> None:
    """Fail fast on incomplete OIDC configuration (called on startup)."""

    if settings.effective_auth_mode != AuthMode.OIDC:
        return

    required = {
        "OIDC_DISCOVERY_URL": settings.oidc_discovery_url,
        "OIDC_CLIENT_ID": settings.oidc_client_id,
        "OIDC_CLIENT_SECRET": settings.oidc_client_secret,
        "SESSION_SECRET": settings.session_secret,
        "PUBLIC_BASE_URL": settings.public_base_url,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(
            f"AUTH_MODE=oidc requires these environment variables: {', '.join(missing)}",
        )


# Retired by the OpenAI-compatible LLM integration, mapped to the variable
# that replaces each. Groq's key is not listed: the ASR worker still uses it.
RETIRED_LLM_VARIABLES = {
    "LLM_PROVIDER": "LLM_BASE_URL",
    "CEREBRAS_API_KEY": "LLM_API_KEY",
    "NEBIUS_API_KEY": "LLM_API_KEY",
    "OLLAMA_BASE_URL": "LLM_BASE_URL",
    "OLLAMA_MODEL": "LLM_MODEL",
}


def validate_llm_settings() -> None:
    """Fail fast on missing or retired LLM configuration (called on startup).

    Both problems are reported in one message so a migration is fixed in a
    single pass instead of one failed restart per variable.
    """

    problems: list[str] = []

    required = {
        "LLM_BASE_URL": settings.llm_base_url,
        "LLM_MODEL": settings.llm_model,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        problems.append(
            f"missing required environment variables: {', '.join(missing)}",
        )

    # Deliberately os.environ, not settings/.env: this catches a retired
    # variable set via the environment (docker compose, shell export). A
    # retired variable left in a .env file is caught earlier and separately
    # - pydantic-settings parses .env itself without writing it into
    # os.environ, and (with extra inputs forbidden) raises ValidationError
    # at Settings() construction, i.e. at import time, before this function
    # ever runs.
    retired = [
        f"{name} (use {replacement})"
        for name, replacement in RETIRED_LLM_VARIABLES.items()
        if os.environ.get(name)
    ]
    if retired:
        problems.append(
            "provider-specific LLM variables are no longer supported, remove: "
            + ", ".join(retired),
        )

    if problems:
        raise RuntimeError(
            "LLM configuration error: "
            + "; ".join(problems)
            + ". Point LLM_BASE_URL at any OpenAI-compatible endpoint, set "
            "LLM_MODEL, and set LLM_API_KEY if the endpoint needs one.",
        )
