from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.routes import entries, auth, prompt_templates
from app.db.database import engine, SessionLocal
from app.models import entry, prompt_template  # Import models to register them
from app.services.prompt_template_service import PromptTemplateService

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
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(entries.router, prefix="/api/entries", tags=["entries"])
app.include_router(prompt_templates.router, prefix="/api/prompt-templates", tags=["prompt-templates"])

@app.get("/")
async def root():
    return {"message": "VoiceVault API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
