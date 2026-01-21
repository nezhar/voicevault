# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

VoiceVault is an enterprise voice intelligence platform for hackathon submission (RAISE2025 - Vultr Track). It transforms voice conversations into actionable insights using AI/ML with enterprise-grade security.

**Core Pipeline**: Audio Upload → ASR Provider (Fast Transcription) → LLM Provider (Intelligent Analysis) → VoiceVault Dashboard → Enterprise Integrations

## System Architecture

### Multi-Service Architecture
The application uses a microservices architecture with 5 containerized services defined in `compose.yml`:

1. **UI Service** (`/ui`): React + TypeScript + Vite frontend served via Nginx on port 3000
2. **API Service** (`/api`): FastAPI backend on port 8000 with SQLAlchemy ORM and Alembic migrations
3. **Download Worker** (`/worker` with `WORKER_MODE=download`): Background service for URL-based content extraction using yt-dlp
4. **ASR Worker** (`/worker` with `WORKER_MODE=asr`): Background service for audio transcription using Groq Whisper
5. **Database**: PostgreSQL 17 with automatic table creation on startup
6. **MinIO**: S3-compatible object storage for development (production uses Vultr Object Storage)

### Worker Architecture Pattern
The `/worker` directory contains a unified worker codebase that runs in two modes:
- **Download Worker**: Polls database for entries with `entry_type='url'` and `status='NEW'`, downloads videos/audio using yt-dlp, extracts audio with FFmpeg, uploads to S3, updates status to `IN_PROGRESS`
- **ASR Worker**: Polls database for entries with `status='IN_PROGRESS'`, downloads audio from S3, transcribes using Groq Whisper API, stores transcript in database, updates status to `READY`

Both workers use the same Docker image but different environment variables to control behavior.

### Entry Status Workflow
Entries progress through these states:
- `NEW` → Entry just created, queued for download worker
- `IN_PROGRESS` → Audio downloaded, queued for ASR worker
- `READY` → Transcript ready, available for chat/analysis
- `COMPLETE` → User marked as finished (optional)

### Database Schema
The primary model is `Entry` in `/api/app/models/entry.py` and `/worker/app/models/entry.py`:
- Uses SQLAlchemy ORM with automatic table creation via `Base.metadata.create_all()` in `app/main.py:15`
- No manual migrations needed - tables auto-created on startup
- Database URL constructed from environment variables via `app/db/database.py`

## Development Commands

### Local Development Setup
```bash
# 1. Copy environment configuration
cp .env.example .env
# Edit .env with your API keys (GROQ_API_KEY is required)

# 2. Start all services with Docker Compose (includes PostgreSQL and MinIO)
docker compose up --build

# 3. Access services
# - Frontend: http://localhost:3000
# - API: http://localhost:8000
# - API Docs: http://localhost:8000/docs
# - PostgreSQL: localhost:5432
# - MinIO Console: http://localhost:9001
```

### Frontend Development (React + TypeScript + Vite)
```bash
cd ui

# Install dependencies
npm install

# Development server with hot reload
npm run dev

# Production build
npm run build

# Preview production build
npm preview
```

### Backend Development (FastAPI)
```bash
cd api

# Install dependencies
pip install -r requirements.txt

# Run API server directly (without Docker)
# Set DATABASE_URL environment variable first
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Access API documentation
# Swagger UI: http://localhost:8000/docs
# ReDoc: http://localhost:8000/redoc
```

### Worker Development
```bash
cd worker

# Install dependencies
pip install -r requirements.txt

# Run download worker
WORKER_MODE=download DATABASE_URL=postgresql://... python -m app.main

# Run ASR worker
WORKER_MODE=asr DATABASE_URL=postgresql://... python -m app.main
```

### Database Operations
```bash
# The application uses automatic table creation on startup (app/main.py:15)
# No manual migrations required for development

# If using Alembic for schema changes:
cd api

# Create new migration
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1

# View migration history
alembic history
```

