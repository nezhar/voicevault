# System Prompt Management Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the hard-coded Chat and Summary system prompts in `chat_service.py` into a database-backed, UI-editable configuration with a new "System Prompts" tab in the Settings modal.

**Architecture:** New `SystemPrompt` SQLAlchemy model (task string PK) + `SystemPromptService` + three API routes. Route handlers resolve prompts from DB and pass them as strings into `ChatService` methods (which gain a `system_prompt: str` parameter). Frontend adds `SystemPromptSettings` component inside a renamed, tabbed `SettingsModal`.

**Tech Stack:** Python/FastAPI/SQLAlchemy (backend), React/TypeScript/Tailwind (frontend), Vitest + Testing Library (frontend tests), unittest/MagicMock (backend tests)

---

## Chunk 1: Backend Data Layer

### Task 1: SystemPrompt SQLAlchemy model

**Files:**
- Create: `api/app/models/system_prompt.py`
- Create: `api/tests/test_system_prompt_service.py` (first test only)

- [ ] **Step 1: Write a failing import test**

```python
# api/tests/test_system_prompt_service.py
import sys
from pathlib import Path
from unittest import TestCase

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.models.system_prompt import SystemPrompt


class SystemPromptModelTests(TestCase):
    def test_model_has_expected_columns(self):
        cols = {c.name for c in SystemPrompt.__table__.columns}
        self.assertEqual(cols, {"task", "body", "updated_at"})

    def test_task_is_primary_key(self):
        pk_cols = {c.name for c in SystemPrompt.__table__.primary_key.columns}
        self.assertEqual(pk_cols, {"task"})
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd /workspace/api && python -m pytest tests/test_system_prompt_service.py::SystemPromptModelTests -v
```
Expected: `ModuleNotFoundError: No module named 'app.models.system_prompt'`

- [ ] **Step 3: Create the model**

```python
# api/app/models/system_prompt.py
from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text

from app.db.database import Base


class SystemPrompt(Base):
    __tablename__ = "system_prompts"

    task = Column(String(50), primary_key=True)
    body = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
cd /workspace/api && python -m pytest tests/test_system_prompt_service.py::SystemPromptModelTests -v
```
Expected: `2 passed`

---

### Task 2: SystemPromptService

**Files:**
- Create: `api/app/services/system_prompt_service.py`
- Modify: `api/tests/test_system_prompt_service.py` (add service tests)

- [ ] **Step 1: Add failing service tests**

Append to `api/tests/test_system_prompt_service.py`:

```python
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from app.services.system_prompt_service import DEFAULT_PROMPTS, SystemPromptService


class SystemPromptServiceTests(TestCase):
    def make_row(self, task="chat", body="custom body"):
        return SimpleNamespace(task=task, body=body)

    def test_get_prompt_returns_db_body_when_row_exists(self):
        db = MagicMock()
        service = SystemPromptService(db)
        db.query.return_value.filter.return_value.first.return_value = self.make_row(
            task="chat", body="db body"
        )
        result = service.get_prompt("chat")
        self.assertEqual(result, "db body")

    def test_get_prompt_falls_back_to_default_when_row_missing(self):
        db = MagicMock()
        service = SystemPromptService(db)
        db.query.return_value.filter.return_value.first.return_value = None
        result = service.get_prompt("chat")
        self.assertEqual(result, DEFAULT_PROMPTS["chat"])

    def test_update_prompt_updates_existing_row(self):
        db = MagicMock()
        service = SystemPromptService(db)
        existing = self.make_row(task="chat", body="old body")
        db.query.return_value.filter.return_value.first.return_value = existing
        service.update_prompt("chat", "new body")
        self.assertEqual(existing.body, "new body")
        db.commit.assert_called_once()

    def test_update_prompt_inserts_when_row_missing(self):
        db = MagicMock()
        service = SystemPromptService(db)
        db.query.return_value.filter.return_value.first.return_value = None
        service.update_prompt("chat", "new body")
        db.add.assert_called_once()
        db.commit.assert_called_once()

    def test_reset_to_default_restores_default_body(self):
        db = MagicMock()
        service = SystemPromptService(db)
        existing = self.make_row(task="summary", body="custom")
        db.query.return_value.filter.return_value.first.return_value = existing
        service.reset_to_default("summary")
        self.assertEqual(existing.body, DEFAULT_PROMPTS["summary"])

    def test_seed_defaults_inserts_when_row_missing(self):
        db = MagicMock()
        service = SystemPromptService(db)
        # Simulate both rows missing
        db.query.return_value.filter.return_value.first.return_value = None
        service.seed_defaults()
        self.assertEqual(db.add.call_count, len(DEFAULT_PROMPTS))
        db.commit.assert_called_once()

    def test_seed_defaults_overwrites_existing_rows_unconditionally(self):
        db = MagicMock()
        service = SystemPromptService(db)
        existing_chat = self.make_row(task="chat", body="custom body")
        existing_summary = self.make_row(task="summary", body="custom summary")
        # Return different rows per task call
        db.query.return_value.filter.return_value.first.side_effect = [
            existing_chat, existing_summary
        ]
        service.seed_defaults()
        # Existing rows must have their body overwritten with defaults
        self.assertEqual(existing_chat.body, DEFAULT_PROMPTS["chat"])
        self.assertEqual(existing_summary.body, DEFAULT_PROMPTS["summary"])
        db.add.assert_not_called()  # no new rows inserted — existing rows updated in place
        db.commit.assert_called_once()

    def test_list_prompts_returns_all_rows(self):
        db = MagicMock()
        service = SystemPromptService(db)
        rows = [self.make_row("chat"), self.make_row("summary")]
        db.query.return_value.all.return_value = rows
        result = service.list_prompts()
        self.assertEqual(result, rows)

    def test_default_prompts_has_chat_and_summary_keys(self):
        self.assertIn("chat", DEFAULT_PROMPTS)
        self.assertIn("summary", DEFAULT_PROMPTS)
        self.assertIn("{entry_title}", DEFAULT_PROMPTS["chat"])
        self.assertIn("{transcript}", DEFAULT_PROMPTS["chat"])
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
cd /workspace/api && python -m pytest tests/test_system_prompt_service.py::SystemPromptServiceTests -v
```
Expected: `ImportError` or `AttributeError` — service does not exist yet

