from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.routes import entries
from app.db.database import engine
from app.models import entry  # Import models to register them

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events"""
    # Startup
    try:
        from app.db.database import Base
        Base.metadata.create_all(bind=engine)
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
app.include_router(entries.router, prefix="/api/entries", tags=["entries"])

@app.get("/")
async def root():
    return {"message": "VoiceVault API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}