# Archive Ready Entries Design

Date: 2026-04-03
Repository: `nezhar/voicevault`
Related issue: `#3`

## Context

Issue #3 asked for an archive page so older entries and transcripts remain accessible. After reviewing the current application and clarifying the desired workflow, the chosen direction is not a separate archive page. Instead, archive becomes an organizational state for `READY` entries inside the existing entries view.

This keeps the current pagination behavior, avoids duplicating list UI, and fits the user's preferred interaction model: an action near `Delete` that archives a video and a filter that shows archived entries.

## Goals

- Allow users to archive entries that are already `READY`.
- Keep the default view focused on active, non-archived entries.
- Let users switch to an archived view using a simple filter.
- Reuse the existing paginated entries list and search flow.
- Allow archived entries to be restored with an `Unarchive` action.

## Non-Goals

- Introducing a dedicated `/archive` page.
- Archiving entries in `NEW`, `IN_PROGRESS`, `COMPLETE`, or `ERROR` states.
- Changing transcript generation or chat semantics.
- Reworking the existing pagination pattern.

## User Experience

### Toolbar

The main entries toolbar will gain an archive filter beside the existing search and add controls. The filter will expose two states:

- `Active`: shows non-archived entries.
- `Archived`: shows archived entries.

The default state on page load is `Active`.

Search remains available in both views and continues to search within the currently selected archive state.

### Entry Card Actions

Entry cards in the active view will show an `Archive` action when the entry is `READY` and not already archived.

Entry cards in the archived view will show an `Unarchive` action for archived entries.

The archive action should be visually similar in weight and placement to the existing delete action, but should not use destructive styling because it is reversible.

### Behavior After an Action

When a user archives an entry while viewing `Active`, the entry should disappear from that list immediately after success.

When a user unarchives an entry while viewing `Archived`, the entry should disappear from that list immediately after success.

The user should not be forced into a full page reload. The UI can either update local state or re-fetch the current filtered list after mutation, but the result must remain consistent with the selected filter and search query.

## Data Model

Add a new boolean field to `Entry`:

- `archived: bool = False`

This field is independent of `status`. `status` continues to describe processing lifecycle, while `archived` only controls list organization.

Existing entries should default to `False`.

## API Design

### List Entries

Extend `GET /api/entries/` with a new query parameter:

- `archived: boolean`, default `false`

The endpoint continues to accept:

- `page`
- `per_page`
- `search`

Filtering happens before pagination so page counts reflect the selected archive state.

### Update Archive State

Add a dedicated endpoint:

- `PUT /api/entries/{entry_id}/archive`

Request body:

```json
{
  "archived": true
}
```

Rules:

- Setting `archived` to `true` is only valid when the entry status is `READY`.
- Setting `archived` to `false` is allowed for archived entries so they can be restored.
- If the entry does not exist, return `404`.
- If the archive request violates the `READY` requirement, return `400`.

The response returns the updated `EntryResponse`, including the new `archived` field.

### Response Schema

`EntryResponse` must include:

- `archived: bool`

The list response structure otherwise remains unchanged.

## Frontend Design

### State

The UI needs one additional piece of list state:

- current archive filter: active vs archived

This filter must be included whenever the client fetches entries.

### Data Loading

The existing list loading flow can remain in place, but the archive filter becomes part of the fetch key alongside:

- page
- search query

Changing the archive filter resets pagination to the first page, just like changing the search query should.

### Mutation Handling

Add an API client method for updating archive state.

On a successful archive or unarchive action:

- remove the entry from the currently visible list if it no longer matches the selected filter
- update totals accordingly
- keep the selected chat entry closed if it was removed from the visible list only because of archive state change; no additional special handling is required unless the product wants the chat modal to remain open

Archived entries remain `READY`, so existing chat behavior can continue to work when those entries are visible in the archived filter.

## Backend Validation and Error Handling

- Reject archive requests for non-`READY` entries with a clear `400` error message.
- Preserve existing list ordering: newest first by `created_at`, then `id`.
- Do not overload the existing `COMPLETE` status to mean archived.

## Testing Strategy

### Backend

Add tests covering:

- default list behavior excludes archived entries
- archived filter returns only archived entries
- search still works within the selected archive state
- archiving a `READY` entry succeeds
- archiving a non-`READY` entry fails with `400`
- unarchiving an archived entry succeeds

### Frontend

Add tests covering:

- the archive filter triggers list reload with the correct query parameter
- `Archive` appears only for eligible active entries
- `Unarchive` appears in the archived view
- successful archive and unarchive actions remove items from the current list

## Implementation Notes

- The repository already uses paginated entry fetching, so this change should extend that path rather than introduce a parallel archive screen.
- The repository includes Alembic migrations; adding the `archived` column should follow the existing migration workflow instead of relying on implicit schema drift.
- The current issue wording mentioned “entries and their transcriptions in a paginated format.” Under the approved design, archived entries remain accessible through the archived filter and continue to expose transcripts through the existing entry card and chat flows.

## Open Decisions Resolved During Brainstorming

- Archive applies only to `READY` videos.
- Archive is reversible via `Unarchive`.
- Pagination stays on the existing entries view instead of moving to a separate archive page.
