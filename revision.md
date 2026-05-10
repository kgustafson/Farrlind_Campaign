# Revision History

## v0.2.15 - 5/10/2026

Added database-backed session workflow state initialization.

- Schema: Added `workflow_run` and `workflow_step_state` tables for per-session workflow state, ordered step tracking, timestamps, comments, JSONB inputs/outputs, dependencies, commands, gates, rerun policy, status rules, and metadata.
- Workflow: Added `rag.py workflow-init sessionXX --apply` to seed a session workflow from `workflows/session_workflow.yaml`.
- Workflow: Kept YAML as the source of step definition/order while preserving runtime status, timestamps, and comments in the database.
- Tests: Added workflow-state coverage for session parsing, recursive session path rendering, schema fields, and generated initialization SQL.
- Docs: Updated the workflow reference and TODO plan to reflect the YAML-definition plus database-state model.

## v0.2.14 - 5/10/2026

Added the first machine-readable session workflow definition.

- Workflow: Added `workflows/session_workflow.yaml` with per-session intake, draft generation, human review, canonization, verification, and version-control steps.
- Workflow: Included newer lore/registry, testing, web smoke verification, version update, commit, tag, and push closure steps.
- Tests: Added workflow definition validation for required fields, unique step ids, dependency integrity, lane references, and coverage of current pipeline steps.
- Docs: Linked the workflow definition from `docs/farrlind_workflow.md` and marked the definition task complete in `todo.md`.

## v0.2.13 - 5/10/2026

Added the Wells of Magic lore editor.

- App: Wired Wells of Magic into the left archive menu.
- App: Added a single large editable Markdown text field backed by `knowledge/Faban/lore/wells_of_magic.md`.
- Canon: Seeded the Wells lore file with current campaign knowledge and open questions.
- Tests: Added service and route coverage for reading and saving Well lore.

## v0.2.12 - 5/10/2026

Added hover notes to artifact names.

- App: Artifact names now show the artifact notes field in a browser tooltip when notes are present.
- App: Added a subtle dotted underline to artifact names with hover notes.
- Tests: Added route coverage for artifact note tooltips.

## v0.2.11 - 5/10/2026

Added the Artifact Registry web interface.

- App: Wired Artifacts into the left archive menu.
- App: Added artifact listing, add/edit modals, delete actions, and an `/api/artifacts` endpoint.
- App: Added artifact service queries and CRUD helpers for type, discovered session, description, lore significance, sentient/cursed/infernal flags, current holder, and notes.
- Tests: Added service and route coverage for artifact registry behavior.
- Docs: Documented how artifact canon is currently maintained through first-mention loading, registry edits, and future durable artifact scrub/custody records.

## v0.2.10 - 5/10/2026

Added the NPC Registry web interface.

- App: Wired NPC Registry into the left archive menu.
- App: Added NPC listing, add/edit modals, delete actions, and an `/api/npcs` endpoint.
- App: Added NPC service queries and CRUD helpers for status, faction, last known location, first-seen session, description, and named/unnamed state.
- Tests: Added service and route coverage for NPC registry behavior.
- Docs: Documented how NPC canon is maintained through reviewed session workflow and the `load_summaries.py` NPC scrub.

## v0.2.9 - 5/10/2026

Promoted parallel transcription into the campaign workflow.

- Workflow: Added `rag.py transcribe sessionXX` to produce `knowledge/Faban/raw/sessionXX_transcript.txt` from `audio/sessionXX.wav`.
- Workflow: Added a production parallel transcription module with `large-v3`, `180` second chunks, and two workers as defaults.
- Workflow: Pointed the benchmark parallel path at the production implementation to avoid drift.
- Tests: Added focused coverage for worker caps, chunk planning, transcript stitching output format, and default campaign paths.
- Docs: Updated README, workflow docs, and benchmark notes to identify two-worker parallel transcription as the normal path.

## v0.2.8 - 5/10/2026

Recorded the two-worker transcription recommendation.

- Docs: Clarified that two workers are the recommended default local `large-v3` transcription setting.
- Docs: Kept three workers available as an explicit comparison or time-sensitive option, not the default path.

## v0.2.7 - 5/10/2026

Recorded transcript equivalence for the session20 benchmark sweep.

- Docs: Added byte-for-byte transcript comparison results to `docs/transcription_benchmark_session20.md`.
- Docs: Preserved shared line, word, byte, and SHA-256 metrics for the existing sequential, two-worker parallel, and three-worker parallel outputs.

## v0.2.6 - 5/10/2026

Preserved session20 transcription benchmark metrics and opened a three-worker benchmark sweep.

- Workflow: Raised the transcription benchmark worker cap from two to three for explicit parallel-worker comparison.
- Docs: Added `docs/transcription_benchmark_session20.md` to preserve benchmark metrics from ignored output artifacts, including existing sequential, two-worker parallel, and three-worker parallel results.
- Docs: Updated benchmark worker-cap language in `README.md` and `docs/farrlind_workflow.md`.
- Tests: Updated worker-cap coverage for the three-worker ceiling.

