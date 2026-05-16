# Revision History

## v0.4.11 - 5/16/2026

Redesigned the Campaign Timeline as a clickable session flow chart.

- App: Replaced stacked timeline cards with a vertical session-node flow chart.
- App: Added clickable numbered session circles that open session detail modals.
- App: Kept location and in-game date visible beside each node, with session-title tooltips on hover.
- App: Added responsive flow styling that extends cleanly as future sessions are added.
- Tests: Updated Campaign Timeline route coverage for the flow chart, tooltip attributes, and modals.

## v0.4.10 - 5/16/2026

Added the PostgreSQL 18 upgrade task to Data Management.

- Docs: Added a planned major-version upgrade from `postgres:16` to PostgreSQL 18.
- Docs: Captured dump/restore or `pg_upgrade`, fresh-volume, matching-client, restore-test, and smoke-test guardrails.

## v0.4.9 - 5/16/2026

Pinned the web container backup client to PostgreSQL 16.

- Docker: Installed `postgresql-client-16` from the PostgreSQL apt repository instead of Debian's default latest client.
- Data: Confirmed the edit container now runs `pg_dump 16.x` against the PostgreSQL 16 app database.
- Data: Generated and restore-tested a fresh utility backup produced by `pg_dump 16.x`.

## v0.4.8 - 5/16/2026

Fixed Project Utilities database backup restore compatibility.

- App: Sanitized generated SQL backups to remove PostgreSQL 17's `transaction_timeout` setting.
- Data: Generated and restore-tested a fresh in-app backup against a temporary PostgreSQL database.
- Tests: Added coverage for backup-file sanitization.

## v0.4.7 - 5/16/2026

Expanded the Project Utilities smoke-test report.

- App: Smoke test output now reports total tests run, pass/fail counts, categories, and per-check details.
- Tests: Added service coverage for the multiline categorized smoke-test summary.

## v0.4.6 - 5/16/2026

Added edit-mode Project Utilities.

- App: Added a Project Utilities sidebar link in edit mode only.
- App: Added viewers for `todo.md` and `revision.md`.
- App: Added a database backup action that creates a restore-friendly SQL dump and exposes a download link.
- App: Added a smoke-test action that checks core routes and database connectivity with pass/fail output.
- Docker: Installed `postgresql-client` in the web image so in-app backups can run `pg_dump`.
- Tests: Added route coverage for Project Utilities and backup fallback coverage for container execution.

## v0.4.5 - 5/16/2026

Marked completed Web Interface Improvement roadmap items.

- Docs: Audited the Web Interface Improvements list against `revision.md`.
- Docs: Marked NPC Registry, Artifact Listing, Wells of Magic lore, Faban Songbook, and Campaign Timeline as done.
- Docs: Added the implementation version and short delivered scope for each completed item.

## v0.4.4 - 5/16/2026

Added the Campaign Timeline archive section.

- App: Wired Campaign Timeline into the sidebar for edit and archive mode.
- App: Added `/timeline` and `/api/timeline` for a derived canon timeline view.
- App: Displayed reviewed sessions with real dates, in-world dates, primary locations, travel movements, and major events.
- App: Fixed Open Threads edit button contrast with a dedicated action-link style.
- Tests: Added route and API coverage for the Campaign Timeline.

## v0.4.3 - 5/16/2026

Improved Open Threads edit-mode controls and ledger readability.

- App: Moved Open Threads edit/delete controls into the thread title cell so CRUD is visible in edit mode.
- App: Reworked the Open Threads ledger into Thread, State, Scope, Description, and Resolution columns.
- App: Gave description text more width and allowed long thread titles to wrap cleanly.
- Tests: Added route assertions that edit/delete controls render for Open Threads in edit mode.

## v0.4.2 - 5/16/2026

Promoted approved Open Threads into managed canon data.

- Canon: Added the approved Open Threads set to the deterministic database loader.
- Schema: Seeded Open Threads and supporting locations in the init schema for fresh installs.
- Data: Loaded the approved threads into the running Docker database.
- Tests: Added loader coverage for Open Threads SQL generation.

## v0.4.1 - 5/16/2026

Added the first Open Threads candidate review pass.

