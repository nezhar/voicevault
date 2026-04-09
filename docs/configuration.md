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

Works with any S3-compatible provider. Local development uses MinIO (included in `compose.yml`):

```env
S3_ENDPOINT_URL=http://minio:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET_NAME=voicevault
```

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