- [ ] **Step 3: Create the service**

```python
# api/app/services/system_prompt_service.py
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.system_prompt import SystemPrompt

DEFAULT_PROMPTS: dict[str, str] = {
    "chat": (
        'You are an AI assistant helping users analyze and discuss voice transcripts.\n'
        'You have access to a transcript from "{entry_title}".\n\n'
        'TRANSCRIPT:\n'
        '{transcript}\n\n'
        'Guidelines:\n'
        '- Answer questions accurately using only the transcript content\n'
        '- Provide specific quotes when relevant\n'
        '- Help with analysis: key themes, action items, decisions, sentiment\n'
        '- If asked about something not in the transcript, say so clearly\n'
        '- Be concise but thorough'
    ),
    "summary": (
        'You are an expert analyst summarizing voice transcripts.\n'
        'Produce a structured summary with these sections:\n\n'
        '**Key Points** — the 3–5 most important topics discussed\n'
        '**Decisions Made** — concrete decisions or conclusions reached\n'
        '**Action Items** — tasks, owners, and deadlines if mentioned\n'
        '**Open Questions** — unresolved issues or topics needing follow-up\n\n'
        'Be factual. Only include sections where content exists in the transcript.'
    ),
}


class SystemPromptService:
    def __init__(self, db: Session):
        self.db = db

    def get_prompt(self, task: str) -> str:
        row = self.db.query(SystemPrompt).filter(SystemPrompt.task == task).first()
        if row:
            return row.body
        return DEFAULT_PROMPTS.get(task, "")

    def update_prompt(self, task: str, body: str) -> SystemPrompt:
        row = self.db.query(SystemPrompt).filter(SystemPrompt.task == task).first()
        if row:
            row.body = body
            row.updated_at = datetime.utcnow()
        else:
            row = SystemPrompt(task=task, body=body, updated_at=datetime.utcnow())
            self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def reset_to_default(self, task: str) -> SystemPrompt:
        return self.update_prompt(task, DEFAULT_PROMPTS[task])

    def seed_defaults(self) -> None:
        """Unconditionally upsert default prompts on every startup.

        Inserts missing rows and resets existing rows to their factory defaults.
        This ensures rows are never absent (e.g. after direct DB deletion) and
        that the factory defaults are always present after a fresh deploy.
        Custom edits are intentionally overwritten — operators should edit via
        the UI, not directly in the database.
        """
        for task, body in DEFAULT_PROMPTS.items():
            existing = self.db.query(SystemPrompt).filter(SystemPrompt.task == task).first()
            if existing:
                existing.body = body
                existing.updated_at = datetime.utcnow()
            else:
                self.db.add(SystemPrompt(task=task, body=body, updated_at=datetime.utcnow()))
        self.db.commit()

    def list_prompts(self) -> list[SystemPrompt]:
        return self.db.query(SystemPrompt).all()
```

- [ ] **Step 4: Run all service tests**

```bash
cd /workspace/api && python -m pytest tests/test_system_prompt_service.py -v
```
Expected: `11 passed`

---

### Task 3: Pydantic schemas

**Files:**
- Modify: `api/app/models/schemas.py`

- [ ] **Step 1: Add schemas to `schemas.py`**

Append to the end of `api/app/models/schemas.py`:

```python
class SystemPromptUpdate(BaseModel):
    body: str = Field(..., min_length=1)


class SystemPromptResponse(BaseModel):
    task: str
    body: str
    updated_at: datetime

    class Config:
        from_attributes = True
```

- [ ] **Step 2: Verify import works**

```bash
cd /workspace/api && python -c "from app.models.schemas import SystemPromptResponse, SystemPromptUpdate; print('OK')"
```
Expected: `OK`

---

### Task 4: Wire model and service into main.py

**Files:**
- Modify: `api/app/main.py`

- [ ] **Step 1: Add model import and seed call**

Make three targeted edits to `api/app/main.py`:

**Edit 1** — add `system_prompt` to the model imports line (currently line 7):
```python
# Before:
from app.models import entry, prompt_template  # Import models to register them
# After:
from app.models import entry, prompt_template, system_prompt  # Import models to register them
```

**Edit 2** — add `SystemPromptService` import directly after the existing `PromptTemplateService` import (currently line 8):
```python
# Before:
from app.services.prompt_template_service import PromptTemplateService
# After:
from app.services.prompt_template_service import PromptTemplateService
from app.services.system_prompt_service import SystemPromptService
```

**Edit 3** — add the seed call inside the `lifespan` function, directly after `PromptTemplateService(db).seed_defaults_if_empty()` (currently line 20):
```python
# Before:
            PromptTemplateService(db).seed_defaults_if_empty()
# After:
            PromptTemplateService(db).seed_defaults_if_empty()
            SystemPromptService(db).seed_defaults()
```

- [ ] **Step 2: Verify the app starts without error**

```bash
cd /workspace/api && python -c "from app.main import app; print('App loaded OK')"
```
Expected: `App loaded OK`

---

## Chunk 2: Backend API Layer

