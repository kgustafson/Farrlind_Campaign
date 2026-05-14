# AI RAG Campaign Workflow

Local pipeline for turning Farrlind source material into reviewed, queryable campaign canon.

The canonical workflow reference is [Farrlind Campaign Workflow](docs/farrlind_workflow.md).

## Common Commands

Run commands from the repo root:

```bash
./rag-env/bin/python scripts/rag.py status session20
./rag-env/bin/python scripts/rag.py transcribe session20
./rag-env/bin/python scripts/rag.py extract session20
./rag-env/bin/python scripts/rag.py postextract session20
```

`postextract` runs:

```text
filter -> classify -> normalize -> merge -> validate -> summarize
```

Use `status` before rerunning a session to see which artifacts already exist. The `transcribe` command uses the production parallel transcription path with two workers by default.

Parallel transcription defaults:

```text
audio/sessionXX.wav -> knowledge/Faban/raw/sessionXX_transcript.txt
model: large-v3
chunk size: 180 seconds
workers: 2
```

## Plain Worker Pipeline Skeleton

The initial deterministic worker skeleton runs:

```text
split -> transcribe_parallel placeholder -> stitch -> validate placeholder
```

Run it from the repo root with:

```bash
PYTHONPATH=src ./rag-env/bin/python -m farrlind_pipeline.pipeline.simple_runner audio/sessionXX.wav --session-id sessionXX --work-dir data/outputs/sessionXX
```

This is intentionally plain Python. LangGraph is not implemented yet.

## Transcription Architecture Benchmark

Use the isolated benchmark harness to compare the older sequential transcription path against the production parallel worker path without touching campaign outputs:

```bash
./rag-env/bin/python scripts/benchmark_transcription_architectures.py audio/session20.wav --session-id session20 --architecture both --model large-v3 --chunk-seconds 180 --max-workers 2
```

Benchmark artifacts are written under ignored `benchmarks/transcription/` directories.

The benchmark defaults to two parallel workers. Treat two workers as the normal local default for `large-v3`; three workers remains available for explicit comparison runs, but is not the recommended default.

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

The interface can run in either edit mode or read-only archive mode. Copy `farrlind/.env.example` to `farrlind/.env` and set:

```text
FARRLIND_INTERFACE_MODE=edit
```

or:

```text
FARRLIND_INTERFACE_MODE=archive
```

Archive mode hides edit controls and rejects mutating requests, which is intended for a hosted viewer copy.

## Artifact Flow

The full artifact map and canon safety rules live in [Farrlind Campaign Workflow](docs/farrlind_workflow.md).

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

See [Farrlind Campaign Workflow](docs/farrlind_workflow.md) for the end-to-end workflow and [Session Review Workflow](docs/session_review_workflow.md) for the focused human review guide:

```text
init-review -> edit review YAML -> review-status -> apply review -> health
```
