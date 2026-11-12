# Model Context Protocol (MCP)

VoiceVault exposes an optional, PAT-authenticated Streamable HTTP endpoint at
`/mcp` (no trailing slash). It wraps the existing REST routes in the API
process; workers, storage, ownership rules, and project permissions are shared.

## Enable and connect

Set these variables in your deployment environment, then rebuild/recreate the API
and UI containers to pick up the dependencies and proxy configuration:

```dotenv
MCP_ENABLED=true
PUBLIC_BASE_URL=https://voicevault.example.com
# Additional Host headers, if clients use another hostname or a local port:
MCP_ALLOWED_HOSTS=localhost,localhost:*,127.0.0.1,127.0.0.1:*
# Include browser origins that will connect directly to MCP, when needed:
CORS_ORIGINS=https://voicevault.example.com,http://localhost:3000
```

`PUBLIC_BASE_URL`'s host (including its port, when specified) is automatically
allowed. `MCP_ALLOWED_HOSTS` is a comma-separated list of hosts, not URLs. The
server validates Host and any supplied Origin header. Invalid hosts receive 421;
invalid origins receive 403. Requests without Origin are supported for native
clients. Use HTTPS for remote connections. Local development can use HTTP.

Create a PAT using the existing Personal Access Tokens page after signing in
through OIDC (or the shared-token mode). Grant only the permissions needed below.
The page shows a short REST/MCP guide with the new token filled in (an `mcpServers`
JSON snippet and a `claude mcp add` command), and keeps the same guide with a
placeholder under "How to use a token". It reads `mcp_enabled` from
`GET /api/auth/config` and warns when MCP is switched off. Configure your MCP
client with:

- Transport: **Streamable HTTP**
- URL: `https://voicevault.example.com/mcp`
- Request header: `Authorization: Bearer vvpat_<your-token>`

Every MCP request, including discovery, requires a PAT. Browser session cookies,
the legacy shared bearer token, and anonymous access are not accepted, even when
`AUTH_MODE=none`. Disabling MCP leaves `/mcp` unavailable. REST auth modes are
unchanged. PAT expiry, revocation, and disabled owners take effect on subsequent
requests; operations already running are not rolled back.

This release uses **custom PAT authentication**, not the MCP OAuth authorization
flow. OIDC remains the interactive login used to manage PATs. Clients must support
custom Authorization headers; OAuth-only clients need a future OAuth integration.
No OAuth metadata or token exchange is advertised. Credentials are dispatched
only within the same VoiceVault ASGI application, never to a configurable upstream.

## Tools and permissions

All paths below are relative to `/api`. Scope checks and object-level access
checks run in the REST routes for every operation. Tool discovery is a static
catalog; discovering a tool does not grant permission to execute it.

| Tool | REST operation | PAT scope |
|---|---|---|
| `list_entries` | `GET /entries/` | `entries:read` |
| `get_entry` | `GET /entries/{id}` | `entries:read` |
| `read_entry_text` | `GET /entries/{id}`, paged transcript/summary projection | `entries:read` |
| `create_entry_from_url` | `POST /entries/url` | `entries:write` |
| `create_entry_from_transcript` | `POST /entries/transcript` | `entries:write` |
| `upload_file` | `POST /entries/upload` (inline) or `POST /entries/upload-sessions` (link) | `entries:write` |
| `get_upload_status` | `GET /entries/upload-sessions/{id}`, then `GET /entries/{id}` | `entries:read` |
| `update_entry_metadata` | `PUT /entries/{id}/metadata` | `entries:write` |
| `update_entry_status` | `PUT /entries/{id}/status` | `entries:write` |
| `set_entry_archived` | `PUT /entries/{id}/archive` | `entries:write` |
| `move_entry_to_project` | `PUT /entries/{id}/project` | `entries:write` |
| `delete_entry` | `DELETE /entries/{id}` | `entries:write` |
| `chat_with_entry` | `POST /entries/{id}/chat` | `entries:read` |
| `generate_entry_summary` | `POST /entries/{id}/summary` | `entries:write` |
| `list_projects` | `GET /projects/` | `projects:read` |
| `get_project` | `GET /projects/{id}` | `projects:read` |
| `list_prompt_templates` | `GET /prompt-templates/` | `templates:read` |

Write scopes do not imply read scopes. Grant both when a client needs to create
and then read entries. A project viewer cannot modify another user's entry even
with `entries:write`; only the entry owner can permanently delete it. Summary
generation saves/replaces a summary and requires editor access. Chat needs only
viewer access. Both invoke the configured LLM and can incur provider charges.