- Canon: Reviewed final summaries, diary entries, and Wells lore for unresolved campaign threads.
- Docs: Added `docs/open_threads_pass.md` with recommended open thread candidates, likely resolved threads, and source anchors.
- Data: Did not load candidates into the database yet; this pass is a review artifact for human approval.

## v0.4.0 - 5/16/2026

Added the Open Threads archive section.

- Schema: Added `open_thread` to persist campaign mysteries, promises, threats, ambiguities, and hooks.
- App: Wired the Open Threads sidebar item to a real page in both edit and archive mode.
- App: Added edit-mode CRUD with modal add/edit forms and read-only archive-mode display.
- App: Implemented the four thread statuses: `open`, `resolved`, `superseded`, and `unknown`.
- Tests: Added Open Threads route coverage and preserved broader archive route coverage.

## v0.3.27 - 5/16/2026

Renamed the root archive navigation item to Sessions.

- App: Changed the root top-nav and sidebar labels from Dashboard to Sessions.
- App: Removed the redundant disabled Sessions placeholder from the sidebar.

## v0.3.26 - 5/16/2026

Removed Validation Queue from the published archive navigation.

- App: Archive mode no longer shows the Validation Queue placeholder in the sidebar.
- Tests: Extended archive navigation coverage to assert that Validation Queue is hidden.

## v0.3.25 - 5/14/2026

Added daily macOS database backup scheduling.

- Ops: Added a launchd plist for `com.farrlind.db-backup`.
- Ops: The scheduled job runs daily at 1:00 AM and writes clean Postgres dumps to `~/FarrlindBackups/`.
- Docs: Documented the LaunchAgent path, backup destination, and launchd log files.

## v0.3.24 - 5/14/2026

Added a clean database backup command.

- App: Added `rag.py db-backup` to create timestamped Postgres dumps from the Docker database.
- Data: The backup command runs `pg_dump --clean --if-exists` so restores can replace existing schema objects cleanly.
- Docs: Documented backup and restore commands for archive/PC setup.
- Project: Ignored local backup dump files under `backups/`.
- Tests: Covered backup path generation and `pg_dump` command construction.

## v0.3.23 - 5/14/2026

Updated Urgan Wyrmbane to the Drive-folder source URL.

- Canon: Stored the Drive-reported Songbook URL for Urgan Wyrmbane's recreated source doc.
- Data: Reloaded songbook source metadata into the running database after the document was moved into the Songbook folder.

## v0.3.22 - 5/14/2026

Recreated the Urgan Wyrmbane source document.

- Canon: Updated the seed schema to point Urgan Wyrmbane at the recreated Google Doc source.
- Canon: Corrected the base Urgan Wyrmbane source audio URL in the seed schema.
- Data: Reloaded songbook source metadata into the running database.

## v0.3.21 - 5/14/2026

Added song source links to lyrics pages.

- App: Individual song lyrics pages now show Source Doc and Source Audio links when known.
- App: Added spacing for the lyrics-page source action buttons.
- Tests: Covered source links on the song lyrics route.

## v0.3.20 - 5/14/2026

Simplified archive-mode session review pages.

- App: Archive-mode session review URLs now force rendered print view.
- App: Archive-mode session pages show only Diary and Summary source buttons.
- App: Archive-mode session pages hide review decision and validation controls, leaving a clean reader.
- Tests: Added route coverage for archive reader controls.

## v0.3.19 - 5/14/2026

Added a side-by-side archive-mode Docker service.

- Docker: Added `web_archive`, running the same app in archive mode on port `8002`.
- Docker: Mounted the archive service repository read-only and left the edit service on port `8000`.
- Docs: Documented the edit and archive viewer URLs for local testing.

## v0.3.18 - 5/14/2026

Hid workflow status from archive mode.

- App: Workflow Status is no longer shown in archive-mode navigation.
- App/API: `/workflow`, `/api/workflow`, and workflow session detail APIs now return `404` in archive mode.
- Tests: Added archive-mode coverage for workflow navigation and API blocking.

## v0.3.17 - 5/14/2026

Added environment-controlled edit and archive interface modes.