### Task 5: System prompts API routes

**Files:**
- Create: `api/app/api/routes/system_prompts.py`
- Modify: `api/app/main.py` (register router)

- [ ] **Step 1: Create the routes file**

```python
# api/app/api/routes/system_prompts.py
from enum import Enum
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.database import get_db
from app.models.schemas import SystemPromptResponse, SystemPromptUpdate
from app.services.system_prompt_service import SystemPromptService

router = APIRouter()


class SystemPromptTask(str, Enum):
    chat = "chat"
    summary = "summary"


@router.get("/", response_model=List[SystemPromptResponse])
async def list_system_prompts(
    db: Session = Depends(get_db),
    current_user: bool = Depends(get_current_user),
):
    service = SystemPromptService(db)
    return service.list_prompts()


@router.put("/{task}", response_model=SystemPromptResponse)
async def update_system_prompt(
    task: SystemPromptTask,
    data: SystemPromptUpdate,
    db: Session = Depends(get_db),
    current_user: bool = Depends(get_current_user),
):
    service = SystemPromptService(db)
    return service.update_prompt(task.value, data.body)


@router.post("/{task}/reset", response_model=SystemPromptResponse)
async def reset_system_prompt(
    task: SystemPromptTask,
    db: Session = Depends(get_db),
    current_user: bool = Depends(get_current_user),
):
    service = SystemPromptService(db)
    return service.reset_to_default(task.value)
```

- [ ] **Step 2: Register the router in `main.py`**

Make two targeted edits to `api/app/main.py`:

**Edit 1** — add `system_prompts` to the routes import (line 5):
```python
# Before:
from app.api.routes import entries, auth, prompt_templates
# After:
from app.api.routes import entries, auth, prompt_templates, system_prompts
```

**Edit 2** — register the router after the prompt-templates router (line 53):
```python
# Before:
app.include_router(prompt_templates.router, prefix="/api/prompt-templates", tags=["prompt-templates"])
# After:
app.include_router(prompt_templates.router, prefix="/api/prompt-templates", tags=["prompt-templates"])
app.include_router(system_prompts.router, prefix="/api/system-prompts", tags=["system-prompts"])
```

- [ ] **Step 3: Verify routes are registered**

```bash
cd /workspace/api && python -c "
from app.main import app
routes = [r.path for r in app.routes]
assert '/api/system-prompts/' in routes, f'GET / not found, routes: {routes}'
print('Routes OK')
"
```
Expected: `Routes OK`

- [ ] **Step 4: Verify invalid task returns 422**

```bash
cd /workspace/api && python -c "
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
resp = client.put('/api/system-prompts/invalid', json={'body': 'test'})
assert resp.status_code == 422, f'Expected 422 got {resp.status_code}'
print('422 validation OK')
"
```
Expected: `422 validation OK`

---

### Task 6: Refactor ChatService to accept system_prompt parameter

**Files:**
- Modify: `api/app/services/chat_service.py`

> **Note for agent:** The file contains trailing spaces on several lines. Read it with the Read tool before making edits and match the exact bytes on disk, not the cleaned-up snippets below.

- [ ] **Step 1: Read the current file**

```bash
cd /workspace/api && cat -A app/services/chat_service.py | head -60
```
Confirm you can see the exact content of the `chat_with_entry` signature (lines 51–56) and the `_build_conversation_context` call (line 73) before editing.

- [ ] **Step 2: Add `system_prompt` parameter to `chat_with_entry`**

In `chat_with_entry` (lines 51–56): add `, system_prompt: str = ""` as the last parameter before `-> str:`. The resulting signature must be:

```python
    async def chat_with_entry(
        self, 
        entry: Entry, 
        user_message: str, 
        conversation_history: Optional[List[Dict[str, str]]] = None,
        system_prompt: str = "",
    ) -> str:
```

In line 73 (inside `chat_with_entry`), change:
```python
        messages = self._build_conversation_context(entry, user_message, conversation_history)
```
to:
```python
        messages = self._build_conversation_context(entry, user_message, conversation_history, system_prompt)
```

- [ ] **Step 3: Replace `_build_conversation_context` body**

The entire method currently spans lines 95–143. Replace it wholesale with the following (keep the same 4-space indentation as the rest of the class):

```python
    def _build_conversation_context(
        self,
        entry: Entry,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        system_prompt: str = "",
    ) -> List[Dict[str, str]]:
        """Build the conversation context for the LLM"""
        messages = [
            {"role": "system", "content": system_prompt}
        ]

        if conversation_history:
            for msg in conversation_history:
                if msg.get("role") in ["user", "assistant"]:
                    messages.append({
                        "role": msg["role"],
                        "content": msg["content"]
                    })

        messages.append({
            "role": "user",
            "content": user_message
        })

        return messages
```

Note: the `entry` parameter is retained in the signature for call-site compatibility even though the method body no longer uses it.

- [ ] **Step 4: Update `generate_summary` signature and body**

Add `, system_prompt: str = ""` parameter to `generate_summary` (line 145). The signature becomes:
```python
    async def generate_summary(self, entry: Entry, system_prompt: str = "") -> str:
```

Then replace the body of `generate_summary` from line 151 up to (but not including) the `try:` block's existing content. Specifically:

1. Delete the `summary_prompt = f"""..."""` block (lines 151–162).
2. Replace the two-message `messages=[...]` list inside the `try:` block (lines 167–170) with:
```python
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": entry.transcript}
                ],
```

The final `generate_summary` body (from the docstring to the end of the try/except) must look like:

