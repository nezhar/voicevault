# Deployment

## Local Development

```bash
git clone https://github.com/your-username/voicevault.git
cd voicevault
cp .env.example .env
# Edit .env — set GROQ_API_KEY (or configure an alternative provider)
docker compose up --build
```

Services:
- Frontend: http://localhost:3000
- API: http://localhost:8000
- API docs: http://localhost:8000/docs
- MinIO console: http://localhost:9001

## Production

Production uses `compose.prod.yml`, which embeds code into images (no volume mounts) and expects externally managed database and S3 storage.

### 1. Prepare a VPS

Any Linux VPS with Docker and Docker Compose installed. Minimum: 2 vCPUs, 4 GB RAM.

### 2. Configure environment

```bash
cp .env.example .env
# Set production values:
# - POSTGRES_HOST → your managed database host
# - S3_ENDPOINT_URL → your S3-compatible provider
# - GROQ_API_KEY (or alternative provider keys)
# - ACCESS_TOKEN → a secure random string
```

### 3. Build and start

```bash
docker compose -f compose.prod.yml up -d --build
```

Check status:
```bash
docker compose -f compose.prod.yml ps
curl http://your-server:8000/health
```

### Using a Container Registry

Build locally and deploy to a server:

```bash
# On build machine
export REGISTRY=registry.example.com/voicevault/
export VERSION=v1.0.0

docker compose -f compose.prod.yml build
docker compose -f compose.prod.yml push

# On production server
docker compose -f compose.prod.yml pull
docker compose -f compose.prod.yml up -d
```

### Management commands

```bash
# View logs
docker compose -f compose.prod.yml logs -f

# Stop services
docker compose -f compose.prod.yml down

# Full cleanup (removes volumes — destroys data)
docker compose -f compose.prod.yml down --volumes --remove-orphans
```

## Provider Setup

For detailed setup walkthroughs for alternative providers, see [docs/configuration.md](configuration.md):

- [Using self-hosted Whisper ASR](configuration.md#using-self-hosted-whisper)
- [Using Ollama for local LLM inference](configuration.md#using-ollama)

## Troubleshooting

### Workers not processing entries

```bash
# Check worker logs
docker compose logs -f worker-download
docker compose logs -f worker-asr

# Verify database connectivity
docker compose exec worker-download python -c "from app.services.database import get_connection; print('DB OK')"

# Verify S3 connectivity
docker compose exec worker-asr python -c "from app.services.s3_service import s3_client; s3_client.list_buckets()"
```

### YouTube download errors

YouTube may block automated downloads. If you see "Sign in to confirm you're not a bot":

- Use Vimeo, SoundCloud, or direct file URLs instead
- Or configure YouTube cookies — see [youtube-authentication.md](youtube-authentication.md)

### Audio transcription failures

- Groq has a 25 MB chunk limit. The worker auto-chunks, but very large files may still fail. Check ASR worker logs.
- Verify your `GROQ_API_KEY` is set and valid.
- Consider switching to `ASR_PROVIDER=whisper_asr` for no file-size limits.

### Database issues

```bash
# Check database tables
docker compose exec db psql -U voicevault_user -d voicevault -c "\dt"

# Reset development database (destroys all data)
docker compose down -v
```

### File upload problems

```bash
# Check nginx configuration
docker compose exec ui cat /etc/nginx/conf.d/default.conf

# Check API file size limit
echo $MAX_FILE_SIZE
```

## Performance & Monitoring

```bash
# Health check
curl http://localhost:8000/health

# Resource usage
docker stats

# Service status
docker compose ps
```

Scale ASR workers for higher throughput by running multiple instances:
```bash
docker compose up -d --scale worker-asr=3
```

Use connection pooling and async queries for database performance. Add Redis for caching if needed at scale.