### Production Deployment
```bash
# Production uses compose.prod.yml with self-contained containers
# (no volume mounts, code embedded in images)

# Option 1: Build locally and run
docker compose -f compose.prod.yml build
docker compose -f compose.prod.yml up -d

# Option 2: Build and push to registry, then pull on production server
export REGISTRY=fra.vultrcr.com/raise2025/
export VERSION=v1.0.0

# On build machine:
docker compose -f compose.prod.yml build
docker compose -f compose.prod.yml push

# On production server:
docker compose -f compose.prod.yml pull
docker compose -f compose.prod.yml up -d

# View logs
docker compose -f compose.prod.yml logs -f

# Stop services
docker compose -f compose.prod.yml down
```

### Testing and Debugging
```bash
# View service logs
docker compose logs -f api
docker compose logs -f worker-asr
docker compose logs -f worker-download

# Check service status
docker compose ps

# Execute commands inside containers
docker compose exec api python -c "from app.db.database import engine; print(engine.url)"
docker compose exec db psql -U voicevault_user -d voicevault -c "\dt"

# Monitor resource usage
docker stats

# Test API endpoints
curl http://localhost:8000/health
curl http://localhost:8000/api/entries/
```

## Environment Configuration

### Required Environment Variables
```bash
# Core API Keys (REQUIRED)
GROQ_API_KEY=your_groq_api_key          # Get from console.groq.com
CEREBRAS_API_KEY=your_cerebras_api_key  # Optional - only if using Cerebras LLM

# Database Configuration
POSTGRES_HOST=db                         # Use 'db' for local, managed host for production
POSTGRES_PORT=5432
POSTGRES_DB=voicevault
POSTGRES_USER=voicevault_user
POSTGRES_PASSWORD=secure_password_here

# S3 Storage Configuration
S3_ENDPOINT_URL=http://minio:9000       # Local dev, or https://ewr1.vultrobjects.com for production
S3_ACCESS_KEY=minioadmin                # Local dev credentials
S3_SECRET_KEY=minioadmin
S3_BUCKET_NAME=voicevault

# Provider Configuration
ASR_PROVIDER=groq                        # Options: groq, whisper_asr
ASR_MODEL=whisper-large-v3-turbo        # Options: whisper-large-v3, whisper-large-v3-turbo

# Whisper ASR Webservice Configuration (only needed if ASR_PROVIDER=whisper_asr)
WHISPER_ASR_URL=http://localhost:9000   # whisper-asr-webservice URL (use http://whisper:9000 in Docker Compose)
LLM_PROVIDER=groq                        # Options: groq, cerebras, ollama
LLM_MODEL=llama-3.3-70b-versatile       # groq: llama-3.3-70b-versatile, llama-3.1-70b-versatile
                                         # cerebras: llama-3.3-70b, llama3.1-8b, qwen-3-32b
                                         # ollama: any model you have pulled (e.g., llama3.2, mistral, codellama)

# Ollama Configuration (only needed if LLM_PROVIDER=ollama)
OLLAMA_BASE_URL=http://localhost:11434  # Ollama server URL (use http://ollama:11434 in Docker Compose)
OLLAMA_MODEL=llama3.2                    # Ollama model name
```

### Optional Authentication
```bash
# Access token for basic API authentication (optional - leave empty to disable)
ACCESS_TOKEN=your_secure_token_here

# When set, API requests must include header:
# Authorization: Bearer your_secure_token_here
```

## Key Architecture Patterns

### API Service Structure (`/api`)
```
api/
├── app/
│   ├── main.py                 # FastAPI application with lifespan events and CORS
│   ├── api/routes/             # API endpoints
│   │   ├── entries.py          # Entry CRUD, upload, chat endpoints
│   │   └── auth.py             # Bearer token authentication
│   ├── services/               # Business logic layer
│   │   ├── entry_service.py    # Entry management operations
│   │   ├── chat_service.py     # LLM chat integration (Groq/Cerebras)
│   │   └── s3_service.py       # S3 file operations
│   ├── models/
│   │   ├── entry.py            # SQLAlchemy Entry model
│   │   └── schemas.py          # Pydantic request/response models
│   ├── db/
│   │   └── database.py         # Database connection and session management
│   └── core/
│       └── config.py           # Environment configuration
├── alembic/                    # Database migrations (optional)
└── requirements.txt            # Python dependencies
```

