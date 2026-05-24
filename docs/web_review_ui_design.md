# Web Review UI Design

Goal: replace direct YAML editing with a local web interface that keeps the review workflow constrained, visible, and hard to accidentally corrupt.

## Product Shape

The first version should be a local DM review workbench, not a public app.

- Runs locally against this repo and the local Farrlind Postgres container.
- Reads/writes the existing review YAML files.
- Uses the same durable apply path as the CLI: `apply-review`, `dbload --apply`, and `write-final-summary`.
- Keeps the database as generated state, not the source of human decisions.

The UI should make canon review feel like approving and correcting index cards, not editing a config file.

## Primary Workflow

1. Pick a session from the review dashboard.
2. See source summary, current DB events, existing review items, and final summary status.
3. Review each item with constrained choices:
   - accept
   - reject
   - correct
   - add missing item
4. Edit only the fields relevant to the chosen decision.
5. Validate that no required fields are missing.
6. Mark the review as reviewed.
7. Apply review.
8. Generate final summary.
9. Show health/status result.

The key interaction model is staged inline editing: the user can edit review items while reading, save the review draft, inspect it again, then explicitly promote it toward canon.

```text
Edit inline -> Save Review -> Mark Reviewed -> Apply to Database -> Write Final Summary
```

There is no autosave in v1.

## Screens

### 1. Review Dashboard

Purpose: answer "what needs attention?"

Content:

- Session list from session00 through latest known session.
- Status columns:
  - review file exists
  - review status: missing, in_review, reviewed, applied
  - pending decisions
  - unapplied decisions
  - final summary exists
  - event count
- Quick filters:
  - Needs review
  - Ready to apply
  - Applied
  - Has health notes
- Actions:
  - Initialize review
  - Open review
  - Apply
  - Write final summary

Design notes:

- This should feel like an operations table, not a landing page.
- Use compact rows, clear status badges, and icon buttons with tooltips.

### 2. Session Review Workspace

Purpose: do the actual canon decision work.

Layout:

- Left column: source context
  - source switcher: Diary, Draft Summary, Final Summary
  - diary text if available
  - draft/source summary
  - current final summary if it exists
- Main column: review item list
  - one item per event/fact
  - sequence number visible and editable
  - decision segmented control
  - canonical text editor when corrected/added
  - event type select
  - location select
  - significance stepper
  - reason field
  - applied status
- Right column: session metadata and validation
  - title
  - dates
  - primary location
  - review status
  - missing required fields
  - duplicate sequence warnings
  - location not found warnings

Core controls:

- Decision segmented control: `Accept`, `Reject`, `Correct`, `Add`
- Event type select using current event types.
- Location combobox using canonical locations, with typed new values prompting an explicit add-location action.
- Significance as 1-5 stepper or compact segmented control.
- Sequence as numeric input that supports decimals.
- Save Review button for staged inline edits.
- Discard Changes button for unsaved staged edits.

Source switcher:

```text
[ Diary ] [ Draft Summary ] [ Final Summary ]
```

Switching sources must not navigate away or discard edits. It only changes the left source pane.

Location creation:

```text
"Road to Fey Woods" is not in canon locations.
[ Add Location ] [ Cancel ]
```

Adding a location should not directly insert into the database. It marks the location as review-introduced so the durable load path can create it when applied.

### 3. Add Item Dialog

Purpose: add missing canon without hand-writing YAML structure.

Fields:

- sequence
- canonical text
- event type
- location
- significance
- reason
- source type defaults to `user_added`
- decided by defaults to `user`
- decided date defaults to today

The dialog should produce a valid `added_items` entry.

### 4. Apply Review Screen

Purpose: make applying feel deliberate.

Pre-apply checks:

- no pending decisions
- every corrected/added item has canonical text
- all locations resolve or are explicitly introduced by review
- no duplicate item IDs
- review status is `reviewed`

Actions:

- Save Review
- Mark Reviewed
- Apply to Database
- Write Final Summary
- Run Health Check

Show command output in a collapsible log panel.

Apply and final-summary generation remain separate buttons. The user may save and reread a review multiple times before publishing.

### 5. Canon Explorer

Purpose: verify what the review produced.

Tabs:

- Final summaries
- Travel log
- NPCs
- Enemy encounters
- General encounters
- Songs

This is read-only for v1. It helps answer "did the DB now reflect the review?"

## Data Sources

Existing files:

- `campaigns/{campaign}/reviews/sessionXX_review.yaml`
- `campaigns/{campaign}/final/sessionXX_summary.md`
- `campaigns/{campaign}/travel.yaml`
- `campaigns/{campaign}/enemy_encounters.yaml`
- `campaigns/{campaign}/encounters.yaml`
- `campaigns/{campaign}/canon_decisions.yaml`

