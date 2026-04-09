# System Prompt Management — Design Spec

**Date:** 2026-04-09
**Status:** Approved
**Inspiration:** fastrepl/char task-based prompt routing pattern

---

## Overview

Extend VoiceVault's Settings to manage system prompts for AI tasks. Currently both the Chat and Summary system prompts are hard-coded in `chat_service.py`. This feature moves them into a database-backed, UI-editable configuration with seeded defaults — following the same architectural pattern as the existing `PromptTemplate` system.

**Scope:** Chat task + Summary task. Title generation excluded (entry titles are set via UI).

---

## Background & Motivation

VoiceVault already has a two-tier prompt system:
- **User-facing prompt templates** — markdown starters injected into the chat input, fully managed via UI
- **System prompts** — hard-coded in Python, not configurable without a code change

The `char` (fastrepl/char) project uses a task-based architecture where `Chat`, `Enhance`, and `Title` tasks each route to distinct system prompts and models. Adapting this pattern gives VoiceVault operator-level control over AI behaviour without requiring redeployment.

---

## Data Model

### New table: `system_prompts`

| Column | Type | Notes |
|--------|------|-------|
| `task` | VARCHAR (PK) | `'chat'` or `'summary'` |
| `body` | TEXT | The system prompt content |
| `updated_at` | DATETIME | Last modified timestamp |

- `task` is the primary key — exactly one row per task
- Both rows are upserted on every API startup (see Seeding below) — rows are never in a missing state after first boot
- Rows are never deleted by the application; only updated

---

## Backend

### New files

**`/api/app/models/system_prompt.py`**
- SQLAlchemy `SystemPrompt` model with the schema above
- Must be imported in `main.py` alongside other model imports so `Base.metadata.create_all()` creates the table

**`/api/app/services/system_prompt_service.py`**
- Hardcoded defaults stored as module-level string constants (`DEFAULT_PROMPTS: dict[str, str]`)
- `get_prompt(task: str) -> str` — returns current DB body; falls back to `DEFAULT_PROMPTS[task]` if row is missing (defensive only — rows are upserted on startup)
- `update_prompt(task: str, body: str)` — upsert by task
- `reset_to_default(task: str)` — sets body to `DEFAULT_PROMPTS[task]`, updates `updated_at`
- `seed_defaults()` — **upserts both rows unconditionally on every startup** (not a skip-if-exists check); ensures rows always exist and resets any rows deleted directly in the DB

**`/api/app/api/routes/system_prompts.py`**

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| `GET` | `/api/system-prompts/` | List both tasks with current body | `list[SystemPromptResponse]` |
| `PUT` | `/api/system-prompts/{task}` | Update prompt body | `SystemPromptResponse` |
| `POST` | `/api/system-prompts/{task}/reset` | Reset to default | `SystemPromptResponse` |

All mutating endpoints return the full updated `SystemPromptResponse` body — consistent with the frontend `Promise<SystemPrompt>` return types for both `updateSystemPrompt` and `resetSystemPrompt`.

- `{task}` path parameter is typed as a Python `Enum` (or `Literal['chat', 'summary']`) at the route level — FastAPI automatically returns 422 for unrecognised values without reaching the service layer

### Modified files

**`/api/app/services/chat_service.py`**

- Remove hardcoded system prompt strings from `_build_conversation_context()` and `generate_summary()`
- `ChatService` today takes no `db` parameter. Rather than restructuring it, the route handler resolves the system prompts **before** calling the service and passes them in as strings. The route handler already has `db: Session = Depends(get_db)`, so:
  ```python
  # In the route handler:
  prompt_service = SystemPromptService(db)
  chat_system_prompt = prompt_service.get_prompt('chat')
  # Then pass into ChatService methods as a parameter
  ```
  `chat_with_entry()` and `generate_summary()` each gain a `system_prompt: str` parameter. This keeps `ChatService` DB-free and the resolution at the boundary layer.

**Chat task message construction** — the stored `body` is a Python format string. Before being passed to `chat_with_entry()`, the route handler performs substitution:
```python
resolved = chat_system_prompt.format(
    entry_title=entry.title,
    transcript=entry.transcript
)
```
A `try/except (KeyError, ValueError)` wraps the `.format()` call; on failure it falls back to the raw body with a logged warning (guards against operators accidentally introducing stray `{`/`}` in the prompt editor).

Placeholder tokens in the default body are `{entry_title}` and `{transcript}` (plain keys, not `entry.title` attribute syntax).

**Summary task message construction** — the stored `body` is used as the system message unchanged (no entry-specific placeholders). The transcript is passed as a separate user message, preserving the existing two-message structure:
```python
messages = [
    {"role": "system", "content": summary_system_prompt},
    {"role": "user", "content": entry.transcript}
]
```

