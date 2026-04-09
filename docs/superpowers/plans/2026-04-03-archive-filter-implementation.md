# Archive Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reversible archiving for `READY` entries and an archived filter in the existing paginated entries view.

**Architecture:** Extend the `Entry` persistence model with an `archived` flag, expose filtering and archive mutation through the existing entries API, and update the React list view to switch between active and archived entries without adding a separate page. Keep the implementation small by reusing the current fetch, pagination, and card patterns.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, React, TypeScript, Vite

---

### Task 1: Backend archive persistence and API

**Files:**
- Create: `api/alembic/versions/<new>_add_archived_flag_to_entries.py`
- Create: `api/tests/test_entry_archive.py`
- Modify: `api/app/models/entry.py`
- Modify: `api/app/models/schemas.py`
- Modify: `api/app/services/entry_service.py`
- Modify: `api/app/api/routes/entries.py`

- [ ] **Step 1: Write the failing backend tests**

Create API/service tests for:
- default list excludes archived entries
- archived filter returns archived entries
- archiving a `READY` entry succeeds
- archiving a non-`READY` entry returns `400`
- unarchiving succeeds

- [ ] **Step 2: Run the backend tests to verify RED**

Run: `python -m pytest api/tests/test_entry_archive.py -q`
Expected: fail because the archive field and endpoints do not exist yet

Note: this environment currently does not provide Python, so execution may need to happen in a Python-capable shell.

- [ ] **Step 3: Write the minimal backend implementation**

Implement:
- `archived` column on `Entry` with default `False`
- schema support for `archived` and archive update payload
- service filtering by archive state
- service method to update archive state with `READY` validation
- route query param for `archived`
- archive update endpoint
- Alembic migration for existing databases

- [ ] **Step 4: Run the backend tests to verify GREEN**

Run: `python -m pytest api/tests/test_entry_archive.py -q`
Expected: pass

- [ ] **Step 5: Commit backend slice**

```bash
git add api/app/models/entry.py api/app/models/schemas.py api/app/services/entry_service.py api/app/api/routes/entries.py api/alembic/versions api/tests/test_entry_archive.py
git commit -m "feat: add entry archive support"
```

### Task 2: Frontend archive filter and card actions

**Files:**
- Create: `ui/src/components/EntryCard.test.tsx`
- Modify: `ui/package.json`
- Modify: `ui/src/App.tsx`
- Modify: `ui/src/components/EntryCard.tsx`
- Modify: `ui/src/components/EntryList.tsx`
- Modify: `ui/src/services/api.ts`
- Modify: `ui/src/types/index.ts`

- [ ] **Step 1: Write the failing frontend test**

Add a component test that proves:
- `Archive` shows only for active `READY` entries
- `Unarchive` shows for archived entries
- non-`READY` entries do not show archive actions

- [ ] **Step 2: Run the frontend test to verify RED**

Run: `cd ui && npm test -- EntryCard.test.tsx`
Expected: fail because test tooling or archive UI is missing

- [ ] **Step 3: Write the minimal frontend implementation**

Implement:
- `archived` field in shared entry types
- `archived` query parameter in the list API
- archive update API client method
- active/archived filter state in `App.tsx`
- filter-aware fetch/reset behavior
- archive/unarchive action button in `EntryCard`
- filter-aware headings in `EntryList`

- [ ] **Step 4: Run the frontend tests to verify GREEN**

Run: `cd ui && npm test -- EntryCard.test.tsx`
Expected: pass

- [ ] **Step 5: Run production build verification**

Run: `cd ui && npm run build`
Expected: exit 0

- [ ] **Step 6: Commit frontend slice**

```bash
git add ui/package.json ui/src/App.tsx ui/src/components/EntryCard.tsx ui/src/components/EntryList.tsx ui/src/services/api.ts ui/src/types/index.ts ui/src/components/EntryCard.test.tsx
git commit -m "feat: add archive filter to entry list"
```

### Task 3: Final verification

**Files:**
- Verify current worktree diff only

- [ ] **Step 1: Run backend verification if Python is available**

Run: `python -m pytest api/tests/test_entry_archive.py -q`
Expected: pass

- [ ] **Step 2: Run frontend verification**

Run: `cd ui && npm test -- --run`
Expected: pass

- [ ] **Step 3: Run frontend production build**

Run: `cd ui && npm run build`
Expected: exit 0

- [ ] **Step 4: Review the diff**

Run: `git status --short && git diff --stat`
Expected: only the archive feature files changed in this worktree