```python
    async def generate_summary(self, entry: Entry, system_prompt: str = "") -> str:
        """Generate a summary of the entry transcript"""
        
        if not entry.transcript:
            raise ValueError("Entry must have a transcript to summarize")
        
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": entry.transcript}
                ],
                max_tokens=512,
                temperature=0.3,
                top_p=0.9
            )
            
            summary = completion.choices[0].message.content
            logger.info(f"Generated summary for entry {entry.id}")
            
            return summary.strip()
            
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            raise Exception(f"Failed to generate summary: {str(e)}")
```

- [ ] **Step 5: Verify ChatService still imports correctly**

```bash
cd /workspace/api && python -c "from app.services.chat_service import ChatService; print('ChatService OK')"
```
Expected: `ChatService OK`

---

### Task 7: Update entry route handlers to resolve system prompts

**Files:**
- Modify: `api/app/api/routes/entries.py`

- [ ] **Step 1: Add SystemPromptService import**

In `api/app/api/routes/entries.py`, add to the imports:
```python
from app.services.system_prompt_service import SystemPromptService
```

- [ ] **Step 2: Update the `chat_with_entry` route handler**

In the `chat_with_entry` route handler (around line 270), replace:
```python
    # Initialize chat service
    try:
        chat_service = ChatService()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Convert conversation history to dict format
    conversation_history = None
    if chat_request.conversation_history:
        conversation_history = [
            {"role": msg.role, "content": msg.content}
            for msg in chat_request.conversation_history
        ]

    try:
        # Generate response
        response_message = await chat_service.chat_with_entry(
            entry=entry,
            user_message=chat_request.message,
            conversation_history=conversation_history
        )
```
with:
```python
    # Initialize chat service
    try:
        chat_service = ChatService()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Resolve system prompt from DB
    raw_prompt = SystemPromptService(db).get_prompt("chat")
    try:
        resolved_prompt = raw_prompt.format(
            entry_title=entry.title,
            transcript=entry.transcript,
        )
    except (KeyError, ValueError):
        logger.warning(f"Failed to format chat system prompt, using raw body")
        resolved_prompt = raw_prompt

    # Convert conversation history to dict format
    conversation_history = None
    if chat_request.conversation_history:
        conversation_history = [
            {"role": msg.role, "content": msg.content}
            for msg in chat_request.conversation_history
        ]

    try:
        # Generate response
        response_message = await chat_service.chat_with_entry(
            entry=entry,
            user_message=chat_request.message,
            conversation_history=conversation_history,
            system_prompt=resolved_prompt,
        )
```

- [ ] **Step 3: Update the `generate_entry_summary` route handler**

In the `generate_entry_summary` route handler (around line 329), replace:
```python
    # Initialize chat service
    try:
        chat_service = ChatService()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        # Generate summary
        summary = await chat_service.generate_summary(entry)
```
with:
```python
    # Initialize chat service
    try:
        chat_service = ChatService()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Resolve system prompt from DB
    summary_system_prompt = SystemPromptService(db).get_prompt("summary")

    try:
        # Generate summary
        summary = await chat_service.generate_summary(entry, system_prompt=summary_system_prompt)
```

- [ ] **Step 4: Verify the entries module imports cleanly**

```bash
cd /workspace/api && python -c "from app.api.routes.entries import router; print('entries router OK')"
```
Expected: `entries router OK`

- [ ] **Step 5: Run all backend tests**

```bash
cd /workspace/api && python -m pytest tests/ -v
```
Expected: all existing tests pass + new system prompt tests pass

---

## Chunk 3: Frontend

### Task 8: TypeScript type and API client functions

**Files:**
- Modify: `ui/src/types/index.ts`
- Modify: `ui/src/services/api.ts`

- [ ] **Step 1: Add `SystemPrompt` interface to types**

In `ui/src/types/index.ts`, append:

```typescript
export interface SystemPrompt {
  task: 'chat' | 'summary';
  body: string;
  updated_at: string;
}
```

- [ ] **Step 2: Add API client functions to `api.ts`**

`api.ts` exports an object named `entryApi`. The three new functions go **inside** the `entryApi` object, after the `deletePromptTemplate` function (around line 132) and before the `chatWithEntry` function (around line 135).

Add the `SystemPrompt` type to the import block at the top of `api.ts`:
```typescript
// Before:
import {
  Entry,
  EntryCreate,
  EntryTranscriptCreate,
  EntryList,
  ChatRequest,
  ChatResponse,
  SummaryResponse,
  PromptTemplate,
  PromptTemplateCreate,
  PromptTemplateUpdate,
} from '../types';
// After:
import {
  Entry,
  EntryCreate,
  EntryTranscriptCreate,
  EntryList,
  ChatRequest,
  ChatResponse,
  SummaryResponse,
  PromptTemplate,
  PromptTemplateCreate,
  PromptTemplateUpdate,
  SystemPrompt,
} from '../types';
```

Then inside the `entryApi` object, insert the three new functions **between** `deletePromptTemplate` and `chatWithEntry`:
```typescript
// Before:
  deletePromptTemplate: async (id: string): Promise<void> => {
    await api.delete(`/prompt-templates/${id}`);
  },

  // Chat with entry
  chatWithEntry: async (id: string, data: ChatRequest): Promise<ChatResponse> => {
// After:
  deletePromptTemplate: async (id: string): Promise<void> => {
    await api.delete(`/prompt-templates/${id}`);
  },

  // System prompts
  getSystemPrompts: async (): Promise<SystemPrompt[]> => {
    const response = await api.get('/system-prompts/');
    return response.data;
  },

  updateSystemPrompt: async (task: string, body: string): Promise<SystemPrompt> => {
    const response = await api.put(`/system-prompts/${task}`, { body });
    return response.data;
  },

  resetSystemPrompt: async (task: string): Promise<SystemPrompt> => {
    const response = await api.post(`/system-prompts/${task}/reset`);
    return response.data;
  },

  // Chat with entry
  chatWithEntry: async (id: string, data: ChatRequest): Promise<ChatResponse> => {
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd /workspace/ui && npx tsc --noEmit 2>&1 | head -20
```
Expected: no errors (or only pre-existing errors unrelated to new code)