## v0.2.5 - 5/10/2026

Added progress logging for long transcription benchmark runs.

- Workflow: Benchmark logs now show architecture start/end, chunk materialization, and per-chunk completion progress.
- Workflow: Progress messages flush immediately so detached runs can be monitored from their log files.

## v0.2.4 - 5/10/2026

Capped the transcription architecture benchmark at two parallel workers.

- Workflow: Added a benchmark worker-count cap so accidental higher values resolve to two workers for the large-v3 CPU comparison.
- Tests: Added coverage for the worker-count cap.
- Docs: Documented the two-worker cap in `README.md` and `docs/farrlind_workflow.md`.

## v0.2.3 - 5/10/2026

Added an isolated benchmark harness for transcription architecture testing.

- Workflow: Added `scripts/benchmark_transcription_architectures.py` to compare the existing sequential transcription path with an experimental parallel worker path.
- Workflow: Benchmark outputs are isolated under ignored `benchmarks/transcription/` directories so normal campaign transcripts and canon artifacts are not touched.
- Docs: Added the benchmark command to `README.md`.
- Docs: Added the benchmark path and output layout to `docs/farrlind_workflow.md`.

## v0.2.2 - 5/10/2026

Added Python 3.11 virtual environment migration to the roadmap.

- Docs: Added a Data Management task to evaluate moving from Python 3.9 to Python 3.11 using a parallel venv.
- Docs: Captured validation expectations for faster-whisper transcription, the worker skeleton, the web app, and the full test suite before replacing `rag-env`.

## v0.2.1 - 5/10/2026

Updated the canonical workflow reference for the plain Python worker skeleton.

- Docs: Added the `split -> transcribe_parallel placeholder -> stitch -> validate placeholder` worker flow to `docs/farrlind_workflow.md`.
- Docs: Documented the new `src/farrlind_pipeline/` worker modules, Pydantic schema location, runner command, and output artifacts.
- Docs: Updated Phase 2 next tasks to include evolving placeholders into real transcription workers and keeping `scripts/rag.py`, `src/farrlind_pipeline/`, and workflow definitions aligned.

## v0.2.0 - 5/10/2026

Introduced the initial plain Python worker pipeline skeleton.

- Workflow: Added `src/farrlind_pipeline/` with deterministic worker modules for split, placeholder parallel transcription, stitch, and placeholder validation.
- Workflow: Added Pydantic schemas for manifests, transcript chunks, stitched transcripts, validation reports, and pipeline run results.
- Workflow: Added `simple_runner.py` to execute `split -> transcribe_parallel placeholder -> stitch -> validate placeholder` without LangGraph.
- Docs: Added the plain worker skeleton command to `README.md`.
- Tests: Added focused unit coverage for chunk manifest creation and the placeholder runner outputs.

## v0.1.3 - 5/9/2026

Added a canonical workflow document for Phase 2 planning.

- Docs: Added `docs/farrlind_workflow.md` as the end-to-end workflow reference.
- Docs: Consolidated pipeline stages, review gates, artifact paths, canon safety rules, and future workflow-state needs.
- Docs: Updated `README.md` and `docs/session_review_workflow.md` to point back to the canonical workflow reference.

## v0.1.2 - 5/9/2026

Closed Phase 1 and cleaned up the project roadmap structure.

- Docs: Marked Version Control Best Practices as complete in `todo.md`.
- Docs: Organized roadmap work into Project Management, Workflow Management, Web Interface Improvements, and Data Management.
- Docs: Added minor-release candidates for NPC Registry, Artifact Listing, Well of Magic lore, Faban Songbook, and Campaign Timeline.

## v0.1.1 - 5/9/2026

Displayed the Farrlind Campaign app version in the archive UI.

- App: Added a small footer to the app layout that reads the current version from `version.md`.
- App: Added route coverage so the dashboard verifies the displayed version.
- Docs: Bumped the current version to `v0.1.1` and recorded the revision.

## v0.1.0 - 5/9/2026

Established the Farrlind Campaign app baseline for versioned development.

- App: Added the Dockerized FastAPI/Jinja review app with Docker Compose support on port 8000.
- App: Added the fantasy archive dashboard, sidebar navigation, review workflow controls, and Locations CRUD.
- App: Added modal add/edit forms for Locations and command-result display for review actions.
- App: Added tests covering the review UI, location routes, command services, and existing DM query/load behavior.
- Canon: Preserved reviewed session summaries, review YAML, travel data, enemy encounters, general encounters, and campaign lore files as the current canon working set.
- Workflow: Captured the planned workflow graph phases in `todo.md`, including database-backed workflow state, human review gates, and later audio ingestion.
- Workflow: Established the canon safety rule that automated reruns must not overwrite reviewed or applied canon without explicit human approval.
- Schema: Baseline uses the existing PostgreSQL campaign schema and seed/load scripts.
- Docs: Added versioning rules based on the major.minor.revision pattern from the Jubilaires membership project.
