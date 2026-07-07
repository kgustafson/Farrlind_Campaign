# Revision History - D&D Campaign Manager

## v0.7.8 - 7/7/2026

Stabilized the session review/archive path and published recent Farrlind canon updates.

- App: Removed the stale "Confirm newly typed locations" blocker from session review saves so final-summary edits are not rejected by the old event-fragment workflow.
- App: Added previous/all/next diary navigation for archive-mode session diary pages, including static archive export support.
- Workflow: Hardened workflow auto-intake queue claiming and Docker database URL handling.
- Open Threads: Made reviewed thread creation merge by title instead of failing on duplicate open-thread titles.
- Extraction: Added Open Thread JSON repair/fallback handling so malformed model output can continue to human review.
- Canon: Added recent Farrlind session 21-23 reviewed/final summary artifacts.
- Tests: Added coverage for archive diary navigation, location-save behavior, Open Thread upserts, Open Thread JSON repair, and workflow worker queue handling.

## v0.7.7 - 6/9/2026

Added protected draft extraction reruns with canon guardrails.

- Workflow: Added a guarded "Re-run Draft Extraction" action to the workflow detail modal.
- Workflow: The rerun requires an existing transcript and refuses to queue if reviewed entity files or a final summary already exist.
- Workflow: Queued draft reruns run only source-status, curation, narrative, spine, entity extraction, event extraction, and postextract draft steps; they do not rerun transcription or apply canon.
- Runtime: Updated the workflow worker to honor the command subset listed in queue payloads.
- Tests: Added coverage for draft-rerun guardrails, queue payloads, worker command filtering, and workflow route behavior.

## v0.7.6 - 6/6/2026

Added Drive-backed source file selection for Faban's Songbook.

- App: Replaced raw source doc/audio URL entry as the primary songbook edit control with Drive-backed lyrics and MP3 dropdowns.
- App: Preserves manual URL fallback fields for files not yet listed in the campaign Drive manifest.
- Canon/Data: Added a campaign-local `drive_files.json` manifest seeded from the KoKCampaign Songbook and Songs folders.
- Tests: Added songbook route coverage for Drive-selected URLs, current saved Drive URLs, and modal rendering.

## v0.7.5 - 6/6/2026

Added edit-mode CRUD and reorder controls for Faban's Songbook.

- App: Added add, edit, delete, and move controls to `/songbook` in edit mode while keeping archive mode read-only.
- App: Treats `song_number` as the stable song identity and adds `order_number` as the editable repertoire/display order.
- Schema: Added `song.order_number` and expanded `v_songbook` with editable metadata fields needed by the songbook form.
- Workflow: Updated the songbook loader and maintenance report to respect songbook order without changing song identity.
- Tests: Added route coverage for songbook creation, updates, deletes, and reordering, plus live smoke verification.

## v0.7.4 - 6/6/2026

Added the first campaign-level maintenance workflow and upgraded the local development venv.

- Workflow: Added `scripts/rag.py songbook-review` for a read-only songbook prompt/repertoire maintenance report.
- Workflow: The report flags missing Suno prompts, missing local lyric/audio assets, final-summary song mentions absent from the song table, high-significance song opportunities, theme clusters, and similar-title watchlist entries.
- Docs: Documented campaign maintenance workflows and the songbook review command in the canonical workflow references.
- Runtime: Rebuilt the local `rag-env` virtual environment with Python 3.11 and preserved the previous Python 3.9 venv as `rag-env-py39-backup`.
- Tests: Added focused coverage for songbook maintenance heuristics and reran transcription, health, and workflow/web review checks.

## v0.7.3 - 6/6/2026

Upgraded the local Docker database stack to PostgreSQL 18.

- Runtime: Changed the Docker database image from `postgres:16` to `postgres:18`.
- Runtime: Moved the database service to a fresh `postgres_data_18` volume mounted at `/var/lib/postgresql`, matching the PostgreSQL 18 official image layout.
- Runtime: Updated the web image from `postgresql-client-16` to `postgresql-client-18` so `pg_dump` and `psql` match the server major version.
- Data: Created a pre-upgrade PostgreSQL 16 dump, restored it into PostgreSQL 18, and verified restored canon counts.
- Data: Generated a new PG18 utility backup and restore-tested it with a clean `public` schema restore.
- Docs: Updated database restore guidance with the clean-schema restore path for initialized databases.
- Tests: Ran focused backup/workflow/web review tests and Project Utilities smoke checks after the migration.