---

### Task 9: SystemPromptSettings component

**Files:**
- Create: `ui/src/components/SystemPromptSettings.tsx`

- [ ] **Step 1: Write the failing test**

Create `ui/src/components/SystemPromptSettings.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SystemPromptSettings } from './SystemPromptSettings';

const mockPrompts = [
  {
    task: 'chat' as const,
    body: 'You are a chat assistant.',
    updated_at: '2026-04-09T00:00:00Z',
  },
  {
    task: 'summary' as const,
    body: 'You are a summary assistant.',
    updated_at: '2026-04-09T00:00:00Z',
  },
];

describe('SystemPromptSettings', () => {
  it('renders both task cards', () => {
    render(
      <SystemPromptSettings
        prompts={mockPrompts}
        isLoading={false}
        error={null}
        onUpdate={vi.fn()}
        onReset={vi.fn()}
      />
    );
    expect(screen.getByText('Chat')).toBeInTheDocument();
    expect(screen.getByText('Summary')).toBeInTheDocument();
  });

  it('shows current body in each textarea', () => {
    render(
      <SystemPromptSettings
        prompts={mockPrompts}
        isLoading={false}
        error={null}
        onUpdate={vi.fn()}
        onReset={vi.fn()}
      />
    );
    const textareas = screen.getAllByRole('textbox');
    expect(textareas[0]).toHaveValue('You are a chat assistant.');
    expect(textareas[1]).toHaveValue('You are a summary assistant.');
  });

  it('marks card dirty when body is edited', () => {
    render(
      <SystemPromptSettings
        prompts={mockPrompts}
        isLoading={false}
        error={null}
        onUpdate={vi.fn()}
        onReset={vi.fn()}
      />
    );
    const textareas = screen.getAllByRole('textbox');
    fireEvent.change(textareas[0], { target: { value: 'edited chat prompt' } });
    const saveButtons = screen.getAllByRole('button', { name: /save/i });
    expect(saveButtons[0]).not.toBeDisabled();
  });

  it('calls onUpdate with task and new body when Save is clicked', async () => {
    const onUpdate = vi.fn().mockResolvedValue(undefined);
    render(
      <SystemPromptSettings
        prompts={mockPrompts}
        isLoading={false}
        error={null}
        onUpdate={onUpdate}
        onReset={vi.fn()}
      />
    );
    const textareas = screen.getAllByRole('textbox');
    fireEvent.change(textareas[0], { target: { value: 'new chat body' } });
    const saveButtons = screen.getAllByRole('button', { name: /save/i });
    fireEvent.click(saveButtons[0]);
    await waitFor(() => {
      expect(onUpdate).toHaveBeenCalledWith('chat', 'new chat body');
    });
  });

  it('calls onReset when Reset is confirmed', async () => {
    const onReset = vi.fn().mockResolvedValue(undefined);
    window.confirm = vi.fn().mockReturnValue(true);
    render(
      <SystemPromptSettings
        prompts={mockPrompts}
        isLoading={false}
        error={null}
        onUpdate={vi.fn()}
        onReset={onReset}
      />
    );
    const resetButtons = screen.getAllByRole('button', { name: /reset/i });
    fireEvent.click(resetButtons[0]);
    await waitFor(() => {
      expect(onReset).toHaveBeenCalledWith('chat');
    });
  });

  it('does not call onReset when Reset is cancelled', () => {
    const onReset = vi.fn();
    window.confirm = vi.fn().mockReturnValue(false);
    render(
      <SystemPromptSettings
        prompts={mockPrompts}
        isLoading={false}
        error={null}
        onUpdate={vi.fn()}
        onReset={onReset}
      />
    );
    const resetButtons = screen.getAllByRole('button', { name: /reset/i });
    fireEvent.click(resetButtons[0]);
    expect(onReset).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
cd /workspace/ui && npx vitest run src/components/SystemPromptSettings.test.tsx 2>&1 | tail -10
```
Expected: `Cannot find module './SystemPromptSettings'`

- [ ] **Step 3: Implement SystemPromptSettings**