Tools have JSON input/output schemas, structured results, and side-effect
annotations. `create_entry_from_transcript`, `update_entry_metadata`, and
`chat_with_entry` take their REST payload in a `data` object. Send objects as JSON
objects, not JSON-encoded strings. String arguments remain literal, including
search terms such as `"null"` or `"[]"`. For example:

```json
{
  "name": "create_entry_from_transcript",
  "arguments": {
    "data": {"title": "Team meeting", "transcript": "Meeting notes..."}
  }
}
```

Entry listings retain `page`, `per_page` (1–100), `search`, `archived`, `project_id`
(`"none"` selects private entries), and `owner` (`"me"`). They return compact
metadata with transcript/summary URIs instead of full transcripts. `get_entry`
also returns compact metadata and processing status. URL creation returns
immediately; poll `get_entry` until processing finishes. Existing REST state
restrictions still apply: for example, only READY entries can be archived.

`read_entry_text` takes `entry_id`, `field` (`transcript` or `summary`), `offset`
(default 0), and `limit` (1–20,000 characters). It supports clients without resource
support. Text is untrusted user data; it must not be treated as server instructions.

Audio streaming, project/member administration, template mutations, admin
operations, and credential management are not exposed in this release.

## Uploading files

`upload_file` sends an audio or video file to VoiceVault, which transcribes it like
a file uploaded in the UI: same supported formats, same `MAX_UPLOAD_SIZE` (2 GB by
default). MCP tool arguments are JSON written by the model, so a file reaches the
server in one of two ways:

- **Upload link (default).** Call `upload_file` without `content_base64`; every
  argument is optional, so a model can ask for a link before it knows anything
  about the file. The result is a single-use link with two ways to use it:
  - `upload_url`, `method` and `headers` for an HTTP `PUT` of the raw file, plus a
    ready `curl` command. Agents that can run shell commands (Claude Code, Codex)
    upload local files this way. When the link was created without a `filename`
    (`filename_query_required: true`), append `?filename=<url-encoded name>`.
  - `browser_url`, a VoiceVault page where the user picks the file, with a
    progress bar. This is for chat clients that cannot read local files. The page
    needs no login; the link authorizes the upload.
- **Inline.** For files up to 1 MiB, pass `filename` and `content_base64`; the entry
  is created in the same call. Larger payloads would exceed the 2 MiB `/mcp`
  request limit, so they are refused with a pointer to the link mode.

Then confirm with `get_upload_status` (`pending`, `uploading`, `completed`,
`expired`; completed uploads include the entry). The entry starts as `NEW`; poll
`get_entry` until it is `READY`, then use `read_entry_text`, `chat_with_entry` or the
transcript resources. Media that cannot be decoded ends as `ERROR` with an
`error_message`.

Error handling:

- Unsupported file types, a declared `size_bytes` above the limit, and missing
  project editor rights are refused before any bytes are sent.
- Optional `size_bytes` and `sha256` (hex) let the server detect truncated or
  corrupted transfers (400).
- An interrupted or failed upload commits nothing, and the same link can be used
  again until it expires. A retry after a lost success response gets 409 naming the
  existing entry instead of creating a duplicate.