## v0.7.2 - 6/6/2026

Tightened session workflow status around the summary-first review model.

- Workflow: Treats completed final summaries as satisfying the final-summary review lane so legacy micro-event pending decisions no longer keep session ingest stuck.
- Workflow: Keeps applied entity extraction reviews authoritative for workflow status, preserving the database as the golden structured canon boundary.
- App: Adjusted the workflow ledger progress and pending counts to focus on session ingest lanes instead of downstream verification/version-control bookkeeping.
- App: Preserved legacy review dashboard behavior where older reviewed-but-unapplied event reviews still show `apply` as the next action.
- Tests: Added regression coverage for final summaries satisfying legacy micro-event review steps and reran focused workflow/web review suites.

## v0.7.1 - 6/5/2026

Added a Docker-managed workflow worker for automatic queued session intake.

- Runtime: Added a `workflow_worker` Docker Compose service that watches `ops/workflow_queue/` and runs queued auto-intake jobs through transcription, draft preparation, and entity extraction.
- Workflow: Added `--watch` mode and polling support to `scripts/workflow_auto_intake.py` so the worker stays alive instead of exiting when the queue is empty.
- Runtime: Added `ffmpeg`, `ffprobe`, and `faster-whisper` to the Docker image so transcription can run inside the worker container.
- Docs: Updated README startup guidance and worker log command.
- Tests: Added coverage for the queue watch loop.

## v0.7.0 - 6/1/2026

Baselined the summary-first review workflow and cleaned up the campaign management surface after the Session 22 intake cycle.

- Workflow: Added high-level workflow status rollups for kickoff, audio validation, transcription progress, draft preparation, six entity reviews, final summary review, and session ingest completion.
- Workflow: Fixed workflow ledger pending counts to use the actual unresolved step count and display only the latest workflow run per session.
- Workflow: Treats applied entity reviews and accepted final summaries as canon boundaries so stale YAML or draft artifacts do not overwrite reviewed database canon.
- App: Reframed Event Review as Session Review, with micro-events treated as evidence for final-summary composition instead of required per-event decision work.
- App: Prevents final-summary locking/writing from reloading entity database canon, preserving human-approved NPCs, locations, artifacts, lore items, combat encounters, and open threads.
- App: Added timeline editing, world-map access, cleaner workflow modals, and archive-mode review behavior refinements.
- App: Added Factions to Project Utilities lookup-table CRUD alongside artifact types, location types, combat outcomes, NPC status, workflow status states, and artifact flags.
- Canon: Fixed combat encounter kill-count preservation and restored Murder Hobo Count accuracy after Session 22 processing.
- Canon: Added Session 22 reviewed summary/diary artifacts and lookup override export support for campaign-specific reference data.
- Runtime: Added configurable `OLLAMA_URL` for Docker containers so app-side model calls reach the host Ollama service reliably.
- Tests: Added regression coverage for final-summary review behavior, workflow rollups, pending-count semantics, lookup-table factions, timeline editing, and combat display cleanup.

## v0.6.4 - 5/29/2026

Fixed campaign timeline compatibility and static archive publishing.

- App: Campaign Timeline now tolerates databases without `session.start_location_id` and `session.end_location_id`, falling back to existing primary-location data.
- Static Export: Restored songbook MP3 copying for legacy `knowledge/Faban/songbook` database paths after the multi-campaign folder move.
- Static Publish: Allows publish to replace generated static output even when a previous partial export left the static repo dirty.
- Static Publish: Sets a repository-local Git author identity before committing, so publishing works from the Docker web container.
- Tests: Added regression coverage for legacy songbook media export and static publish Git identity setup.

## v0.6.3 - 5/29/2026

Tightened the post-spine review workflow and restored Farrlind songbook audio compatibility.

- App: Reworked session review toward final-summary composition instead of high-level event bucketing for post-extraction review.
- App: Improved workflow status display for human-review markers, not-applicable steps, and stale downstream artifacts.
- Workflow: Added event-draft refresh wiring before final review initialization.
- Workflow: Expanded session workflow definition for narrative and spine processing gates.
- Extraction: Strengthened extractor source/context handling to reduce unsupported candidates and campaign bleed.
- Canon: Restored Farrlind songbook MP3/lyrics resolution for legacy `knowledge/Faban/songbook` database paths after the multi-campaign folder move.
- Data: Updated Trinyvale lookup overrides for campaign-specific normalization.
- Tests: Added coverage for entity source selection, event extraction, final-summary review behavior, workflow state, and songbook legacy path compatibility.

