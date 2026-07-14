from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from app.api.routes import entries, auth, prompt_templates, projects
from app.core.config import AuthMode, settings, validate_auth_settings
from app.db.database import engine, SessionLocal
from app.services.prompt_template_service import PromptTemplateService
from app.services.user_service import UserService
import app.models  # noqa: F401  (registers all tables on Base)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events"""
    # Startup
    try:
        from app.db.database import Base, ensure_entry_schema

        Base.metadata.create_all(bind=engine)
        ensure_entry_schema()
        db = SessionLocal()
        try:
            PromptTemplateService(db).seed_defaults_if_empty()

            validate_auth_settings()
            if settings.effective_auth_mode in (AuthMode.NONE, AuthMode.TOKEN):
                user_service = UserService(db)
                system_user = user_service.get_or_create_system_user()
                user_service.assign_orphan_entries(system_user)
            elif not settings.initial_owner_email:
                print(
                    "⚠️  AUTH_MODE=oidc without INITIAL_OWNER_EMAIL: "
                    "pre-existing entries stay invisible until it is set",
                )
        finally:
            db.close()
        print("✅ Database tables created/verified")
    except Exception as e:
        print(f"❌ Database migration failed: {str(e)}")
        raise

    yield

    # Shutdown (if needed)
    print("🔄 API shutting down")


app = FastAPI(
    title="VoiceVault API",
    description="Enterprise voice intelligence platform",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if settings.effective_auth_mode == AuthMode.OIDC:
    # Only used to hold state/code_verifier during the OIDC handshake
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        same_site="lax",
        https_only=settings.session_cookie_secure,
    )

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(entries.router, prefix="/api/entries", tags=["entries"])
app.include_router(
    prompt_templates.router,
    prefix="/api/prompt-templates",
    tags=["prompt-templates"],
)
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])


@app.get("/")
async def root():
    return {"message": "VoiceVault API", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