- App: Added `FARRLIND_INTERFACE_MODE=edit|archive`, defaulting to edit mode.
- App: Archive mode hides Add/Edit/Delete/review action controls and renders Wells lore read-only.
- App: Archive mode rejects mutating HTTP requests with `403` so the hosted PC version cannot change canon.
- Docker/Docs: Passed the interface mode through Docker Compose and documented `.env` usage.
- Tests: Added archive-mode coverage for hidden controls, blocked writes, and read-only lore rendering.

## v0.3.16 - 5/13/2026

Fixed Faban's Songbook source links and surfaced the preface.

- App: Added a compact expandable preface section to `/songbook` using the existing songbook front matter file.
- Canon: Corrected the initial song seed for The Contract of Baron Wells and Ranger Rick and his Mighty Stick so source docs and audio links match the proper songs.
- Workflow: Updated the rerunnable songbook loader to sync source links from the master revealed songbook index.
- Tests: Added coverage for songbook front matter and source-link SQL generation.

## v0.3.15 - 5/13/2026

Added Faban's Songbook to the campaign archive.

- App: Wired Faban's Songbook into the sidebar with a `/songbook` archive page.
- App: Added read-only song cards from `v_songbook` with metadata, local audio playback, source links, and lyrics pages.
- App/API: Added `/api/songbook` plus safe local asset routes for lyrics and audio.
- Tests: Added service and route coverage for songbook rows, lyrics, and audio serving.

## v0.3.14 - 5/12/2026

Added the Murder Hobo Count to Combat Encounters.

- App: Added a parchment stat card to `/combat-encounters` with the party's confirmed kill total.
- App: The count includes known quantities with `killed` or `defeated` outcomes and excludes fled, resolved, unknown, or mixed unresolved outcomes.
- Tests: Added service and route coverage for kill-total calculation and rendering.

## v0.3.13 - 5/12/2026

Tightened the Balrog cultist combat encounter.

- Canon: Replaced the unknown Balrog cultist count with two spellcasting cultists and three melee cultists.
- Canon: Marked all five Balrog cultists as killed in the Orsydon encounter.
- Tests: Added loader coverage for the split cultist composition and outcomes.

## v0.3.12 - 5/12/2026

Added the Combat Encounters archive section.

- App: Added a sidebar link, `/combat-encounters` page, and `/api/combat-encounters` endpoint.
- App: Combat rows group enemy records by combat scene and show session span, location, enemy type, enemy count, outcome, confidence, and notes.
- App: Unknown enemy quantities now render explicitly as `unknown`, while mixed known/unknown totals render like `1+ unknown`.
- Tests: Added service and route coverage for grouped enemies, unknown quantities, and combat spanning multiple sessions.

## v0.3.11 - 5/12/2026

Audited diary and summary NPC coverage.

- Canon: Added high-confidence missed NPCs from diary/final-summary review: Alexander Venrid, Blue-skinned fey creature, Khorag, Magistrate Kaotoa, Bolder Grog, and Benjamin.
- Canon: Corrected Cole's first-seen session from Session 13 to Session 02 based on the diary identifying him as the old man first met near the Fey Woods.
- Tests: Added loader coverage for the audited NPC scrub entries.

## v0.3.10 - 5/12/2026

Added Jebediah Galloway to the NPC registry canon.

- Canon: Added Jebediah Galloway to the canonical NPC scrub with first appearance in Session 17 at the Crossroads Festival.
- App: Reloaded the database so the NPC Registry includes Jebediah Galloway in the current listing.
- Tests: Added loader coverage to keep the Crossroads Festival NPC scrub from regressing.

## v0.3.9 - 5/10/2026

Added future session initiation requirements to Phase 4.

- Docs: Added a Phase 4 requirement for session initiation before workflow actions.
- Docs: Session initiation must capture the real-world session date and either an uploaded audio file or a filesystem path to the audio file.
- Docs: Session initiation should create the session row, create the workflow run, seed ordered workflow step state from the YAML definition, and record the audio path without automatically starting transcription unless explicitly confirmed.

## v0.3.8 - 5/10/2026

Closed Phase 3 workflow status UI work.

- Docs: Marked Phase 3 as complete in `todo.md`.
- Docs: Confirmed the workflow UI now covers read-only status, progress, status distinctions, attention surfacing, and archive navigation links.