## v0.6.2 - 5/25/2026

Baselined the cleaned Trinyvale audio-first workflow through the session spine validation stage.

- Workflow: Added active-session narrative generation that separates podcast recap/context from live session material before chunking.
- Workflow: Added narrative post-hygiene for recap-only facts, unsupported found-location claims, known role conflicts, and PC/familiar ownership confusion.
- Workflow: Added session spine extraction and validation stages, including workflow status wiring, auto-intake queue integration, and stale-step detection when upstream draft artifacts are newer.
- Workflow: Strengthened spine extraction with preservation-aware handling for key items, character/resource beats, and final cliffhangers.
- Extraction: Added compact source/context handling and shared hygiene improvements across entity extractors to reduce campaign bleed and unsupported candidates.
- App: Continued Trinyvale workflow support with campaign-specific metadata, lookup overrides, review wiring, and map/sidebar cleanup from Farrlind-specific assumptions.
- Tests: Added coverage for narrative active-session boundaries, session spine extraction/validation, workflow stale detection, audio extension handling, campaign metadata seeding, and extractor hygiene.

## v0.6.1 - 5/24/2026

Added build-hash visibility for campaign runtimes.

- App: Reads `FARRLIND_GIT_HASH` from the campaign environment and shows the short hash in the archive footer when available.
- Runtime: Passes `FARRLIND_GIT_HASH` into both edit and archive Docker containers.
- Ops: Updated local campaign `.env` files for Farrlind and Trinyvale with the current Git commit hash.
- Tests: Added dashboard coverage for rendering the configured build hash.

## v0.6.0 - 5/24/2026

Added multi-campaign support and tightened the extractor-driven workflow using Trinyvale as a clean test campaign.

- App: Added campaign-scoped runtime configuration so separate campaigns can run with their own database, ports, archive name, subtitle, and feature flags.
- App: Added optional songbook support so new campaigns can omit Farrlind-specific songbook routes and exports.
- App: Added campaign-aware startup helpers and Docker Compose parameterization for running multiple campaign archives side by side.
- Workflow: Updated auto-intake, transcription, postextract, status checks, and workflow state tracking to operate against the selected campaign.
- Workflow: Added campaign bootstrap extraction for party, player, DM, and campaign metadata discovery from early sessions.
- Workflow: Preserved non-timestamped extracted events during merge so transcript-derived sessions do not collapse to empty summaries.
- Data: Moved Farrlind canon assets under `campaigns/farrlind` and added a blank `campaigns/trinyvale` scaffold.
- Extraction: Added shared hygiene guardrails for entity extractors and tightened NPC, location, artifact, lore, combat, and open-thread extraction behavior.
- Ops: Ignored campaign audio inputs and generated runtime artifacts so large MP3/WAV files and transient outputs stay out of Git.
- Tests: Added and updated campaign config, bootstrap extraction, merge, extractor, workflow, and web-route coverage.

## v0.5.0 - 5/23/2026

Added the model-curated extraction review layer and static archive release tooling.

- Workflow: Added Gemma-backed transcript curation prompts and wired curated output into the session processing flow.
- Workflow: Added dedicated extractors for NPCs, Locations, Artifacts, Lore Items, Combat Encounters, and Open Threads.
- App: Added human review/apply pages for extracted entities so model output becomes canon only after explicit approval.
- App: Expanded Combat Encounters into editable encounter records with child enemy rows and quantity/outcome tracking.
- App: Added Lore Items as a first-class archive section with CRUD and extraction review.
- App: Added Open Thread extraction review and changed Open Thread edit/delete controls to the shared pencil/X icon style.
- App: Added Project Utilities support for static archive export and related utility command output.
- Data: Added campaign metadata for party, players, and DM context used by extraction prompts.
- Model Eval: Added gold summaries and prompt iterations for local model cook-off scoring.
- Docs: Updated workflow and TODO notes for the revised curation-first review approach.
- Tests: Added extractor, review-service, route, workflow, and static-export coverage for the new release.

## v0.4.31 - 5/18/2026

Enforced the staged session review workflow.

