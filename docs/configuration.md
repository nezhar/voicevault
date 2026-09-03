# Configuration Reference

Copy `.env.example` to `.env` and edit the values. All configuration is via environment variables.

## Database

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_HOST` | `db` | Database host (`db` for Docker Compose, external host for production) |
| `POSTGRES_PORT` | `5432` | Database port |
| `POSTGRES_DB` | `voicevault` | Database name |
| `POSTGRES_USER` | — | Database user |
| `POSTGRES_PASSWORD` | — | Database password |

## API

| Variable | Default | Description |
|----------|---------|-------------|
| `API_PORT` | `8000` | API server port |
| `ACCESS_TOKEN` | _(empty)_ | Bearer token for API auth. Leave empty to disable authentication. See [authentication.md](authentication.md). |
| `ADMIN_EMAILS` | _(empty)_ | Comma-separated admin email addresses. Used in OIDC mode only; requires an API restart to change. |
| `BACKFILL_METRICS_ON_STARTUP` | `true` | Fill in missing entry consumption metrics in the background at API startup. See below. |

### Startup metrics backfill

Entries created before consumption metrics were tracked have no size, duration,
or word count, which makes the admin dashboard totals a lower bound. On startup
the API fills them in, in a background thread — it never delays serving traffic
or the healthcheck, and it logs `Startup metrics backfill: …` when it has
examined anything.

It costs one S3 HEAD per entry with an unknown size, and entries whose metrics
can never be derived (no object in S3, a pasted transcript with no audio) are
re-examined on every start. That is bounded and cheap for most deployments, but
if it is not for yours — a very large library, metered object-storage requests,
or an API that restarts often — set `BACKFILL_METRICS_ON_STARTUP=false` and run
the script by hand instead:

```bash
docker compose exec api python -m app.scripts.backfill_entry_metrics --dry-run
docker compose exec api python -m app.scripts.backfill_entry_metrics
```

Only one process backfills at a time: the pass takes a PostgreSQL advisory
lock, so extra API replicas log that they skipped it rather than repeating the
same S3 requests.

### Admin dashboard access

Who reaches the read-only `/admin` dashboard and the `/api/admin` endpoints
depends on the auth mode:

| `AUTH_MODE` | Who is admin |
|-------------|--------------|
| `none` | The shared local user — that is, anyone who can reach the API |
| `token` | The shared local user, so whoever holds `ACCESS_TOKEN` |
| `oidc` | Signed-in users whose email is listed in `ADMIN_EMAILS` |

In `none` and `token` mode there is exactly one user and no `ADMIN_EMAILS` to
consult. Admin is granted there because the dashboard only aggregates data the
caller can already read in full through `/api/entries` — withholding it would
protect nothing. Note what that means for `none` mode: an API exposed without
authentication exposes the dashboard too, along with every transcript.

In OIDC mode:

```env
ADMIN_EMAILS=ada@corp.com,bob@corp.com
```

Addresses are matched case-insensitively and surrounding whitespace is ignored,
so `ADMIN_EMAILS=" Ada@Corp.com , bob@corp.com"` is valid. Two properties are
worth stating explicitly:

- **Non-admins get `404`, not `403`** — they should not learn the area exists.
  A database that once ran in OIDC mode and was switched back to `token` keeps
  its real user rows, and those are not admins in the new mode; only the shared
  local account is.
- **Changing it requires an API restart.** The value is read from the
  environment at startup; adding or removing an admin takes effect only after
  `docker compose restart api`.

## ASR Provider

| Variable | Default | Description |
|----------|---------|-------------|
| `ASR_PROVIDER` | `groq` | ASR backend: `groq` or `whisper_asr` |
| `ASR_MODEL` | `whisper-large-v3-turbo` | Model name (Groq only). Options: `whisper-large-v3`, `whisper-large-v3-turbo` |
| `GROQ_API_KEY` | — | Required when `ASR_PROVIDER=groq` |
| `WHISPER_ASR_URL` | `http://localhost:9000` | Required when `ASR_PROVIDER=whisper_asr` |

### Using Groq (default)