### Worker Service Structure (`/worker`)
```
worker/
├── app/
│   ├── main.py                 # Worker entry point (checks WORKER_MODE env var)
│   ├── services/
│   │   ├── worker_service.py   # Base worker polling logic
│   │   ├── download_service.py # yt-dlp video/audio download
│   │   ├── asr_service.py      # Groq Whisper transcription
│   │   ├── audio_conversion_service.py  # FFmpeg audio format conversion
│   │   ├── audio_chunking_service.py    # Split large audio files
│   │   ├── database.py         # Database operations
│   │   └── s3_service.py       # S3 file operations
│   └── models/
│       └── entry.py            # SQLAlchemy Entry model (duplicate)
└── requirements.txt            # Python dependencies
```

### Frontend Structure (`/ui`)
```
ui/
├── src/
│   ├── App.tsx                 # Main app component with routing
│   ├── components/             # Reusable React components
│   ├── services/               # API client functions (axios)
│   └── types/                  # TypeScript type definitions
├── Dockerfile                  # Multi-stage build with Nginx
├── package.json                # Node dependencies
└── vite.config.ts              # Vite build configuration
```

### AI Provider Integration
The system uses dynamic provider initialization:

**ASR Service** (`/worker/app/services/asr_service.py`):
- Checks `ASR_PROVIDER` environment variable
- Supports: `groq` (Groq cloud API) or `whisper_asr` (self-hosted whisper-asr-webservice)
- Automatically converts audio to MP3 for compatibility
- Handles chunking for files >25MB (Groq only - whisper-asr has no inherent limit)

**LLM Service** (`/api/app/services/chat_service.py`):
- Checks `LLM_PROVIDER` environment variable
- Supports: `groq` (Groq client), `cerebras` (OpenAI-compatible client), or `ollama` (OpenAI-compatible client)
- Used for interactive chat with transcripts
- Context window includes full transcript + conversation history

