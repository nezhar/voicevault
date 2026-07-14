from pydantic import field_validator
from pydantic_settings import BaseSettings
from enum import Enum


class LLMProvider(str, Enum):
    GROQ = "groq"
    CEREBRAS = "cerebras"
    OLLAMA = "ollama"
    NEBIUS = "nebius"


class AuthMode(str, Enum):
    NONE = "none"
    TOKEN = "token"
    OIDC = "oidc"


class Settings(BaseSettings):
    # Database
    database_url: str = (
        "postgresql://voicevault_user:your_password_here@localhost:5432/voicevault"
    )

    # LLM Configuration
    llm_provider: LLMProvider = LLMProvider.GROQ
    llm_model: str = "llama-3.3-70b-versatile"  # Groq default

    # API Keys
    groq_api_key: str | None = None
    cerebras_api_key: str | None = None

    # Ollama Configuration
    ollama_base_url: str = "http://localhost:11434"  # Default Ollama URL
    ollama_model: str = "llama3.2"  # Default Ollama model

    # Nebius Configuration
    nebius_api_key: str | None = None

    # Authentication
    access_token: str | None = None  # Global access token (token mode)
    auth_mode: AuthMode | None = None  # none | token | oidc; derived when unset

    @field_validator("auth_mode", mode="before")
    @classmethod
    def _empty_auth_mode_is_unset(cls, value):
        # docker compose forwards unset variables as empty strings
        return None if value == "" else value

    # OIDC (required only for AUTH_MODE=oidc)
    oidc_discovery_url: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_scopes: str = "openid profile email"
    oidc_claim_subject: str = "sub"
    oidc_claim_email: str = "email"  # ADFS: upn
    oidc_claim_name: str = "name"  # ADFS: unique_name
    public_base_url: str | None = None  # e.g. https://voicevault.example.com
    initial_owner_email: str | None = None  # takes over legacy entries on first login

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

    # File Storage
    upload_dir: str = "uploads"
    max_upload_size: int = 500 * 1024 * 1024  # 500MB (chunking allows large files)
    max_file_size: int = (
        26214400  # This gets overridden by MAX_FILE_SIZE env var (25MB chunk limit)
    )

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
