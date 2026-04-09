# API Reference

Base URL: `http://localhost:8000` (development)

Interactive documentation is available at `/api/docs` (Swagger UI) and `/api/redoc`.

## Authentication

Authentication is optional. When `ACCESS_TOKEN` is set, all API requests must include:

```
Authorization: Bearer <token>
```

See [authentication.md](authentication.md) for details.

## Entries

### Upload a file
`POST /api/entries/upload`

Multipart form upload. Accepts audio and video files.

**Request:** `multipart/form-data` with `title` (string, required) and `file` fields.

**Response:** Entry object with `id` and `status: NEW`.

---

### Submit a URL
`POST /api/entries/url`

Submit a URL for download and transcription (YouTube, Vimeo, SoundCloud, direct links).

**Request:**
```json
{ "title": "My Recording", "source_url": "https://example.com/audio.mp3" }
```

**Response:** Entry object with `status: NEW`.

---

### Create from transcript
`POST /api/entries/transcript`

Create an entry directly from an existing transcript (no audio processing required).

**Request:**
```json
{ "title": "My Meeting", "transcript": "Full transcript text here..." }
```

**Response:** Entry object with `status: READY`.

---

### List entries
`GET /api/entries/`

Returns all entries, newest first.

**Query params:** `page` (default 1), `per_page` (default 12), `search` (optional), `archived` (default false).

**Response:** Paginated object:
```json
{
  "entries": [...],
  "total": 42,
  "page": 1,
  "per_page": 12,
  "total_pages": 4,
  "has_next": true,
  "has_previous": false
}
```

---

### Get entry
`GET /api/entries/{id}`

Returns a single entry including transcript and summary if available.

**Response fields:** `id`, `title`, `source_type`, `source_url`, `filename`, `status`, `archived`, `transcript`, `summary`, `error_message`, `created_at`, `updated_at`.

---

### Update status
`PUT /api/entries/{id}/status`

**Request:**
```json
{ "status": "COMPLETE" }
```

Valid statuses: `NEW`, `IN_PROGRESS`, `READY`, `COMPLETE`, `ERROR`.

---

### Archive / unarchive
`PUT /api/entries/{id}/archive`

**Request:**
```json
{ "archived": true }
```

Archived entries are hidden from the default list view.

---

### Delete entry
`DELETE /api/entries/{id}`

Deletes the entry and its associated S3 files.

**Response:**
```json
{ "message": "Entry deleted successfully" }
```

---

## Chat & Analysis

### Chat with a transcript
`POST /api/entries/{id}/chat`

Send a message and receive an AI response in the context of the entry's transcript. The entry must have `status: READY`.

**Request:**
```json
{
  "message": "What were the key decisions made?",
  "conversation_history": [
    { "role": "user", "content": "Previous question" },
    { "role": "assistant", "content": "Previous answer" }
  ]
}
```

`conversation_history` is optional. Each item requires `role` (`"user"` or `"assistant"`) and `content`.

**Response:**
```json
{ "message": "...", "timestamp": "2024-01-01T00:00:00Z" }
```

---

### Generate a summary
`POST /api/entries/{id}/summary`

Generate an AI summary of the entry transcript. The entry must have `status: READY`. The generated summary is also saved back to the entry.

**Response:**
```json
{ "summary": "...", "timestamp": "2024-01-01T00:00:00Z" }
```

---

## Prompt Templates

Prompt templates are reusable system-prompt snippets for customising LLM behaviour.

### List templates
`GET /api/prompt-templates/`

**Query param:** `active_only=true` to filter inactive templates.

**Response:** Array of template objects.

---

### Create template
`POST /api/prompt-templates/`

**Request:**
```json
{
  "label": "Meeting Summary",
  "preview_text": "Extracts action items and decisions",
  "body_markdown": "Extract action items and decisions from this meeting transcript.",
  "sort_order": 0,
  "is_active": true
}
```

`label` and `body_markdown` are required. `preview_text` (max 512 chars), `sort_order` (default 0), and `is_active` (default true) are optional.

**Response fields:** `id`, `label`, `preview_text`, `body_markdown`, `sort_order`, `is_active`, `created_at`, `updated_at`.

---

### Update template
`PUT /api/prompt-templates/{template_id}`

Partial update — include only the fields to change. All fields are optional.

**Request:**
```json
{ "label": "Updated Label", "is_active": false }
```

---

### Delete template
`DELETE /api/prompt-templates/{template_id}`

**Response:**
```json
{ "message": "Prompt template deleted successfully" }
```

---

## System

### Health check
`GET /health`

Returns `200 OK` when the service is running.

### API info
`GET /`

Returns API version and status.