- Other `PUT` responses: 401 invalid or revoked link, 410 expired, 413 too large,
  503 storage unavailable (retry the same link). See the [API reference](api.md#upload-links).

Security notes:

- Links work once and expire after `UPLOAD_SESSION_TTL_MINUTES` (default 60) unless
  their upload has started. Each one can only add one file to its creator's
  account and cannot read anything.
- The link secret (`vvupl_…`) appears in the tool result, and therefore in the
  conversation, and in the `curl` command line. Revoking the PAT that created a link,
  deactivating its owner, or removing their editor role invalidates it.
- The browser page receives the secret in the URL fragment, which browsers do not
  send to servers, and removes it from the address bar once loaded.
- Links are built from `PUBLIC_BASE_URL`; without it, link creation returns 503.

## Resources

Resource templates are discoverable through `resources/templates/list`; there is
no eagerly enumerated list of every user's entries. Obtain IDs through the list
tools. All resources return `application/json` and enforce the corresponding read
scope and object access on every read:

- `voicevault://entries/{entry_id}`: compact metadata.
- `voicevault://entries/{entry_id}/transcript`: first transcript page.
- `voicevault://entries/{entry_id}/summary`: first saved summary page.
- `voicevault://entries/{entry_id}/transcript/{offset}`: transcript continuation.
- `voicevault://entries/{entry_id}/summary/{offset}`: summary continuation.
- `voicevault://projects/{project_id}`: project details.

Text pages include `available`, `text`, `status`, `total_characters`, `next_offset`,
and `next_uri`. Follow `next_uri` until it is null. Missing text has
`available=false`; a resource read never generates a summary or starts processing.
Pages reflect current REST data and are not immutable snapshots.

## Python client smoke check

Use the API environment (`pip install -r api/requirements.txt`) and set
`VOICEVAULT_MCP_URL` and `VOICEVAULT_PAT` through your shell or secret manager.
The script only discovers tools and lists entries; it does not modify data:

```bash
python dev/mcp_smoke.py
```

The script uses the official SDK client over HTTP. The server pins `mcp==1.28.0`
(the maintained 1.x SDK) and tests protocol revision `2025-11-25`. Earlier revisions
supported by that SDK can negotiate normally; revision `2026-07-28` is not part of
this release. The transport is stateless, returns JSON, and does not offer resource
subscriptions or legacy HTTP+SSE endpoints. No session affinity is needed.

## Inspector and LLM client validation

Using MCP Inspector, choose Streamable HTTP, enter the endpoint URL, and set the
Authorization header. If the client sends an Origin, add that exact origin to
`CORS_ORIGINS`. Follow the same connection settings in an LLM client that supports
custom HTTP headers.

Acceptance scenario using disposable data:

1. Discover tools and resource templates.
2. Create an entry from a short transcript with a read/write PAT.
3. Read its transcript resource and confirm the entry appears in the REST API/UI.
4. Upload a short audio file through an `upload_file` link (curl or `browser_url`),
   confirm it with `get_upload_status`, and read the transcript once it is `READY`.
5. Repeat a write with an `entries:read`-only PAT and verify the permission error.
6. Revoke the PAT through the UI and verify subsequent MCP requests return 401,
   and that an unused upload link created with it returns 401 too.

The automated suite uses an independent Python SDK client over a real TCP socket,
including concurrent users. Inspector 1.0.2 interoperability was also exercised
against disposable data during development. Interactive LLM-host behavior and a
live production deployment remain deployment acceptance checks.

## Deployment and maintenance

The Compose files forward MCP settings to the API. The Nginx templates contain an
exact `/mcp` location with HTTP/1.1, preserved request headers, buffering/cache
disabled, 300-second proxy timeouts, and a 2 MiB request-body limit, which also
bounds inline uploads. Upload links use the `/api` location instead, which accepts
`MAX_UPLOAD_SIZE`. Internal REST
operations have a 180-second asynchronous timeout and are not automatically
retried. Chat and summary generation use asynchronous provider clients with a
10-second connection timeout, 120-second read/write timeouts, and provider retries
disabled. Provider clients close after success, failure, or cancellation. Other
synchronous REST work, such as database operations, is not preempted by the
asynchronous timeout. The proxy limit does not apply when bypassing Nginx. Cancellation or a
timeout may occur after a mutation committed; check the entry before retrying.

Invalid authentication returns HTTP 401. Tool-level REST failures are returned as
MCP tool errors with the REST status and a safe message. Resource failures use MCP
resource errors. Missing permissions produce 403; invisible entries/projects
retain REST's 404 behavior. Server-side REST failures omit internal exception
details. MCP argument-validation errors report field locations and error codes
without echoing submitted values. The existing PAT activity tracking also records the authorized `/auth/me`
preflight used for MCP authentication/discovery. No raw tokens are added to logs.

SDK dependencies require compatible updates to FastAPI, HTTPX, Pydantic,
pydantic-settings, python-multipart, and Uvicorn. OpenAI's client is updated for
HTTPX 0.28 compatibility. Upload links are stored in an `upload_sessions` table,
created automatically at API startup; there are no manual migrations or worker
changes.

Run all API and MCP tests:

```bash
cd api
python -m unittest discover -s tests
```

Tests use temporary SQLite data with real REST routes, PAT validation, and access
checks; LLM calls are mocked. CI runs the same suite on Python 3.11. Production
PostgreSQL, worker/provider processing, and reverse-proxy deployment should also
be checked in the target environment before enabling the feature there.

References: [Python SDK](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x),
[MCP authorization](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization),
[MCP Inspector](https://github.com/modelcontextprotocol/inspector).
