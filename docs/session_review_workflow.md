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
./rag-env/bin/python scripts/dm_query.py review-status
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

Each drafted event starts as:

```yaml
decision: pending
applied_status: pending
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

## Added Items

Use `added_items` for missing events, facts, or other review decisions:

```yaml
added_items:
  - id: added-001
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

AI drafts the memory. The user canonizes it. The database changes only after review decisions are recorded.