```tsx
// ui/src/components/SystemPromptSettings.tsx
import React, { useEffect, useState } from 'react';
import { SystemPrompt } from '../types';

const TASK_LABELS: Record<string, string> = {
  chat: 'Chat',
  summary: 'Summary',
};

const TASK_DESCRIPTIONS: Record<string, string> = {
  chat: 'System prompt sent to the AI when a user chats with a transcript. Use {entry_title} and {transcript} as placeholders.',
  summary: 'System prompt sent to the AI when generating a transcript summary. The transcript is appended automatically.',
};

interface SystemPromptSettingsProps {
  prompts: SystemPrompt[];
  isLoading: boolean;
  error: string | null;
  onUpdate: (task: string, body: string) => Promise<void>;
  onReset: (task: string) => Promise<void>;
}

interface CardState {
  body: string;
  dirty: boolean;
  saving: boolean;
  saveError: string | null;
}

export const SystemPromptSettings: React.FC<SystemPromptSettingsProps> = ({
  prompts,
  isLoading,
  error,
  onUpdate,
  onReset,
}) => {
  const [cardStates, setCardStates] = useState<Record<string, CardState>>({});

  useEffect(() => {
    const initial: Record<string, CardState> = {};
    for (const p of prompts) {
      initial[p.task] = { body: p.body, dirty: false, saving: false, saveError: null };
    }
    setCardStates(initial);
  }, [prompts]);

  const handleChange = (task: string, value: string) => {
    setCardStates(prev => ({
      ...prev,
      [task]: { ...prev[task], body: value, dirty: true, saveError: null },
    }));
  };

  const handleSave = async (task: string) => {
    setCardStates(prev => ({ ...prev, [task]: { ...prev[task], saving: true, saveError: null } }));
    try {
      await onUpdate(task, cardStates[task].body);
      setCardStates(prev => ({ ...prev, [task]: { ...prev[task], saving: false, dirty: false } }));
    } catch {
      setCardStates(prev => ({
        ...prev,
        [task]: { ...prev[task], saving: false, saveError: 'Failed to save. Please try again.' },
      }));
    }
  };

  const handleReset = async (task: string) => {
    if (!window.confirm('Reset this prompt to its default? Your edits will be lost.')) return;
    setCardStates(prev => ({ ...prev, [task]: { ...prev[task], saving: true, saveError: null } }));
    try {
      await onReset(task);
    } finally {
      setCardStates(prev => ({ ...prev, [task]: { ...prev[task], saving: false, dirty: false } }));
    }
  };

  if (isLoading) {
    return <div className="p-6 text-sm text-gray-500">Loading system prompts…</div>;
  }

  if (error) {
    return <div className="p-6 text-sm text-red-600">{error}</div>;
  }

  const tasks = ['chat', 'summary'];

  return (
    <div className="flex flex-col gap-4 p-6">
      {tasks.map(task => {
        const state = cardStates[task];
        if (!state) return null;
        return (
          <div key={task} className="rounded-lg border border-gray-200 bg-white p-4">
            <div className="mb-1 text-sm font-semibold text-gray-800">{TASK_LABELS[task]}</div>
            <div className="mb-3 text-xs text-gray-500">{TASK_DESCRIPTIONS[task]}</div>
            <textarea
              className="w-full rounded border border-gray-300 p-2 text-xs font-mono leading-relaxed focus:outline-none focus:ring-2 focus:ring-blue-500"
              rows={8}
              value={state.body}
              onChange={e => handleChange(task, e.target.value)}
            />
            {state.saveError && (
              <div className="mt-1 text-xs text-red-600">{state.saveError}</div>
            )}
            <div className="mt-3 flex gap-2">
              <button
                className="rounded bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                disabled={!state.dirty || state.saving}
                onClick={() => handleSave(task)}
              >
                {state.saving ? 'Saving…' : 'Save'}
              </button>
              <button
                className="rounded border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50"
                disabled={state.saving}
                onClick={() => handleReset(task)}
              >
                Reset to default
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
};
```

- [ ] **Step 4: Run the tests**

```bash
cd /workspace/ui && npx vitest run src/components/SystemPromptSettings.test.tsx 2>&1 | tail -15
```
Expected: `6 passed`

---

### Task 10: Add `embedded` prop to PromptTemplateManager + create SettingsModal

**Background:** `PromptTemplateManager` currently renders its own `fixed inset-0 z-40` backdrop and close button. To embed it as a tab panel inside `SettingsModal` without a double-modal conflict, we add an `embedded?: boolean` prop. When `embedded=true`, the outer wrapper becomes a plain `flex-1` div (fills its container) and the close button is hidden. Default behaviour is unchanged.

**Files:**
- Modify: `ui/src/components/PromptTemplateManager.tsx`
- Create: `ui/src/components/SettingsModal.tsx`
- Modify: `ui/src/components/PromptTemplateManager.test.tsx` → rename to `SettingsModal.test.tsx`

- [ ] **Step 1: Verify current consumers of PromptTemplateManager**

```bash
cd /workspace/ui && grep -r "PromptTemplateManager" src/ --include="*.ts" --include="*.tsx" -l
```
Expected output (all known consumers):
```
src/components/PromptTemplateManager.tsx
src/components/PromptTemplateManager.test.tsx
src/App.tsx
```
If any other file appears, update its import before continuing.

- [ ] **Step 2: Add `embedded` prop to PromptTemplateManager**

In `ui/src/components/PromptTemplateManager.tsx`, update the `PromptTemplateManagerProps` interface (around line 8) to add the optional `embedded` prop:

```tsx
// Before:
interface PromptTemplateManagerProps {
  templates: PromptTemplate[];
  isOpen: boolean;
  isLoading: boolean;
  error: string | null;
  onClose: () => void;
  onCreate: (template: PromptTemplateCreate) => Promise<void> | void;
  onUpdate: (id: string, template: PromptTemplateUpdate) => Promise<void> | void;
  onDelete: (id: string) => Promise<void> | void;
}
// After:
interface PromptTemplateManagerProps {
  templates: PromptTemplate[];
  isOpen: boolean;
  isLoading: boolean;
  error: string | null;
  onClose: () => void;
  onCreate: (template: PromptTemplateCreate) => Promise<void> | void;
  onUpdate: (id: string, template: PromptTemplateUpdate) => Promise<void> | void;
  onDelete: (id: string) => Promise<void> | void;
  embedded?: boolean;
}
```

Destructure `embedded` from props (around line 43):
```tsx
// Before:
export const PromptTemplateManager: React.FC<PromptTemplateManagerProps> = ({
  templates,
  isOpen,
  isLoading,
  error,
  onClose,
  onCreate,
  onUpdate,
  onDelete,
}) => {
// After:
export const PromptTemplateManager: React.FC<PromptTemplateManagerProps> = ({
  templates,
  isOpen,
  isLoading,
  error,
  onClose,
  onCreate,
  onUpdate,
  onDelete,
  embedded = false,
}) => {
```

