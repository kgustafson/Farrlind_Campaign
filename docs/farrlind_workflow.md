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
  -> production parallel transcription, for recorded session audio
       -> split audio into chunks
       -> transcribe chunks with two faster-whisper workers
       -> stitch transcript text
       -> write raw transcript
  -> plain worker skeleton, for future structured audio orchestration
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

Audio ingestion now has a production parallel transcription command. The broader workflow still treats generated transcripts as source material that must be reviewed downstream.

## Plain Worker Skeleton

`v0.2.0` introduced a plain Python worker skeleton under:

```text
src/farrlind_pipeline/
```

This is a deterministic worker pipeline, not a LangGraph implementation. It exists to prove the worker boundaries, structured data contracts, and intermediate file layout before adding heavier orchestration.

The current skeleton runs:

```text
split -> transcribe_parallel placeholder -> stitch -> validate placeholder
```

Run it from the repo root with:

```bash
PYTHONPATH=src ./rag-env/bin/python -m farrlind_pipeline.pipeline.simple_runner audio/sessionXX.wav --session-id sessionXX --work-dir data/outputs/sessionXX
```

Current worker modules:

| Worker | Module | Purpose | Output |
| --- | --- | --- | --- |
| split | `farrlind_pipeline.audio.split` | Builds chunk metadata for an audio file. WAV duration is detected when possible. | `chunks/chunk_manifest.json` |
| transcribe_parallel placeholder | `farrlind_pipeline.transcription.transcribe_parallel` | Writes deterministic placeholder transcript JSON per chunk using a worker pool. | `transcripts/chunk-XXXX.json` |
| stitch | `farrlind_pipeline.transcription.stitch` | Sorts chunk transcripts, detects missing/duplicate chunks, and writes stitched transcript artifacts. | `stitched/stitched_transcript.md`, `stitched/stitched_transcript.json` |
| validate placeholder | `farrlind_pipeline.validation.validate` | Writes a placeholder quality report and marks placeholder transcripts as needing review. | `validation/validation_report.json`, `validation/validation_report.md` |

Shared Pydantic schemas live in:

```text
src/farrlind_pipeline/models/schemas.py
```

The skeleton produces structured intermediate JSON and Markdown so failed chunks can later become retryable without rerunning the entire pipeline.

## Transcription Architecture Benchmark

`v0.2.3` added an isolated benchmark harness for comparing transcription architecture choices without touching campaign outputs.

`v0.2.9` promoted the two-worker parallel path into the normal campaign workflow:

```bash
./rag-env/bin/python scripts/rag.py transcribe sessionXX
```

By default this reads:

```text
audio/sessionXX.wav
```

and writes:

```text
knowledge/Faban/raw/sessionXX_transcript.txt
```

The production defaults are `large-v3`, `180` second chunks, and `2` workers.

Run the full session20 benchmark from the repo root with:

```bash
./rag-env/bin/python scripts/benchmark_transcription_architectures.py audio/session20.wav --session-id session20 --architecture both --model large-v3 --chunk-seconds 180 --max-workers 2
```

The benchmark compares:

- `existing_sequential`: the current `scripts/transcribe.py` style, using one model instance and sequential chunks.
- `parallel_workers`: the production worker strategy that materializes chunks in an isolated directory and transcribes chunks with a process worker pool.

Benchmark outputs are written under ignored paths:

```text
benchmarks/transcription/sessionXX/<timestamp>/
  -> existing/existing_transcript.txt
  -> parallel/chunk_manifest.json
  -> parallel/chunks/chunk-XXXX.wav
  -> parallel/chunk_json/chunk-XXXX.json
  -> parallel/parallel_transcript.txt
  -> summary.json
  -> report.md
```

Use `--dry-run` to plan the run without writing output files. Use `--limit-seconds` for shorter smoke tests.

For the current large-v3 CPU benchmark, the parallel architecture defaults to two workers. Treat two workers as the normal local default because it captured most of the speedup without pushing as close to contention. Three workers remains available for explicit comparison runs, but is not the recommended default.

## Canon Safety Rules

- AI-generated output is draft material.
- `knowledge/Faban/clean/sessionXX_summary.md` is an ingest summary, not final canon.
- Reviewed canon summaries live in `knowledge/Faban/final/sessionXX_summary.md`.
- Automated reruns must never overwrite reviewed or applied canon.
- Any canon-changing rerun must return to human review before it can become canon.
- Human review decisions are part of the session record and should remain inspectable.