**`/api/app/main.py`**
- Import `system_prompt` model module alongside `entry` and `prompt_template` so the table is registered with `Base.metadata`
- Call `SystemPromptService(db).seed_defaults()` in the startup lifespan (after existing `seed_defaults_if_empty()` call for templates)

**`/api/app/models/schemas.py`**
- Add `SystemPromptResponse` (task, body, updated_at) and `SystemPromptUpdate` (body) Pydantic schemas

---

## Frontend

### New files

**`/ui/src/components/SystemPromptSettings.tsx`**
- Fetches all system prompts via `getSystemPrompts()` on mount (list endpoint returns both tasks — no single-resource GET needed given only two tasks)
- Two stacked cards, one per task (Chat, Summary)
- Each card: task label + description, textarea editor, Save button, Reset to default button
- Per-card dirty state (unsaved changes tracked independently per card)
- Reset triggers a confirmation dialog before overwriting

### Modified files

**`/ui/src/components/PromptTemplateManager.tsx` → becomes `SettingsModal.tsx`**
- Known consumers to update alongside the rename: `App.tsx` (import + JSX reference) and `PromptTemplateManager.test.tsx` (rename file + update import)
- Search all other files for `PromptTemplateManager` before renaming to catch any additional consumers
- Becomes a tabbed modal: Tab 1 "Templates" (existing content, unchanged), Tab 2 "System Prompts" (new `SystemPromptSettings`)
- Export name changes from `PromptTemplateManager` to `SettingsModal`

**`/ui/src/services/api.ts`**
- `getSystemPrompts() → Promise<SystemPrompt[]>`
- `updateSystemPrompt(task: string, body: string) → Promise<SystemPrompt>`
- `resetSystemPrompt(task: string) → Promise<SystemPrompt>`

**`/ui/src/types/index.ts`**
- Add `SystemPrompt` interface:
  ```typescript
  interface SystemPrompt {
    task: 'chat' | 'summary'
    body: string
    updated_at: string
  }
  ```

**`/ui/src/App.tsx`**
- Update import and reference from `PromptTemplateManager` to `SettingsModal`
- Update the visible button label from `"Templates"` to `"Settings"` (the modal now covers more than templates)

---

## Default Prompt Content

### Chat (task: `'chat'`)

Stored body uses `{entry_title}` and `{transcript}` as Python format string placeholders. Substitution happens in `chat_service.py` before the LLM call.

```
You are an AI assistant helping users analyze and discuss voice transcripts.
You have access to a transcript from "{entry_title}".

TRANSCRIPT:
{transcript}

Guidelines:
- Answer questions accurately using only the transcript content
- Provide specific quotes when relevant
- Help with analysis: key themes, action items, decisions, sentiment
- If asked about something not in the transcript, say so clearly
- Be concise but thorough
```

### Summary (task: `'summary'`)

Stored body is used directly as the system message. No entry-specific placeholders — the transcript is injected as a separate user message by `chat_service.py`.

```
You are an expert analyst summarizing voice transcripts.
Produce a structured summary with these sections:

**Key Points** — the 3–5 most important topics discussed
**Decisions Made** — concrete decisions or conclusions reached
**Action Items** — tasks, owners, and deadlines if mentioned
**Open Questions** — unresolved issues or topics needing follow-up

Be factual. Only include sections where content exists in the transcript.
```

---

## Error Handling

- Invalid `task` value in route → 422 Unprocessable Entity (enforced by route-level `Enum`/`Literal` type, not service layer)
- DB unavailable during prompt load → fall back to `DEFAULT_PROMPTS` constants (no crash)
- Frontend save failure → show inline error on the affected card, do not clear editor

---

## What is NOT in scope

- Title generation task (entry titles are set via UI)
- Per-user system prompt customization (single global config)
- Creating new task types beyond `chat` and `summary`
- Prompt versioning or history
- Single-resource `GET /api/system-prompts/{task}` endpoint (list-all is sufficient for two tasks)

---

## File Change Summary

| File | Change |
|------|--------|
| `api/app/models/system_prompt.py` | New — also add import in `main.py` model imports |
| `api/app/services/system_prompt_service.py` | New |
| `api/app/api/routes/system_prompts.py` | New |
| `api/app/services/chat_service.py` | Remove hardcoded prompts, inject service, add format() substitution for chat |
| `api/app/main.py` | Add model import + `seed_defaults()` call on startup |
| `api/app/models/schemas.py` | Add SystemPrompt schemas |
| `ui/src/components/SystemPromptSettings.tsx` | New |
| `ui/src/components/PromptTemplateManager.tsx` | Rename to `SettingsModal.tsx` |
| `ui/src/components/PromptTemplateManager.test.tsx` | Rename to `SettingsModal.test.tsx`, update import |
| `ui/src/services/api.ts` | Add system prompt API calls |
| `ui/src/types/index.ts` | Add SystemPrompt type |
| `ui/src/App.tsx` | Update import from `PromptTemplateManager` to `SettingsModal` |