In the JSX return (around line 172), replace the outer wrapper `div` className to be conditional:
```tsx
// Before:
      <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/50 p-4">
        <div className="flex h-[85vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl md:flex-row">
// After:
      <div className={embedded ? 'flex h-full flex-col' : 'fixed inset-0 z-40 flex items-center justify-center bg-black/50 p-4'}>
        <div className={embedded ? 'flex flex-1 flex-col overflow-hidden md:flex-row' : 'flex h-[85vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl md:flex-row'}>
```

Hide the close button when `embedded=true` (the close button is in the header around line 187):
```tsx
// Before:
              <button
                onClick={onClose}
                className="rounded-md p-2 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
                aria-label="Close prompt templates"
              >
                <X className="h-5 w-5" />
              </button>
// After:
              {!embedded && (
                <button
                  onClick={onClose}
                  className="rounded-md p-2 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
                  aria-label="Close prompt templates"
                >
                  <X className="h-5 w-5" />
                </button>
              )}
```

- [ ] **Step 3: Verify the existing test still passes (embedded=false by default)**

```bash
cd /workspace/ui && npx vitest run src/components/PromptTemplateManager.test.tsx 2>&1 | tail -5
```
Expected: `1 passed`

- [ ] **Step 4: Create SettingsModal.tsx**

Both tab panels are always rendered (using `hidden` class to toggle visibility) so unsaved form state in Templates is preserved when switching to System Prompts and back.