## v0.3.7 - 5/10/2026

Kept workflow View buttons on one line.

- App: Added no-wrap styling to archive action links.
- App: Added no-wrap styling to the workflow status action column.

## v0.3.6 - 5/10/2026

Expanded the Wells of Magic lore editor textarea.

- App: Set the Wells lore textarea to `20` visible rows for more comfortable editing.
- Tests: Added route coverage for the larger lore textarea.

## v0.3.5 - 5/10/2026

Moved workflow detail into a modal and restored the full ledger.

- App: Changed workflow View actions to open a modal detail view instead of a side-by-side panel.
- App: Restored the workflow ledger to a full-width table so the View buttons are no longer squeezed by the detail panel.
- App: `/workflow` now shows the ledger alone, while `/workflow?session=XX` opens the selected session detail modal.
- Tests: Added route coverage for default ledger-only rendering and selected-session modal rendering.

## v0.3.4 - 5/10/2026

Removed horizontal-scroll reliance from the workflow ledger for Safari.

- App: Changed the workflow session table to a fixed compact layout so the action column remains visible without using a horizontal scrollbar.
- App: Allowed long workflow text to wrap inside cells instead of forcing table overflow.
- App: Hid horizontal overflow on the ledger panel to avoid Safari scrollbar behavior differences.

## v0.3.3 - 5/10/2026

Fixed workflow ledger layout and optional correction-note attention noise.

- App: Prevented the workflow detail panel from covering the ledger's View buttons by allowing the ledger panel to own horizontal scrolling.
- App: Added a stable minimum width and right-side padding for the workflow session table action column.
- Workflow: Treats `knowledge/Faban/notes/sessionXX_corrections.md` as optional so missing correction notes do not create false attention items.
- Tests: Added coverage to confirm optional correction notes are ignored by workflow issue detection.

## v0.3.2 - 5/10/2026

Surfaced workflow attention items for missing artifacts and validation/status problems.

- App: Added attention counts to the workflow session ledger.
- App: Added a detail-level Needs Attention panel and per-step issue lists.
- Workflow: Detects pending, blocked, and stale step statuses as attention items.
- Workflow: Checks declared input/output file artifacts and reports missing paths or unmatched globs.
- Tests: Added coverage for status issues, missing artifact checks, rendered attention panels, and API issue metadata.

## v0.3.1 - 5/10/2026

Added archive navigation links to workflow status steps.

- App: Linked workflow session rows directly to their selected workflow detail.
- App: Added review, final-summary, lore, and registry links to relevant workflow steps.
- App: Exposed generated workflow URLs in the workflow API responses.
- Tests: Added service, route, and rendered-template coverage for workflow navigation links.

## v0.3.0 - 5/10/2026

Started Phase 3 with a read-only workflow status web view.

- App: Added `/workflow` with a session workflow ledger and ordered per-session step detail panel.
- App: Added `/api/workflow` and `/api/workflow/sessions/{session}` for workflow state inspection.
- App: Wired Workflow Status into the archive sidebar and styled progress/status states in the parchment archive theme.
- Workflow: Marked the first Phase 3 web status tasks complete in `todo.md`.
- Tests: Added workflow service and route coverage for the new page and APIs.

## v0.2.17 - 5/10/2026

Closed Phase 2 and moved LangGraph to a future workflow item.

- Docs: Marked Phase 2 workflow graph definition as complete.
- Docs: Moved LangGraph out of the numbered phase plan and into an unphased future orchestration candidate.
- Docs: Renumbered audio ingestion as the next workflow-management phase.

## v0.2.16 - 5/10/2026

Added historical workflow-state seeding for sessions 00 through 20.

- Workflow: Added `rag.py workflow-seed-history --start-session 0 --end-session 20 --apply`.
- Workflow: Seeded historical step statuses, estimated start/end timestamps, summary comments, and evidence metadata from existing audio, transcript, draft, review, final summary, and Git history artifacts.
- Workflow: Marked unpreserved older diary-session audio/transcription/draft stages as `not_applicable` rather than pretending those artifacts existed.
- Tests: Extended workflow-state tests for session 00 handling and historical seed generation.
- Docs: Documented the historical seeding command and timestamp-estimate metadata.

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
