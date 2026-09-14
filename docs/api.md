# API Reference

Base URL: `http://localhost:8000` (development)

Interactive documentation is available at `/api/docs` (Swagger UI) and `/api/redoc`.

Every timestamp in a response is UTC and carries an explicit `Z`, e.g.
`"2026-10-04T12:00:00Z"`. Inbound timestamps may carry any offset; they are
converted to UTC on the way in.

## Authentication

Authentication is optional. When `ACCESS_TOKEN` is set, all API requests must include:

```
Authorization: Bearer <token>
```


User PATs use the same header and start with `vvpat_`. They are scoped and may
be used in OIDC or token mode. See [authentication.md](authentication.md) for
the permission matrix.

### Personal access tokens

- `POST /api/auth/pats` — create a token; accepts `name`, `permissions`, and an
  optional ISO-8601 `expires_at`; returns the raw `token` once.
- `GET /api/auth/pats` — list the current user's token metadata, never secrets.
- `PATCH /api/auth/pats/{token_id}` — rename an owned token and/or change its
  expiry. Send only the fields to change; `"expires_at": null` removes the
  expiry. Only active tokens can be edited (`409` for expired or revoked ones)
  so an expired credential cannot be revived. Permissions are immutable.
- `DELETE /api/auth/pats/{token_id}` — revoke an owned token.

Tokens can only be created by and for the signed-in user; there is no way to
mint a token on someone else's behalf. Administrators have interactive-only,
cross-user review and revocation endpoints:

- `GET /api/admin/pat-users` — server-side user search, returning at most 50 matches.
- `GET /api/admin/pats` — paginated token metadata; supports `page`, `per_page`,
  `user_id`, token `name`, and `status` (`active`, `expired`, or `revoked`).
- `DELETE /api/admin/pats/{token_id}` — revoke any user's token.

These management endpoints require interactive authentication and return `403`
when called with a PAT. `expires_at`, wherever it is accepted, must lie in the
future (`422` otherwise); timezone-aware values are stored as UTC.
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
    "created_at": "2026-08-20T10:00:00Z",
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

## Admin

Platform statistics for the `/admin` dashboard, plus account activation and the
cross-user token management listed under *Personal access tokens*. Who may call
them depends on the auth mode: in `none` and `token` mode the single shared local
user is the admin, so they are available without extra configuration. In `oidc`
mode they are restricted to users listed in the `ADMIN_EMAILS` environment
variable, and changing that list requires an API restart. Callers who are not
admins receive `404` rather than `403`, so the area stays undiscoverable; this
holds for a non-admin's PAT too, whatever its scopes. The read endpoints accept
an admin's PAT carrying `admin:read`; the mutations require an interactive login.

### Platform statistics
`GET /api/admin/stats`

System-wide totals. User counts exclude the synthetic system user.
`entries_total` includes archived entries; `entries_archived` is reported as a
subset rather than subtracted.

**Response:**
```json
{
  "users_total": 12,
  "users_active_30d": 8,
  "users_new_30d": 2,
  "entries_total": 340,
  "entries_archived": 15,
  "entries_by_status": { "NEW": 1, "IN_PROGRESS": 2, "READY": 330, "COMPLETE": 5, "ERROR": 2 },
  "entries_by_source": { "upload": 200, "url": 140 },
  "storage_bytes_total": 10737418240,
  "duration_seconds_total": 432000.0,
  "words_total": 1250000,
  "projects_total": 6,
  "entries_missing_metrics": 0,
  "entries_unassigned": 0
}
```

`entries_missing_metrics` counts entries with no recorded size, duration, or
word count. When it is non-zero the totals are a lower bound. The API backfills
them in the background on every startup, so restarting it normally clears this;
some entries can never be completed (no object in S3, or a pasted transcript
with no audio) and keep counting. See the backfill notes in
[CLAUDE.md](../CLAUDE.md) for running it by hand
(`python -m app.scripts.backfill_entry_metrics`).

`entries_unassigned` counts entries with no owner (`user_id IS NULL`). They are
included in `entries_total` but belong to no row in `/api/admin/users`, so when
it is non-zero the per-user breakdown will not add up to the system totals. This
happens on OIDC deployments where `INITIAL_OWNER_EMAIL` was never set, leaving
pre-existing entries unclaimed.

---

### Per-user consumption
`GET /api/admin/users`

Per-user breakdown. Users with no entries still appear. The system user is
excluded unless it still owns entries, in which case it is listed with
`is_system: true` so the per-user rows reconcile with `entries_total`.

**Query params:** `skip` (default 0), `limit` (default 50, max 200),
`sort` (default `storage_bytes`), `order` (`asc` or `desc`, default `desc`).

`sort` must be one of `entry_count`, `storage_bytes`, `duration_seconds`,
`word_count`, `email`, `created_at`. Any other value returns `400` — sort keys
are resolved through a whitelist and never interpolated into SQL.

**Response:**
```json
{
  "total": 12,
  "users": [
    {
      "id": "b21d...",
      "email": "ada@corp.com",
      "display_name": "Ada Lovelace",
      "is_admin": true,
      "is_system": false,
      "created_at": "2026-01-15T09:30:00Z",
      "last_login_at": "2026-08-20T08:12:00Z",
      "entry_count": 42,
      "storage_bytes": 1073741824,
      "duration_seconds": 54000.0,
      "word_count": 180000,
      "error_count": 1,
      "project_count": 3
    }
  ]
}
```

---

## System

### Health check
`GET /health`

Returns `200 OK` when the service is running.

### API info
`GET /`

Returns API version and status.

## MCP access

An optional PAT-authenticated MCP endpoint is available at `/mcp`.
See [MCP setup, tools, and client examples](mcp.md).