```tsx
// ui/src/components/SettingsModal.tsx
import React, { useState } from 'react';
import { X } from 'lucide-react';

import { PromptTemplate, PromptTemplateCreate, PromptTemplateUpdate, SystemPrompt } from '../types';
import { PromptTemplateManager } from './PromptTemplateManager';
import { SystemPromptSettings } from './SystemPromptSettings';

type Tab = 'templates' | 'system-prompts';

interface SettingsModalProps {
  templates: PromptTemplate[];
  isOpen: boolean;
  isLoading: boolean;
  error: string | null;
  onClose: () => void;
  onCreate: (template: PromptTemplateCreate) => Promise<void> | void;
  onUpdate: (id: string, template: PromptTemplateUpdate) => Promise<void> | void;
  onDelete: (id: string) => Promise<void> | void;
  systemPrompts: SystemPrompt[];
  systemPromptsLoading: boolean;
  systemPromptsError: string | null;
  onUpdateSystemPrompt: (task: string, body: string) => Promise<void>;
  onResetSystemPrompt: (task: string) => Promise<void>;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  templates,
  isOpen,
  isLoading,
  error,
  onClose,
  onCreate,
  onUpdate,
  onDelete,
  systemPrompts,
  systemPromptsLoading,
  systemPromptsError,
  onUpdateSystemPrompt,
  onResetSystemPrompt,
}) => {
  const [activeTab, setActiveTab] = useState<Tab>('templates');

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="relative flex h-[85vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">Settings</h2>
          <button
            onClick={onClose}
            className="rounded-md p-2 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
            aria-label="Close settings"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-200 px-6">
          <button
            className={`mr-4 border-b-2 py-3 text-sm font-medium transition-colors ${
              activeTab === 'templates'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
            onClick={() => setActiveTab('templates')}
          >
            Templates
          </button>
          <button
            className={`border-b-2 py-3 text-sm font-medium transition-colors ${
              activeTab === 'system-prompts'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
            onClick={() => setActiveTab('system-prompts')}
          >
            System Prompts
          </button>
        </div>

        {/* Tab panels — both always mounted to preserve unsaved form state */}
        <div className={`flex-1 overflow-auto ${activeTab === 'templates' ? '' : 'hidden'}`}>
          <PromptTemplateManager
            embedded
            templates={templates}
            isOpen={isOpen}
            isLoading={isLoading}
            error={error}
            onClose={onClose}
            onCreate={onCreate}
            onUpdate={onUpdate}
            onDelete={onDelete}
          />
        </div>
        <div className={`flex-1 overflow-auto ${activeTab === 'system-prompts' ? '' : 'hidden'}`}>
          <SystemPromptSettings
            prompts={systemPrompts}
            isLoading={systemPromptsLoading}
            error={systemPromptsError}
            onUpdate={onUpdateSystemPrompt}
            onReset={onResetSystemPrompt}
          />
        </div>
      </div>
    </div>
  );
};
```

- [ ] **Step 5: Rename the test file and update it**

```bash
mv /workspace/ui/src/components/PromptTemplateManager.test.tsx /workspace/ui/src/components/SettingsModal.test.tsx
```

In the renamed `SettingsModal.test.tsx`, update:

1. The import at the top:
```tsx
// Before:
import { PromptTemplateManager } from './PromptTemplateManager';
// After:
import { SettingsModal } from './SettingsModal';
```

2. The `describe` block name:
```tsx
// Before:
describe('PromptTemplateManager', () => {
// After:
describe('SettingsModal', () => {
```

3. The `render(...)` call — replace the whole render block with:
```tsx
    render(
      <SettingsModal
        templates={[
          {
            id: 'template-1',
            label: 'Action items',
            preview_text: 'Extract action items',
            body_markdown: '## Action Items',
            sort_order: 10,
            is_active: true,
            created_at: '2026-04-03T00:00:00Z',
            updated_at: '2026-04-03T00:00:00Z',
          },
        ]}
        isOpen
        isLoading={false}
        error={null}
        onClose={vi.fn()}
        onCreate={vi.fn()}
        onUpdate={vi.fn()}
        onDelete={vi.fn()}
        systemPrompts={[]}
        systemPromptsLoading={false}
        systemPromptsError={null}
        onUpdateSystemPrompt={vi.fn()}
        onResetSystemPrompt={vi.fn()}
      />
    );
```

- [ ] **Step 6: Run the renamed test**

```bash
cd /workspace/ui && npx vitest run src/components/SettingsModal.test.tsx 2>&1 | tail -10
```
Expected: `1 passed`

---

### Task 11: Wire SettingsModal into App.tsx

**Files:**
- Modify: `ui/src/App.tsx`

- [ ] **Step 1: Read current state of App.tsx imports and state**

```bash
cd /workspace/ui && grep -n "PromptTemplateManager\|promptTemplates\|isTemplateManagerOpen\|systemPrompt" src/App.tsx | head -30
```

- [ ] **Step 2: Update the import**

In `ui/src/App.tsx`, replace the import:
```tsx
import { PromptTemplateManager } from './components/PromptTemplateManager';
```
with:
```tsx
import { SettingsModal } from './components/SettingsModal';
```

- [ ] **Step 3: Add system prompt state and update imports**

In `ui/src/App.tsx`:

1. Add `SystemPrompt` to the existing type import (line 11):
```tsx
// Before:
import { Entry, PromptTemplate, PromptTemplateCreate, PromptTemplateUpdate } from './types';
// After:
import { Entry, PromptTemplate, PromptTemplateCreate, PromptTemplateUpdate, SystemPrompt } from './types';
```

2. After the existing `promptTemplates` state declarations (around line 20), add:
```tsx
const [systemPrompts, setSystemPrompts] = useState<SystemPrompt[]>([]);
const [systemPromptsLoading, setSystemPromptsLoading] = useState(false);
const [systemPromptsError, setSystemPromptsError] = useState<string | null>(null);
```

- [ ] **Step 4: Add system prompt fetch on mount**

`App.tsx` uses `entryApi` (imported from `'./services/api'`) for all API calls. Inside the `useEffect` that loads initial data, add a `loadSystemPrompts` call:

```tsx
const loadSystemPrompts = async () => {
  setSystemPromptsLoading(true);
  try {
    const prompts = await entryApi.getSystemPrompts();
    setSystemPrompts(prompts);
  } catch {
    setSystemPromptsError('Failed to load system prompts');
  } finally {
    setSystemPromptsLoading(false);
  }
};
loadSystemPrompts();
```

- [ ] **Step 5: Add system prompt handlers**

In `App.tsx`, add handler functions alongside the existing prompt template handlers:

```tsx
const handleUpdateSystemPrompt = async (task: string, body: string) => {
  const updated = await entryApi.updateSystemPrompt(task, body);
  setSystemPrompts(prev => prev.map(p => (p.task === task ? updated : p)));
};

const handleResetSystemPrompt = async (task: string) => {
  const updated = await entryApi.resetSystemPrompt(task);
  setSystemPrompts(prev => prev.map(p => (p.task === task ? updated : p)));
};
```

- [ ] **Step 6: Replace PromptTemplateManager JSX with SettingsModal**

Replace the Settings button label and the `<PromptTemplateManager ...>` component in the JSX:

Change the button:
```tsx
        <span>Templates</span>
```
to:
```tsx
        <span>Settings</span>
```

The current `App.tsx` (lines 346–354) has the `<PromptTemplateManager ...>` block. Find its closing `/>` in the file and replace the entire element including the closing `/>`:

```tsx
      <PromptTemplateManager
        templates={promptTemplates}
        isOpen={isTemplateManagerOpen}
        isLoading={promptTemplatesLoading}
        error={promptTemplatesError}
        onClose={() => setIsTemplateManagerOpen(false)}
        onCreate={handleCreatePromptTemplate}
        onUpdate={handleUpdatePromptTemplate}
        onDelete={handleDeletePromptTemplate}
      />
```
with:
```tsx
      <SettingsModal
        templates={promptTemplates}
        isOpen={isTemplateManagerOpen}
        isLoading={promptTemplatesLoading}
        error={promptTemplatesError}
        onClose={() => setIsTemplateManagerOpen(false)}
        onCreate={handleCreatePromptTemplate}
        onUpdate={handleUpdatePromptTemplate}
        onDelete={handleDeletePromptTemplate}
        systemPrompts={systemPrompts}
        systemPromptsLoading={systemPromptsLoading}
        systemPromptsError={systemPromptsError}
        onUpdateSystemPrompt={handleUpdateSystemPrompt}
        onResetSystemPrompt={handleResetSystemPrompt}
      />
```

- [ ] **Step 7: Run the full frontend test suite**

```bash
cd /workspace/ui && npx vitest run 2>&1 | tail -20
```
Expected: all tests pass

- [ ] **Step 8: TypeScript final check**

```bash
cd /workspace/ui && npx tsc --noEmit 2>&1 | head -30
```
Expected: no new errors

---

## Post-implementation Checklist

- [ ] All backend tests pass: `cd /workspace/api && python -m pytest tests/ -v`
- [ ] All frontend tests pass: `cd /workspace/ui && npx vitest run`
- [ ] TypeScript compiles clean: `cd /workspace/ui && npx tsc --noEmit`
- [ ] App loads in Docker: `docker compose up --build` and visit http://localhost:3000
- [ ] Settings button shows "Settings" label
- [ ] Settings modal has two tabs: "Templates" and "System Prompts"
- [ ] System Prompts tab shows Chat and Summary cards with editable textareas
- [ ] Save and Reset to default work on each card independently
- [ ] Chat and Summary in a READY entry use the DB-backed prompts (verify by editing a prompt and checking LLM output changes)
