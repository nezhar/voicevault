# Prompt Template Manager Design

Date: 2026-04-03
Repository: `nezhar/voicevault`
Related issue: `#2`

## Context

Issue #2 asks for a prompt template manager to improve repeated chat tasks. The current codebase does not have an existing keyword or prompt-template management system. The closest current behavior is the hardcoded suggested questions in the chat modal.

After clarifying the intended workflow, the chosen direction is:

- prompt templates are managed in a separate global area, not inline in chat
- templates are used from the chat interface
- templates contain markdown content
- chat users should be able to either prefill the composer or use the template and send it immediately
- chat should not render the full template body inline in the starter list
- a modal preview should render the full markdown body on demand

## Goals

- Add a global prompt-template library stored in the database
- Seed a small starter set of templates on first startup
- Provide a lightweight management UI for add, edit, delete, and activate/deactivate
- Extend the chat starter area to support both simple starter prompts and managed templates
- Preserve fast chat usage with a dominant `Use & Send` action

## Non-Goals

- User-specific templates or permissions
- Rich collaboration, history, or versioning for templates
- A full settings subsystem beyond the prompt-template manager
- Hiding the actual sent template content from the chat transcript

## Product Decisions

- Templates are global because the app has no real user model
- The manager entry point is a floating settings button fixed to the bottom-left of the app shell
- Templates are authored in markdown
- Each template record includes:
  - `label`
  - optional `preview_text`
  - `body_markdown`
  - `sort_order`
  - `is_active`
- Chat supports two template actions:
  - `Use & Send` as the primary action
  - `Use Only` as the secondary action

## User Experience

### Entry Point

Add a floating settings button in the main authenticated app shell. It should:

- stay fixed while the main page scrolls
- be visually distinct from entry actions
- use safe-area spacing so it does not collide with browser chrome on smaller screens

This button opens the prompt-template manager.

### Prompt Template Manager

The manager can be implemented as a modal to match the app’s current interaction style. It should include:

- a list of existing prompt templates
- add button
- edit action
- delete action
- activate/deactivate toggle
- ordering support through `sort_order`

The edit form should include:

- label input
- optional preview text input
- markdown body editor
- live markdown preview

The goal is usability, not a full WYSIWYG editor. A textarea plus rendered preview is sufficient for this project.

### Chat Starter Area

The current chat modal shows hardcoded suggested questions. This becomes a mixed starter area containing:

- built-in short prompts that behave as they do now
- managed prompt-template cards loaded from the API

Template cards should remain compact and show only:

- label
- short preview text
- actions

The full markdown body must not be rendered inline in the starter list.

### Template Actions in Chat

Each template card should support:

- `Use & Send`
- `Use Only`
- `Preview`

Behavior:

- `Use Only` fills the composer with the full template markdown
- `Use & Send` sends the full markdown body immediately as the user message
- `Preview` opens a modal rendering the full markdown body

This preserves usability while avoiding hidden behavior. The actual content sent to the AI remains visible in the chat transcript after send.

## Data Model

Add a new database entity, `PromptTemplate`, with fields:

- `id`
- `label`
- `preview_text` nullable
- `body_markdown`
- `sort_order`
- `is_active`
- `created_at`
- `updated_at`

Constraints:

- `label` required and non-empty
- `body_markdown` required and non-empty
- default `is_active = true`
- default `sort_order = 0`

## API Design

Add CRUD endpoints under `/api/prompt-templates`.

Recommended endpoints:

- `GET /api/prompt-templates`
- `POST /api/prompt-templates`
- `PUT /api/prompt-templates/{id}`
- `DELETE /api/prompt-templates/{id}`

The list endpoint should return active and inactive templates so the manager can control visibility. If needed, the frontend can filter inactive templates out of the chat starter area client-side, or the API can support an `active_only` query parameter.

For chat usage, only active templates should be shown in the starter area.

## Startup Seeding

On startup, seed a small set of default templates if and only if no prompt templates exist yet.

This seeding must be idempotent:

- do not duplicate defaults on later startups
- do not overwrite edited templates

## Frontend Structure

### New Components

Recommended additions:

- `PromptTemplateManager`
- `PromptTemplateForm`
- `PromptTemplatePreviewModal`
- `FloatingSettingsButton`

Where practical, these can remain small modal-oriented components rather than introducing a large settings module.

### State and Data Loading

At the app shell level:

- manage whether the prompt-template manager is open
- fetch templates when the manager opens and when chat needs starter data

At the chat modal level:

- merge built-in prompts with active managed templates
- handle template preview modal state
- support immediate send and prefill flows

## Error Handling

- If prompt-template loading fails, chat must still work with built-in starter prompts
- Manager mutation failures should show inline error state and preserve current form input
- Invalid template submissions should return clear validation errors from the API

## Testing Strategy

### Backend

Add tests for:

- prompt-template CRUD operations
- validation for required label and markdown body
- stable ordering by `sort_order`
- seed logic runs only when the table is empty

### Frontend

Add tests for:

- manager open and list rendering
- create and edit form behavior
- preview modal rendering markdown
- chat starter rendering of template cards
- `Use Only` prefills composer
- `Use & Send` sends full body immediately
- inactive templates do not appear in chat starters

## Implementation Notes

- The current app is modal-heavy, so a modal manager is preferable to a new standalone page
- The current issue mentions keywords and descriptions, but the clarified product shape is better represented as named markdown prompt templates plus optional preview text
- The current suggested questions in chat should remain as lightweight built-in prompts rather than being forced into database records

## Open Decisions Resolved During Brainstorming

- Templates are managed in a separate area, not inline in chat
- Templates are global, not user-specific
- Templates are markdown-based
- Chat supports both prefill and immediate send, with immediate send as the dominant option
- The entry point is a floating settings button fixed to the bottom-left of the app shell
