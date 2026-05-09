# AI RAG Campaign Workflow

Local pipeline for turning session audio/transcripts into cleaned campaign artifacts.

## Common Commands

Run commands from the repo root:

```bash
./rag-env/bin/python scripts/rag.py status session20
./rag-env/bin/python scripts/rag.py extract session20
./rag-env/bin/python scripts/rag.py postextract session20
```

`postextract` runs:

```text
filter -> classify -> normalize -> merge -> validate -> summarize
```

Use `status` before rerunning a session to see which artifacts already exist.

## Web Review App

Run the database, Adminer, and the Farrlind review UI with Docker Compose:

```bash
cd farrlind
docker compose up --build -d
```

Then open:

```text
http://127.0.0.1:8000
```

The web container bind-mounts the repo into `/app`, so review and canon files written by the UI persist in the working tree.

## Artifact Flow

```text
audio/session20.wav
  -> knowledge/Faban/raw/session20_transcript.txt
  -> knowledge/Faban/clean/session20_events.md
  -> knowledge/Faban/clean/session20_filtered.md
  -> knowledge/Faban/clean/session20_classified.md
  -> knowledge/Faban/clean/session20_normalized.md
  -> knowledge/Faban/clean/session20_merged.md
  -> knowledge/Faban/clean/session20_validation.md
  -> knowledge/Faban/clean/session20_summary.md
```

Session-specific correction and normalization context lives in:

```text
knowledge/Faban/sessions/session20_context.yaml
knowledge/Faban/notes/session20_corrections.md
```

## Review Workflow

AI-generated events and summaries are drafts until reviewed.

See [Session Review Workflow](docs/session_review_workflow.md) for the human review loop:

```text
init-review -> edit review YAML -> review-status -> apply review -> health
```