- App: Session review now shows only the high-level event order editor until that step is explicitly completed.
- App: Added a dedicated bucketing stage where every loaded event is assigned to a high-level bucket or rejected.
- App: Full event resolution fields are hidden until bucketing is complete.
- Workflow: Bucket assignment overrides preexisting draft locations with the high-level bucket location.
- Workflow: Reviewed and applied sessions continue to open in the final event-resolution/archive view.
- Tests: Updated route and service coverage for the staged review flow.

## v0.4.30 - 5/18/2026

Supported bucket-first session review with inherited locations.

- App: Added bucket navigation to the review sidebar so a session can be reviewed one high-level event at a time.
- App: Added Unbucketed and Rejected review lanes for the triage pass.
- App: Preserves the current bucket filter across review saves, single-item saves, and batch updates.
- Workflow: Assigning an event to a high-level bucket now immediately inherits the bucket location.
- Tests: Added coverage for bucket filtering and location inheritance from high-level event buckets.

## v0.4.29 - 5/18/2026

Moved high-level event-order editing into a modal grid.

- App: Replaced the cramped sidebar high-level event editor with a modal spreadsheet-style grid.
- App: Added top-of-modal controls for inserting a new high-level event row.
- App: Added per-row remove controls using a compact `x` affordance.
- App: Decimal insertion orders such as `1.5` are sorted into place and renumbered as a clean `1..N` sequence when saved.
- App: High-level event locations now auto-create basic Location records when the macro order is saved.
- Tests: Added coverage for decimal insertion renumbering and automatic Location creation from high-level event buckets.

## v0.4.28 - 5/18/2026

Added high-level event-order buckets to session review.

- App: Added editable high-level event buckets with order, description, and location fields in the session review page.
- App: Review items can now be assigned to high-level buckets individually or in batches.
- App: Added an Apply Buckets action that gives bucketed review items the bucket location and renumbers them contiguously by macro event order.
- Tests: Added coverage for macro bucket creation, removal, batch assignment, route wiring, and bucket-order application.

## v0.4.27 - 5/18/2026

Made large audio-first session reviews manageable.

- App: Added selected-row batch decisions for session review items.
- App: Added per-item save buttons so one event can be decided without saving the full wall of review rows.
- App: Added quick location creation from the review page using the existing Locations registry.
- App: Added merge-selected review flow that creates one canonical added item and rejects the original fragments.
- App: Pending or invalid review items now bubble to the top of the list, and validation display is capped to avoid overwhelming the page.
- Workflow: Review validation now requires a valid event type for accepted, corrected, and added facts, while rejected items can remain otherwise incomplete.
- Tests: Added coverage for pending-first sorting, single-item saves, batch decisions, and review-item merging.

## v0.4.26 - 5/18/2026

Initialized audio-first reviews from merged draft events.

- Workflow: `init-review` now falls back to `knowledge/Faban/clean/sessionXX_merged.md` when a new audio session has no canonical DB events yet.
- Workflow: Draft merged events become pending review items tagged as `draft_merged_event`, preserving the human review gate before canon is applied.
- Tests: Added coverage for merged-event parsing and the DB-preferred review initialization fallback.

## v0.4.25 - 5/17/2026

Queued automatic session intake through the human-review gate.

- Workflow: Session initiation now queues auto-intake when a registered audio file exists.
- Workflow: Added a Mac-side auto-intake worker that runs transcribe, source status, extract, postextract, and init-review, then stops for human review.
- Workflow: The worker updates Workflow Status step timestamps, status, comments, log paths, and final run state as commands execute.
- App: Added workflow status badge styling for running, failed, and needs-attention states.
- Ops: Added a screen-based worker starter for local polling of queued workflow jobs.
- Tests: Added coverage for queue creation and the auto-intake command plan.

## v0.4.24 - 5/17/2026

Surfaced workflow step state fields in Workflow Status.

- App: Added a per-step state ledger to the Workflow Status detail modal.
- App: Shows status, started timestamp, completed timestamp, summary comment, inputs, and outputs for each workflow step.
- App: Styled long input/output artifacts so they remain readable in the workflow modal.
- Tests: Updated workflow route coverage for the displayed step state fields.

## v0.4.23 - 5/17/2026

Fixed audio-registration workflow updates for session initiation.

- Workflow: Qualified workflow-step timestamp columns when marking source audio registration complete.
- App: Verified session 21 can be re-registered with `audio/session21.wav` and the workflow moves Source Audio Registered to complete.

## v0.4.22 - 5/17/2026

Preserved the editable Farrlind world map source artwork.