Existing commands:

- `scripts/dm_query.py init-review sessionXX`
- `scripts/dm_query.py review-status`
- `scripts/dm_query.py review-events sessionXX`
- `scripts/dm_query.py apply-review sessionXX`
- `scripts/dm_query.py write-final-summary sessionXX`
- `scripts/dm_query.py health`
- `scripts/rag.py dbload --apply`

Postgres read models:

- `session`
- `session_event`
- `location`
- `npc`
- `enemy`
- `event_enemy`
- `encounter`
- `travel_log`

## Proposed Local Architecture

Use a small Python web service plus a simple frontend.

Recommended stack:

- Backend: FastAPI
- Templates/UI: server-rendered Jinja, with a small amount of vanilla JavaScript or HTMX for source switching and staged inline edits
- DB reads: SQLAlchemy against the local Postgres container
- Styling: plain CSS with a restrained dashboard layout
- YAML: PyYAML, preserving our current file shape
- Command execution: existing CLI commands for apply/final/health

Why this shape:

- Fast to build.
- Easy to keep local.
- Does not require a heavy frontend build pipeline.
- Gives the user a chance to learn FastAPI while keeping familiar Jinja rendering.
- SQLAlchemy provides clean read models for canon state.
- Existing scripts remain the trusted write/apply path.

Suggested paths:

```text
web_review/
  app.py
  db.py
  models.py
  schemas.py
  services/
    reviews.py
    commands.py
    canon.py
  templates/
    base.html
    dashboard.html
    session_review.html
    partials/
  static/
    review.css
tests/
  test_web_review.py
```

## Backend Endpoints

Read endpoints:

- `GET /`
  - dashboard
- `GET /sessions/{session}/review`
  - review workspace
- `GET /api/review-status`
- `GET /api/sessions/{session}/review`
- `GET /api/sessions/{session}/source`
- `GET /api/sessions/{session}/final`
- `GET /api/locations`
- `GET /api/event-types`

Write endpoints:

- `POST /api/sessions/{session}/init-review`
- `PATCH /api/sessions/{session}/review/metadata`
- `PATCH /api/sessions/{session}/review/items/{item_id}`
- `POST /api/sessions/{session}/review/items`
- `DELETE /api/sessions/{session}/review/items/{item_id}`
- `POST /api/sessions/{session}/mark-reviewed`
- `POST /api/sessions/{session}/apply`
- `POST /api/sessions/{session}/write-final-summary`
- `POST /api/health`

Write rules:

- Never write directly to DB from UI review actions.
- UI edits only review YAML.
- Applying review uses the same command path as CLI.
- Final summaries are generated, not hand-edited.
- Applied reviews require an explicit reopen/edit action before inline editing is enabled.

## Validation Rules

For every review:

- top-level `status` must be one of `in_review`, `reviewed`, `applied`
- every item decision must be one of `accepted`, `rejected`, `corrected`, `added`
- no `pending` decisions before apply
- `corrected` and `added` require canonical text
- `corrected` and `added` require event type, location, significance, reason
- sequence values must be unique after sorting numerically
- added item IDs must be unique
- locations must either exist in DB or be introduced by reviewed items
- typed combobox values for locations must be confirmed before saving
- applied reviews cannot be edited unless explicitly reopened

## V1 Implementation Plan

1. Add read-only dashboard.
   - Show sessions, review status, final summary status, pending counts.

2. Add session review workspace.
   - Load and render review YAML.
   - Show the source switcher for Diary, Draft Summary, and Final Summary.
   - No writes yet.

3. Add item editing.
   - Stage inline edits for decision, sequence, canonical text, event type, location, significance, reason.
   - Save staged edits to review YAML only when Save Review is clicked.
   - Preserve YAML shape.

4. Add add-item flow.
   - Generate `added-###` IDs.
   - Validate required fields.

5. Add review actions.
   - Save review.
   - Mark reviewed.
   - Apply review.
   - Write final summary.
   - Run health.

6. Add read-only canon explorer.
   - NPCs, travel, enemy encounters, general encounters.

## Non-Goals For V1

- User accounts
- Remote hosting
- Multi-campaign support
- Direct transcript/audio editing
- Full RAG pipeline orchestration
- Travel/enemy/general encounter YAML editors
- Rich text editor
- Drag-and-drop event ordering

## V1 Decisions

1. Source context is switchable between Diary, Draft Summary, and Final Summary.
2. Review items are editable inline with staged saves.
3. Location fields use comboboxes that allow typed values, but new locations require explicit confirmation.
4. Travel, enemy, and general encounter YAML editors are backlogged after v1, but are must-have eventual features.
5. Save Review, Mark Reviewed, Apply to Database, and Write Final Summary are separate actions.
6. Applied reviews are locked until explicitly reopened.
