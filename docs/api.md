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

## Project Access Requests

A project is reachable at the permalink `/projects/{project_id}`. Anyone signed
in may look it up; joining it requires an owner's approval. These endpoints
exist only when `AUTH_MODE=oidc` — in `none` and `token` mode they return `404`,
because those modes share a single local user. `/preview` is the exception and
works in every mode.

### Preview a project
`GET /api/projects/{project_id}/preview`

Permalink landing data. Unlike `GET /api/projects/{project_id}`, this does not
return `404` for non-members: it deliberately reveals the name and owners to
whoever holds the project UUID.

**Response:**
```json
{
  "id": "8f3c1d2e-4b5a-4c6d-9e8f-0a1b2c3d4e5f",
  "name": "Q3 Customer Calls",
  "owners": [{ "display_name": "Ada Lovelace", "email": "ada@example.com" }],
  "my_role": null,
  "request_status": null,
  "request_id": null,
  "can_request": true
}
```

`404` only when no project with that id exists.

---

### Request access
`POST /api/projects/{project_id}/access-requests`

Ask the project's owners for membership. A previously denied request is reopened
rather than duplicated, so one user never produces more than one row.

**Request:**
```json
{ "message": "I'm joining the QBR team" }
```

`message` is optional and capped at 500 characters.

**Response:** Access request object with `status: pending`. Returns `409` when
the caller is already a member.

---

### Cancel your request
`DELETE /api/projects/{project_id}/access-requests/{request_id}`

Withdraw your own pending request. `404` if the request is not yours, `409` if
an owner has already decided it.

**Response:**
```json
{ "message": "Access request cancelled" }
```

---

### List access requests
`GET /api/projects/{project_id}/access-requests?status=pending`

Owner only. `status` accepts `pending` (default), `approved`, `denied`, or `all`.

**Response:**
```json
[
  {
    "id": "1f0e...",
    "project_id": "8f3c...",
    "user_id": "b21d...",
    "email": "bob@example.com",
    "display_name": "Bob Miller",
    "status": "pending",
    "message": "I'm joining the QBR team",
    "created_at": "2026-08-20T10:00:00",
    "decided_at": null,
    "decided_by_name": null
  }
]
```

---

### Approve a request
`POST /api/projects/{project_id}/access-requests/{request_id}/approve`

Owner only. Creates the membership with the chosen role and marks the request
approved. Calling it again on an approved request is a no-op.

**Request:**
```json
{ "role": "viewer" }
```

`role` defaults to `viewer`, the lowest role.

**Response:** Access request object with `status: approved`.

---

### Deny a request
`POST /api/projects/{project_id}/access-requests/{request_id}/deny`

Owner only. Keeps the row with `status: denied` plus the decider and timestamp.
The requester may ask again later.

**Response:** Access request object with `status: denied`.

---

## System

### Health check
`GET /health`

Returns `200 OK` when the service is running.

### API info
`GET /`

Returns API version and status.