**Ollama Integration**:
- Uses OpenAI-compatible API (`/v1/chat/completions` endpoint)
- Requires Ollama server running (default: http://localhost:11434)
- No API key required (uses dummy key "ollama")
- Supports any model you have pulled with `ollama pull <model>`
- Configure via `OLLAMA_BASE_URL` and `OLLAMA_MODEL` environment variables

### S3 Storage Pattern
Both API and workers use S3-compatible storage (`s3_service.py`):
- **Development**: MinIO running in Docker (compose.yml)
- **Production**: Vultr Object Storage or any S3-compatible provider
- **File Structure**: `{bucket}/{entry_id}/original.{ext}` and `{bucket}/{entry_id}/audio.mp3`
- **Presigned URLs**: Not currently used (direct S3 access from backend)

### Database Connection Pattern
All services construct `DATABASE_URL` from environment variables:
```python
DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
```
- **Development**: Uses `db` service in Docker Compose
- **Production**: Uses managed PostgreSQL (set `POSTGRES_HOST` to external host)
- **Automatic Migration**: Tables created on API startup via `Base.metadata.create_all()`

### Authentication Pattern
Optional Bearer token authentication (`/api/app/api/routes/auth.py`):
- If `ACCESS_TOKEN` environment variable is set: authentication required
- If `ACCESS_TOKEN` is empty: authentication disabled (development mode)
- Protected endpoints check for `Authorization: Bearer {token}` header
- Used for PoC protection, not full user management

## API Endpoints Reference

### Entry Management
- `POST /api/entries/upload` - Upload file (multipart/form-data)
- `POST /api/entries/url` - Create entry from URL (JSON: `{"url": "..."}`)
- `GET /api/entries/` - List entries with pagination (`?skip=0&limit=50`)
- `GET /api/entries/{id}` - Get entry details including transcript
- `DELETE /api/entries/{id}` - Delete entry and S3 files
- `PUT /api/entries/{id}/status` - Update entry status

### Chat & Analysis
- `POST /api/entries/{id}/chat` - Chat with transcript (JSON: `{"message": "..."}`)
  - Returns AI response using configured LLM provider
  - Maintains conversation context

### System
- `GET /api/` - API info
- `GET /api/health` - Health check
- `GET /api/docs` - Swagger UI
- `GET /api/redoc` - ReDoc documentation

## Common Troubleshooting

### Workers Not Processing Entries
```bash
# Check worker logs for errors
docker compose logs -f worker-download
docker compose logs -f worker-asr

# Verify database connectivity
docker compose exec worker-download python -c "from app.services.database import get_connection; print('DB OK')"

# Check S3 connectivity
docker compose exec worker-asr python -c "from app.services.s3_service import s3_client; s3_client.list_buckets()"
```

### YouTube Download Errors
- YouTube may require authentication cookies (see `docs/youtube-authentication.md`)
- Alternative: Use Vimeo, SoundCloud, or direct file uploads
- Error appears as "Sign in to confirm you're not a bot" in worker logs

### Audio Transcription Failures
- Groq API has 25MB file limit (100MB for dev tier with `GROQ_API_KEY`)
- Worker automatically chunks large files but may still fail
- Check ASR worker logs for API errors
- Verify `GROQ_API_KEY` is set correctly

### Database Migration Issues
- Tables are created automatically on API startup
- If using Alembic migrations: ensure versions match between code and database
- Reset development database: `docker compose down -v` (destroys data)

### Using Ollama for Local LLM
To use Ollama as your LLM provider:

1. **Install and start Ollama**:
   ```bash
   # Install Ollama (macOS/Linux)
   curl -fsSL https://ollama.com/install.sh | sh

   # Or download from https://ollama.com

   # Start Ollama service (if not auto-started)
   ollama serve
   ```

2. **Pull a model**:
   ```bash
   # Pull Llama 3.2 (3B - fast, good for development)
   ollama pull llama3.2

   # Or other models:
   ollama pull mistral
   ollama pull codellama
   ollama pull llama3.1
   ```

3. **Configure VoiceVault to use Ollama**:
   ```bash
   # In your .env file:
   LLM_PROVIDER=ollama
   OLLAMA_BASE_URL=http://localhost:11434  # or http://host.docker.internal:11434 from Docker
   OLLAMA_MODEL=llama3.2  # Must match a pulled model
   ```

4. **Docker networking**:
   - If running VoiceVault in Docker and Ollama on host: use `http://host.docker.internal:11434`
   - If running both in Docker Compose: add Ollama service and use `http://ollama:11434`
   - If running VoiceVault outside Docker: use `http://localhost:11434`

5. **Verify Ollama is accessible**:
   ```bash
   curl http://localhost:11434/api/tags  # Should list your pulled models
   ```

### Using whisper-asr-webservice for Local ASR
To use [whisper-asr-webservice](https://github.com/ahmetoner/whisper-asr-webservice) as your ASR provider:

1. **Run whisper-asr-webservice**:
   ```bash
   # Using Docker (recommended)
   docker run -d -p 9000:9000 -e ASR_MODEL=base onerahmet/openai-whisper-asr-webservice:latest

   # Available models: tiny, base, small, medium, large-v1, large-v2, large-v3
   # For GPU support:
   docker run -d --gpus all -p 9000:9000 -e ASR_MODEL=large-v3 onerahmet/openai-whisper-asr-webservice:latest-gpu
   ```

2. **Configure VoiceVault to use whisper-asr-webservice**:
   ```bash
   # In your .env file:
   ASR_PROVIDER=whisper_asr
   WHISPER_ASR_URL=http://localhost:9000  # or http://host.docker.internal:9000 from Docker
   ```

3. **Docker networking**:
   - If running VoiceVault in Docker and whisper-asr on host: use `http://host.docker.internal:9000`
   - If running both in Docker Compose: add whisper service and use `http://whisper:9000`
   - If running VoiceVault outside Docker: use `http://localhost:9000`

4. **Verify whisper-asr-webservice is accessible**:
   ```bash
   curl http://localhost:9000/  # Should return service info
   ```

5. **Key differences from Groq**:
   - No API key required (self-hosted)
   - No file size limits (Groq has 25MB limit requiring chunking)
   - Runs locally - no external API calls
   - Model quality depends on which Whisper model you run