## NPC Registry Flow

NPC canon is maintained through the same reviewed-canon load path as sessions and locations.

- New or corrected NPCs should first be captured in session review decisions or the reviewed canon scrub list in `scripts/load_summaries.py`.
- `scripts/rag.py dbload --apply` runs the NPC scrub and updates/inserts canonical NPC rows.
- NPC fields currently preserved by the load path include name, alias, status, last known location, first-seen session, description, named/unnamed flag, and notes.
- First-seen corrections are intentional canon decisions. The load path may move an NPC earlier when review establishes that the NPC appeared in an earlier session.
- The web NPC Registry edits the database view of those records, but future durable canon updates should still be reflected back into reviewed summaries or the scrub list so reloads do not lose them.

## Artifact Registry Flow

Artifact canon is partly maintained through the reviewed-canon load path and partly through the artifact registry.

- `scripts/load_summaries.py` tracks first mentions for known artifacts and updates `artifact.discovered_session` during `scripts/rag.py dbload --apply`.
- Rich artifact fields such as type, description, lore significance, sentient/cursed/infernal flags, and notes are editable in the web Artifact Registry.
- Current holder is read from the latest `artifact_custody` row when available.
- Durable artifact canon should eventually be promoted into reviewed summaries, a reviewed artifact scrub list, or explicit custody records so future reloads preserve manual edits.

## Wells of Magic Lore Flow

The Wells of Magic lore section is a single editable Markdown canon note:

```text
knowledge/Faban/lore/wells_of_magic.md
```

The web page at `/wells` edits that file directly. Use it for consolidated Well lore, rules, open questions, and current understanding that cuts across sessions.

## Stage Definitions

| Stage | Command | Input | Output | Canon Impact | Gate |
| --- | --- | --- | --- | --- | --- |
| worker skeleton | `PYTHONPATH=src ./rag-env/bin/python -m farrlind_pipeline.pipeline.simple_runner ...` | source audio | chunk manifest, placeholder chunk transcripts, stitched transcript, validation report | draft only | experimental, safe to rerun |
| status | `scripts/rag.py status sessionXX` | expected artifact paths | artifact presence report | none | safe anytime |
| transcribe | `scripts/rag.py transcribe sessionXX` | audio | `raw/sessionXX_transcript.txt` | source material | rerun before review |
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

Plain worker skeleton artifacts:

```text
audio/sessionXX.wav
  -> data/outputs/sessionXX/chunks/chunk_manifest.json
  -> data/outputs/sessionXX/transcripts/chunk-XXXX.json
  -> data/outputs/sessionXX/stitched/stitched_transcript.md
  -> data/outputs/sessionXX/stitched/stitched_transcript.json
  -> data/outputs/sessionXX/validation/validation_report.json
  -> data/outputs/sessionXX/validation/validation_report.md
```

Production transcription artifacts:

```text
audio/sessionXX.wav
  -> knowledge/Faban/raw/sessionXX_transcript.txt
```

Existing RAG and canon artifacts:

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

- Plain Python worker skeleton: `src/farrlind_pipeline/pipeline/simple_runner.py`
- Transcription architecture benchmark: `scripts/benchmark_transcription_architectures.py`
- CLI pipeline: `scripts/rag.py`
- CLI canon/review commands: `scripts/dm_query.py`
- Web review app: FastAPI/Jinja app in `web_review/`
- Docker Compose runtime: `farrlind/docker-compose.yml`

The web app should become the main operator surface over time, but the workflow definition should remain explicit, deterministic, and inspectable.

## Phase 2 Work

Phase 2 is not greenfield. It should formalize the existing workflow into a machine-readable definition that can power the web UI.

Near-term tasks:

1. Extend the plain Python worker skeleton from placeholders to real transcription workers.
2. Create a canonical workflow definition from the stage table above.
3. Decide whether the definition should be YAML, Python data, database seed data, or a combination.
4. Map each workflow step to command, inputs, outputs, dependencies, and gate rules.
5. Define database persistence for per-session workflow state.
6. Keep `scripts/rag.py`, `src/farrlind_pipeline/`, and the workflow definition from drifting.
7. Update the web UI only after the workflow rules are explicit enough to display.
