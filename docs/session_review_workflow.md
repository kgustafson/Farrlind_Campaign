# Session Review Workflow

The campaign database should treat AI output as a draft, not canon.

Use this workflow after a session has been transcribed and run through the RAG pipeline.

## Flow

```text
audio
  -> transcript
  -> extraction/postextract
  -> draft summary and events
  -> review YAML
  -> human decisions
  -> apply review
  -> database update
  -> health check
```

## Commands

Run the normal pipeline first:

```bash
./rag-env/bin/python scripts/rag.py status sessionXX
./rag-env/bin/python scripts/rag.py extract sessionXX
./rag-env/bin/python scripts/rag.py postextract sessionXX
./rag-env/bin/python scripts/rag.py dbload --apply
```

Create a review file:

```bash
./rag-env/bin/python scripts/dm_query.py init-review sessionXX
```

Check review progress:

```bash
./rag-env/bin/python scripts/dm_query.py review-next
./rag-env/bin/python scripts/dm_query.py review-status
```

Apply a completed review:

```bash
./rag-env/bin/python scripts/dm_query.py apply-review sessionXX
./rag-env/bin/python scripts/dm_query.py health
```

View the final reviewed session packet:

```bash
./rag-env/bin/python scripts/dm_query.py session-final sessionXX
```

Write the canonical session summary:

```bash
./rag-env/bin/python scripts/dm_query.py write-final-summary sessionXX
```

Inspect a session beside canon decisions:

```bash
./rag-env/bin/python scripts/dm_query.py review-events sessionXX
```

## Review File

Review files live in:

```text
knowledge/Faban/reviews/sessionXX_review.yaml
```

Each review file starts as:

```yaml
status: in_review
```

Each drafted event starts as:

```yaml
sequence: 1
decision: pending
applied_status: pending
```

Use `sequence` to keep the final session chronology. You can use decimals for inserted facts:

```yaml
sequence: 4.5
```

Change `decision` to one of:

- `accepted`: the item is correct as-is.
- `rejected`: the item is wrong and should be removed or ignored.
- `corrected`: the item is partly right, but needs `canonical_text`.
- `added`: a user-added item that was missing from the draft.

For `corrected` or `added`, fill in the fields that should become canon:

```yaml
canonical_text: The corrected or added event text.
event_type: social
location: Coast near Catur
significance: 4
reason: Why this decision matters.
decided_by: user
decided_on: "YYYY-MM-DD"
```

Leave `applied_status: pending` until an apply step updates the database.

When every item has a decision and any corrections/additions are filled in, set the top-level review status to:

```yaml
status: reviewed
```

`apply-review` refuses reviews with pending decisions. After it successfully reloads the database, it marks the review and its decided items as applied.

## Added Items

Use `added_items` for missing events, facts, or other review decisions:

```yaml
added_items:
  - id: added-001
    sequence: 4.5
    source_type: user_added
    source_text: ''
    decision: added
    canonical_text: The party negotiated with fishermen for a vessel.
    event_type: social
    location: Coast near Catur
    significance: 4
    reason: Important setup for entering Catur.
    decided_by: user
    decided_on: "YYYY-MM-DD"
    applied_status: pending
    applied_on: ''
```

## Principle

AI drafts the memory. The user canonizes it. The ingest `sessionXX_summary.md` file is source material from the audio pipeline, not final truth. After review is applied, the canonical session summary lives in:

```text
knowledge/Faban/final/sessionXX_summary.md
```
