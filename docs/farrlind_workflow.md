# Farrlind Campaign Workflow

This is the canonical workflow reference for turning Farrlind source material into reviewed, queryable campaign canon.

The short rule:

```text
AI drafts the memory. The user canonizes it.
```

Generated transcripts, extracted events, draft summaries, and validation notes are source material. Canon changes only after human review and explicit apply/publish actions.

## End-To-End Flow

```text
source material
  -> transcript or diary source
  -> extract
  -> filter
  -> classify
  -> normalize
  -> merge
  -> validate
  -> summarize
  -> initialize review
  -> human decisions
  -> apply review
  -> write final summary
  -> database/canon health
```

Audio ingestion is intentionally upstream and later-phase work. The current stable workflow starts once a transcript, diary entry, or other source artifact exists.

## Canon Safety Rules

- AI-generated output is draft material.
- `knowledge/Faban/clean/sessionXX_summary.md` is an ingest summary, not final canon.
- Reviewed canon summaries live in `knowledge/Faban/final/sessionXX_summary.md`.
- Automated reruns must never overwrite reviewed or applied canon.
- Any canon-changing rerun must return to human review before it can become canon.
- Human review decisions are part of the session record and should remain inspectable.

## Stage Definitions

| Stage | Command | Input | Output | Canon Impact | Gate |
| --- | --- | --- | --- | --- | --- |
| status | `scripts/rag.py status sessionXX` | expected artifact paths | artifact presence report | none | safe anytime |
| extract | `scripts/rag.py extract sessionXX` | transcript | `clean/sessionXX_events.md` | draft only | rerun with care |
| filter | `scripts/rag.py filter sessionXX` | extracted events | `clean/sessionXX_filtered.md` | draft only | rerun with care |
| classify | `scripts/rag.py classify sessionXX` | filtered events | `clean/sessionXX_classified.md` | draft only | rerun with care |
| normalize | `scripts/rag.py normalize sessionXX` | filtered/classified events plus context | `clean/sessionXX_normalized.md` | draft only | rerun with care |
| merge | `scripts/rag.py merge sessionXX` | normalized events | `clean/sessionXX_merged.md` | draft only | rerun with care |
| validate | `scripts/rag.py validate sessionXX` | merged events and summary context | `clean/sessionXX_validation.md` | draft only | safe diagnostic |
| summarize | `scripts/rag.py summarize sessionXX` | merged events, diary, corrections | `clean/sessionXX_summary.md` | draft only | rerun with care |
| postextract | `scripts/rag.py postextract sessionXX` | filtered pipeline inputs | clean draft artifacts | draft only | rerun with care |
| dbload | `scripts/rag.py dbload --apply` | final summaries and canon files | database rows | can affect database | use intentionally |
| init review | `scripts/dm_query.py init-review sessionXX` | draft summary/events | `reviews/sessionXX_review.yaml` | none | starts human review |
| review status | `scripts/dm_query.py review-status` | review YAML | review progress report | none | safe anytime |
| review next | `scripts/dm_query.py review-next` | review YAML | next review action | none | safe anytime |
| apply review | `scripts/dm_query.py apply-review sessionXX` | reviewed decisions | database reload/update | canon-affecting | requires reviewed status |
| final packet | `scripts/dm_query.py session-final sessionXX` | database and review state | session report | none | safe anytime |
| write final summary | `scripts/dm_query.py write-final-summary sessionXX` | applied review/database state | `final/sessionXX_summary.md` | canon file output | requires applied review |
| health | `scripts/dm_query.py health` | database/canon state | health report | none | safe anytime |

`postextract` is the shortcut for:

```text
filter -> classify -> normalize -> merge -> validate -> summarize
```

## Artifact Map

```text
audio/sessionXX.wav
  -> knowledge/Faban/raw/sessionXX_transcript.txt
  -> knowledge/Faban/clean/sessionXX_events.md
  -> knowledge/Faban/clean/sessionXX_filtered.md
  -> knowledge/Faban/clean/sessionXX_classified.md
  -> knowledge/Faban/clean/sessionXX_normalized.md
  -> knowledge/Faban/clean/sessionXX_merged.md
  -> knowledge/Faban/clean/sessionXX_validation.md
  -> knowledge/Faban/clean/sessionXX_summary.md
  -> knowledge/Faban/reviews/sessionXX_review.yaml
  -> database canon rows
  -> knowledge/Faban/final/sessionXX_summary.md
```

Session-specific correction and normalization context lives in:

```text
knowledge/Faban/sessions/sessionXX_context.yaml
knowledge/Faban/notes/sessionXX_corrections.md
```

## Human Review Decisions

Review files live in:

```text
knowledge/Faban/reviews/sessionXX_review.yaml
```

Each review item receives one of these decisions:

- `accepted`: the item is correct as-is.
- `rejected`: the item is wrong and should be removed or ignored.
- `corrected`: the item is partly right, but needs `canonical_text`.
- `added`: a user-added item that was missing from the draft.

Every corrected or added item should include canonical text, event type, location, significance, reason, decision owner, and decision date.

Use `sequence` to preserve chronology. Decimal sequences are allowed for inserted facts:

```yaml
sequence: 4.5
```

When every item has a decision and required fields are filled in, the review can move to:

```yaml
status: reviewed
```

`apply-review` refuses reviews with pending decisions.

## Database State

The current schema already contains pipeline metadata tables:

- `pipeline_run`
- `extraction_confidence`

Phase 2 should decide whether these are enough or whether the app also needs explicit workflow-state tables for per-session step status.

Likely workflow-state needs:

- session id
- workflow id/version
- step id
- step status
- started/completed timestamps
- input artifact paths
- output artifact paths
- command result summary
- stale/missing artifact flags
- human gate status
- rerun eligibility

Workflow state should live in the database. YAML and Markdown files remain source/canon artifacts, not the primary state machine.

## Current Operator Surfaces

- CLI pipeline: `scripts/rag.py`
- CLI canon/review commands: `scripts/dm_query.py`
- Web review app: FastAPI/Jinja app in `web_review/`
- Docker Compose runtime: `farrlind/docker-compose.yml`

The web app should become the main operator surface over time, but the workflow definition should remain explicit, deterministic, and inspectable.

## Phase 2 Work

Phase 2 is not greenfield. It should formalize the existing workflow into a machine-readable definition that can power the web UI.

Near-term tasks:

1. Create a canonical workflow definition from the stage table above.
2. Decide whether the definition should be YAML, Python data, database seed data, or a combination.
3. Map each workflow step to command, inputs, outputs, dependencies, and gate rules.
4. Define database persistence for per-session workflow state.
5. Keep `scripts/rag.py` and the workflow definition from drifting.
6. Update the web UI only after the workflow rules are explicit enough to display.