- Docs: Added the Photoshop source file for the Farrlind world map alongside the exported PNG artwork.
- Canon: Confirmed the Wells of Magic lore file has no remaining uncommitted content changes after line-ending normalization.

## v0.4.21 - 5/17/2026

Added a shared Farrlind World Map modal.

- App: Added a World Map link to the shared archive sidebar for both edit and archive modes.
- App: Added a large responsive map modal using the Farrlind map PNG.
- App: Copied the map image into web static assets for reliable container serving.
- Tests: Added dashboard coverage for the World Map link and modal asset in edit and archive modes.

## v0.4.20 - 5/17/2026

Added Project Utilities session initiation.

- App: Added an Initiate Session card and modal form under Project Utilities for edit mode.
- Workflow: Added a database-backed workflow initiation service that seeds the session workflow from `workflows/session_workflow.yaml`.
- Workflow: Captures real session date, optional audio file path, and operator notes without overwriting reviewed canon.
- Workflow: Marks source audio registration complete only when the supplied audio file exists; otherwise the workflow remains pending for that step.
- Tests: Added route and workflow-service coverage for session initiation and next-session defaults.
- Runtime: Added missing `requests` and `httpx` dependencies so the existing tests and script imports work after container rebuilds.

## v0.4.19 - 5/16/2026

Added edit modal icons for NPCs, Locations, and Artifacts.

- App: Added standardized 512px source and static icons for NPC, Location, and Artifact add/edit modals.
- App: Wired the icons into the shared Add New and Edit modal headers for each section.
- Tests: Added route coverage for the add and edit modal icon assets.

## v0.4.18 - 5/16/2026

Added Project Utilities and Workflow Status title-card icons.

- App: Added standardized 512px source and static icons for Project Utilities and Workflow Status.
- App: Wired both icons into the right side of their archive title cards.
- Tests: Added route coverage for both icon assets.

## v0.4.17 - 5/16/2026

Added Project Utilities lookup table CRUD.

- Schema: Added reference tables for combat outcomes, workflow status states, and artifact flags.
- App: Added a Project Utilities lookup manager for Artifact Types, Location Types, Combat Outcomes, NPC Status, Workflow Status States, and Artifact Flags.
- App: Added add, edit, and delete routes for managed lookup values in edit mode.
- App: Seeded default values for the new combat outcome, workflow status, and artifact flag reference tables.
- Tests: Added service and route coverage for lookup listing and CRUD actions.

## v0.4.16 - 5/16/2026

Tightened Campaign Timeline labels and date ranges.

- App: Reduced the location and in-game date label size beside timeline session circles by half.
- App: Added timeline display formatting that collapses multiple in-game dates to earliest date thru latest date.
- App: Preserved raw in-game date strings in the timeline API while adding display/date-bound fields.
- Tests: Added coverage for multi-date, cross-month, ranged, and continued in-game date display.

## v0.4.15 - 5/16/2026

Refreshed archive section icons and Sessions subtitle copy.

- App: Updated the Sessions landing-page subtitle to the final eclectic travelling bard wording.
- App: Added title-card icons for Locations, Open Threads, and Wells of Magic.
- App: Refreshed the NPC Registry, Artifacts, Combat Encounters, and Faban's Songbook icon artwork.
- Docs: Added the standardized 512px source images for Locations, Open Threads, and Wells of Magic.
- Tests: Extended route coverage for the new Locations, Open Threads, and Wells of Magic icon assets.

## v0.4.14 - 5/16/2026

Updated the Sessions hero copy.

- App: Replaced the Sessions landing-page description with the travelling bard archive wording.

## v0.4.13 - 5/16/2026

Switched archive icons to the standardized 512px artwork.

- App: Replaced temporary SVG stat icons with final 512px PNG icons for sessions, travel days, and current location.
- App: Added title-card icons for NPC Registry, Artifacts, Combat Encounters, and Faban's Songbook.
- App: Kept responsive sizing so title-card and stat-card artwork remains secondary to the page text.
- Docs: Cleaned `docs/images` down to the standardized 512px source images.
- Tests: Updated route coverage for timeline and section-header icon assets.

## v0.4.12 - 5/16/2026

Added illustrated stat-card icons to the Campaign Timeline.

- App: Added sepia archive-style SVG icons for reviewed sessions, travel days, and current location.
- App: Placed and resized the icons inside the three timeline stat cards with responsive styling.
- Tests: Extended Campaign Timeline route coverage to assert the stat icon assets are rendered.

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
