# Architecture

VoiceVault is a multi-service application composed of five containerised services.

## System Overview

```mermaid
graph TB
    subgraph "User Interface"
        UI[React + TypeScript]
    end

    subgraph "API Layer"
        API[FastAPI]
    end

    subgraph "Workers"
        DW[Download Worker]
        AW[ASR Worker]
    end

    subgraph "AI Providers"
        ASR[ASR Provider]
        LLM[LLM Provider]
    end

    subgraph "Data"
        DB[(PostgreSQL)]
        S3[(S3 Storage)]
    end

    UI --> API
    API --> DB
    API --> S3
    API --> LLM
    DW --> DB
    DW --> S3
    AW --> DB
    AW --> S3
    AW --> ASR
```

## Services

### UI (`/ui`)
React 18 + TypeScript + Vite frontend served by Nginx on port 3000. Provides drag-and-drop file upload, real-time entry status, interactive chat, and prompt template management.

### API (`/api`)
FastAPI backend on port 8000. Handles entry CRUD, file uploads, chat, prompt templates, and optional Bearer token authentication. Database tables are created automatically on startup via `Base.metadata.create_all()` — no manual migrations needed for development.

### Download Worker (`/worker`, `WORKER_MODE=download`)
Polls for entries with `entry_type=url` and `status=NEW`. Downloads audio/video via yt-dlp, extracts audio with FFmpeg, uploads to S3, and advances status to `IN_PROGRESS`.

### ASR Worker (`/worker`, `WORKER_MODE=asr`)
Polls for entries with `status=IN_PROGRESS`. Fetches audio from S3, transcribes via the configured ASR provider, stores the transcript, and advances status to `READY`.

### Database
PostgreSQL 17. Stores entry metadata, transcripts, chat history, and prompt templates.

### Object Storage
Any S3-compatible provider. Stores original uploads and processed audio files. MinIO is used locally via Docker Compose.

## Entry Status Workflow

```
NEW → IN_PROGRESS → READY → COMPLETE
          ↓
        ERROR
```

- **NEW** — entry created (file uploaded or URL submitted)
- **IN_PROGRESS** — audio downloaded and stored, queued for ASR
- **READY** — transcript available, entry can be chatted with
- **COMPLETE** — user has marked the entry as finished
- **ERROR** — processing failed; the `error_message` field contains details

## Processing Sequence

### File upload
```mermaid
sequenceDiagram
    participant U as User
    participant API as API
    participant S3 as S3
    participant AW as ASR Worker
    participant ASR as ASR Provider
    participant DB as Database

    U->>API: POST /api/entries/upload
    API->>DB: Create entry (status: NEW)
    API->>S3: Store file
    API->>DB: Update entry with file path
    AW->>DB: Poll for NEW upload entries
    AW->>S3: Fetch audio
    AW->>ASR: Transcribe
    ASR->>AW: Transcript
    AW->>DB: Store transcript (status: READY)
```

### URL submission
```mermaid
sequenceDiagram
    participant U as User
    participant API as API
    participant DW as Download Worker
    participant S3 as S3
    participant AW as ASR Worker
    participant ASR as ASR Provider
    participant DB as Database

    U->>API: POST /api/entries/url
    API->>DB: Create entry (status: NEW)
    DW->>DB: Poll for NEW URL entries
    DW->>DW: Download + extract audio
    DW->>S3: Store audio
    DW->>DB: Update status (IN_PROGRESS)
    AW->>DB: Poll for IN_PROGRESS entries
    AW->>S3: Fetch audio
    AW->>ASR: Transcribe
    ASR->>AW: Transcript
    AW->>DB: Store transcript (status: READY)
```

## Project Structure

```
voicevault/
├── api/                    # FastAPI backend
│   ├── app/
│   │   ├── api/routes/     # Endpoints (entries, prompt_templates, auth)
│   │   ├── core/           # Config, authentication
│   │   ├── db/             # Database connection
│   │   ├── models/         # SQLAlchemy models + Pydantic schemas
│   │   │   ├── entry.py
│   │   │   └── prompt_template.py
│   │   └── services/       # Business logic
│   │       ├── entry_service.py
│   │       ├── chat_service.py
│   │       ├── prompt_template_service.py
│   │       └── s3_service.py
│   ├── alembic/            # Database migrations
│   └── requirements.txt
├── ui/                     # React frontend
│   └── src/
│       ├── components/
│       ├── services/       # API client
│       └── types/
├── worker/                 # Shared worker codebase
│   └── app/
│       ├── services/       # download, asr, audio conversion, S3
│       └── models/
├── docs/                   # Documentation
├── compose.yml             # Local development
├── compose.prod.yml        # Production
└── .env.example            # Environment template
```
