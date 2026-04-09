# README Redesign — Design Spec

**Date:** 2026-04-09
**Status:** Approved

## Goal

Simplify and modernise the VoiceVault README. Remove hackathon-specific and Vultr-specific framing. Move detailed content to dedicated docs. Present VoiceVault as a provider-agnostic, open voice intelligence platform.

## Constraints

- Single mention of hackathon origin (no RAISE2025 or Vultr Track references beyond that)
- No provider badges or Vultr badges
- Groq is one option, not the default identity of the platform
- Deployment instructions must be provider-agnostic (generic VPS)
- Detailed sections move to `docs/` with short inline references in the README

## README Structure

### 1. Header
- Title + one-line pitch: *"Enterprise voice intelligence platform — transcribe, analyse, and chat with your voice conversations."*
- Badges: MIT license only
- One-sentence origin note: *"Started as a hackathon project, now developed as an open platform."*

### 2. Demo
- Embedded `screencast.mp4` using GitHub's native video support (`screencast.mp4` is already present in the repository root)

### 3. How It Works
- 3–4 sentences describing the pipeline: upload audio/video → ASR provider transcribes → LLM provider analyses → explore via dashboard and chat
- Single minimal Mermaid flow diagram: `Audio/Video → ASR Provider → LLM Provider → Dashboard` — node labels must use generic provider names, not Groq-specific labels (i.e. replace existing `Groq Transcription` / `Llama Analysis` nodes)
- Link to `docs/architecture.md` for full component breakdown and diagrams

### 4. Features
- Concise bullet list (no emojis, no marketing statistics)
- Highlights: multi-format input, pluggable ASR provider, pluggable LLM provider, interactive chat, background processing pipeline, S3-compatible storage, optional Bearer token auth

### 5. Quick Start
- Prerequisites: Docker, Docker Compose, Git
- Three steps: clone → copy and edit `.env` → `docker compose up --build`
- Access URLs after start (UI, API, docs, MinIO console)
- Link to `docs/deployment.md` for production setup

### 6. Configuration
- Short table of the most important env vars: `ASR_PROVIDER`, `ASR_MODEL`, `LLM_PROVIDER`, `LLM_MODEL`, `ACCESS_TOKEN` (optional Bearer auth, empty by default), S3 variables, and a generic note that provider-specific API keys (e.g. `GROQ_API_KEY`) are covered in `docs/configuration.md`
- Note that both ASR and LLM providers are pluggable and API keys are provider-dependent
- Link to `.env.example` and `docs/configuration.md` for full reference

### 7. API
- One-line description per endpoint group: Entries (upload, list, get, delete, status), Chat & Analysis (chat, summary), Prompt Templates (list, create, update, delete), System (health, docs)
- Link to `docs/api.md` and the live Swagger UI at `/api/docs`

### 8. Tech Stack
- Compact table with columns: Layer | Technology
- Rows: Frontend (React + TypeScript + Vite), Backend (FastAPI + SQLAlchemy), Workers (Python, yt-dlp, FFmpeg), ASR Providers (Groq (Whisper), self-hosted Whisper), LLM Providers (Groq, Cerebras, Ollama), Storage (PostgreSQL, S3-compatible), Infrastructure (Docker Compose)

### 9. Contributing
- Brief: follow existing code patterns, use conventional commits
- Open issues and pull requests via GitHub Issues / Pull Requests

### 10. License
- MIT, one line

## Docs to Create / Update

| File | Content |
|------|---------|
| `docs/architecture.md` | Full system diagram, component descriptions, entry status workflow, worker architecture |
| `docs/deployment.md` | Production deployment on a generic VPS, compose.prod.yml usage, container registry workflow (use generic `registry.example.com/` — no Vultr-specific hostnames), troubleshooting (workers, YouTube errors, transcription failures, DB issues), Ollama setup walkthrough, whisper-asr-webservice setup walkthrough, performance and monitoring guidance |
| `docs/api.md` | Full API endpoint reference (moved from README). Must include: Entries, Chat & Analysis (chat + summary — both implemented), Prompt Templates, System. |
| `docs/configuration.md` | Full environment variable reference (moved from README). Do not carry forward `HUGGINGFACE_TOKEN` — it has no active backend usage. |

Existing docs to keep unchanged: `docs/authentication.md`, `docs/youtube-authentication.md`, `docs/nginx-proxy.conf`, `docs/nginx-setup.md`.

Internal planning artefacts to leave in place but not reference from the README: `docs/concept.md`, `docs/contraint.md`, `docs/implementation.md`, `docs/task.md`. These are not to be updated or reconciled with the new docs — the four new docs files (`architecture.md`, `deployment.md`, `api.md`, `configuration.md`) are the canonical developer reference going forward.

Note: `screencast.mp4` is already present in the repository root and can be embedded immediately.

`HUGGINGFACE_TOKEN` has no active backend usage and must be removed from: the new README, `docs/configuration.md`, `.env.example`, `api/.env.example`, `compose.yml`, and `compose.prod.yml` (where it is passed as a dead container env var). All six locations must be cleaned up as part of this work.

The Vultr-specific S3 comment in `.env.example` (`# Vultr: https://ewr1.vultrobjects.com`) may be retained as one example among peers (AWS, DigitalOcean), but should be reordered so it is not listed first — consistent with the provider-agnostic framing.

## What Is Removed from README

- `## Hackathon Requirements (RAISE2025 - Vultr Track)` section
- `## Hackathon Context` footer section
- All Vultr-specific env var examples (registry URLs, managed DB hostnames)
- Vultr badge
- Groq badge
- Success metrics section
- Detailed roadmap (phases with checkboxes)
- Full sequence diagrams (move to `docs/architecture.md`)
- Duplicate deployment instructions (consolidate to Quick Start + link)
- Performance optimisation and monitoring sub-sections in Troubleshooting (move to `docs/deployment.md`)
- Full Troubleshooting section from the README — move to `docs/deployment.md` (covers workers not processing, YouTube errors, transcription failures, database issues, Ollama setup, whisper-asr-webservice setup). The README will not have a Troubleshooting section; users are directed to `docs/deployment.md`.
- Explicit `alembic upgrade head` step from Quick Start (tables are auto-created on API startup via `Base.metadata.create_all()` — no manual migration needed for development)
- `POST /api/entries/{id}/summary` was previously labelled "planned" in the README — it is fully implemented and must be included in `docs/api.md`

## Provider-Agnostic Framing

- Pipeline described as "ASR Provider" and "LLM Provider" throughout
- Supported options listed as configuration choices, not as the platform identity:
  - ASR: Groq Whisper, self-hosted whisper-asr-webservice
  - LLM: Groq, Cerebras, Ollama
- S3 storage described as "any S3-compatible provider" with MinIO for local dev