Sign up at [console.groq.com](https://console.groq.com) to get an API key. Set `ASR_PROVIDER=groq` and `GROQ_API_KEY`.

Groq imposes a 25 MB file size limit (100 MB on the dev tier). The ASR worker automatically chunks larger files.

### Using self-hosted Whisper

Run [whisper-asr-webservice](https://github.com/ahmetoner/whisper-asr-webservice):

```bash
docker run -d -p 9000:9000 -e ASR_MODEL=base onerahmet/openai-whisper-asr-webservice:latest
```

Set `ASR_PROVIDER=whisper_asr` and `WHISPER_ASR_URL=http://localhost:9000` (or `http://host.docker.internal:9000` when running VoiceVault inside Docker).

No API key is required. No file size limit.

## LLM Provider

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `groq` | LLM backend: `groq`, `cerebras`, `ollama`, or `nebius` |
| `LLM_MODEL` | `llama-3.3-70b-versatile` | Model name (provider-specific) |
| `GROQ_API_KEY` | — | Required when `LLM_PROVIDER=groq` |
| `CEREBRAS_API_KEY` | — | Required when `LLM_PROVIDER=cerebras` |
| `NEBIUS_API_KEY` | — | Required when `LLM_PROVIDER=nebius` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Required when `LLM_PROVIDER=ollama` |
| `OLLAMA_MODEL` | `llama3.2` | Ollama model name |

### Model options

**Groq:** `llama-3.3-70b-versatile`, `llama-3.1-70b-versatile`

**Cerebras:** `llama-3.3-70b`, `llama3.1-8b`, `qwen-3-32b`

**Nebius:** `meta-llama/Meta-Llama-3.1-70B-Instruct`

**Ollama:** any model you have pulled locally (e.g. `llama3.2`, `mistral`, `codellama`)

### Using Ollama

Install Ollama from [ollama.com](https://ollama.com), pull a model, and configure:

```bash
ollama pull llama3.2
```

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434   # or http://host.docker.internal:11434 from Docker
OLLAMA_MODEL=llama3.2
```

Verify the server is accessible:
```bash
curl http://localhost:11434/api/tags
```

## S3 Storage

| Variable | Default | Description |
|----------|---------|-------------|
| `S3_ENDPOINT_URL` | — | S3-compatible endpoint URL |
| `S3_ACCESS_KEY` | — | S3 access key |
| `S3_SECRET_KEY` | — | S3 secret key |
| `S3_BUCKET_NAME` | `voicevault` | Bucket name |
| `MINIO_PORT` | `9000` | Host port for the local MinIO API (`compose.yml` only) |
| `MINIO_CONSOLE_PORT` | `9001` | Host port for the MinIO console (`compose.yml` only) |

Works with any S3-compatible provider. Local development uses MinIO (included in `compose.yml`):

```env
S3_ENDPOINT_URL=http://minio:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET_NAME=voicevault
```

### Port conflicts with MinIO

Port 9000 is crowded — whisper-asr-webservice (see the ASR section above),
Portainer, and php-fpm all default to it. If startup fails with
`failed to bind host port 0.0.0.0:9000`, find the owner and either stop it or
move MinIO:

```bash
sudo ss -ltnp 'sport = :9000'
docker ps --filter publish=9000     # a stale stack of your own?
```

`MINIO_PORT` and `MINIO_CONSOLE_PORT` are a **pair — move both**. They default
to adjacent ports, so setting only `MINIO_PORT=9001` makes MinIO collide with
its own console and Docker reports `port is already allocated`:

```env
MINIO_PORT=9010
MINIO_CONSOLE_PORT=9011
```

**Leave `S3_ENDPOINT_URL` as `http://minio:9000`.** These variables change host
access only; the API and workers reach MinIO by service name inside the Docker
network, where the port is always 9000. Pointing `S3_ENDPOINT_URL` at the new
host port breaks every upload with a connection error that looks unrelated.

Provider examples:
```env
# AWS S3
S3_ENDPOINT_URL=https://s3.amazonaws.com

# DigitalOcean Spaces
S3_ENDPOINT_URL=https://nyc3.digitaloceanspaces.com

# Vultr Object Storage
S3_ENDPOINT_URL=https://ewr1.vultrobjects.com
```

## Processing

| Variable | Default | Description |
|----------|---------|-------------|
| `PROCESSING_TIMEOUT` | `3600` | Worker processing timeout in seconds |
| `WORKER_INTERVAL` | `10` | Seconds between worker poll cycles |
| `BATCH_SIZE` | `5` | Entries processed per worker cycle |
| `MAX_FILE_SIZE` | `26214400` | Maximum chunk size (bytes) sent to the Groq ASR API (default 25 MB). Increase only if your Groq tier supports larger uploads. |
