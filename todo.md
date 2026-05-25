# D&D Campaign Manager TODO

## Goal

Build a clear workflow graph for any campaign pipeline, starting lightweight and only adding heavier orchestration if it earns its keep.

The workflow should eventually make it easy to see where each session is in the path from raw source material to queryable canon.

```text
audio/transcript
  -> draft canon packet with gemma4:e2b
  -> human canon packet review
  -> accepted canon summary
  -> accepted structured canon items
  -> apply review
  -> final summary
  -> database/canon health
```

## Current Decisions

- Workflow state should live in the database.
- Start with per-session workflow state first.
- Add campaign-level maintenance workflows later.
- Audio ingestion is now part of the per-session intake path, but remains upstream draft/source material.
- Reruns must never overwrite reviewed or applied canon automatically.
- Reruns may only affect canon after explicit human review and approval.
- Which steps can run automatically versus require user approval will be decided over time.
- Gemma curation should be treated as a draft canon packet generator, not merely a prose summarizer.
- Draft canon packets should extract coherent sections for summary, major events, NPCs/entities, locations, artifacts/items, lore items, combat encounters, open threads, timeline notes, and inventory/resource notes.

## Project Management

### Phase 1: Version Control Best Practices - Complete

- Introduced best-practice version control for campaign canon and workflow changes.
- Defined and documented version rules using:
  - major
  - minor
  - revision
- Decided what kind of change increments each level.
- Included database/schema versioning rules.
- Included canon/content versioning rules.
- Included workflow graph versioning rules.
- Reviewed how versioning is handled in the Jubilaires membership project and adapted the useful parts here.
- Added app-visible version display.
- Established matching Git tags for versioned commits.

## Workflow Management

### Phase 2: Define The Workflow Graph - Complete

- Done - Create a plain YAML workflow definition for the Farrlind session pipeline.
- Done - Persist workflow state in database tables rather than YAML state files.
- Done - Model each step with:
  - stable step id
  - display name
  - dependencies
  - command, if already known
  - expected inputs
  - expected outputs
  - status rules
- Done - Add a session workflow initialization command that seeds `workflow_run` and ordered `workflow_step_state` rows from the YAML definition.
- Done - Add a historical workflow seeding command for sessions 00 through 20, with estimated timestamps and evidence comments.
- Done - Kept the first workflow graph deterministic, inspectable, YAML-defined, and database-backed.

### Phase 3: Show Workflow State In The Web UI - Complete

- Done - Add a read-only workflow/status view to the local web app.
- Done - Show each session's progress through the graph.
- Done - Make incomplete, blocked, stale, complete, and not-applicable steps visually distinct.
- Done - Link workflow steps back to existing review/session, lore, and registry pages where useful.
- Done - Surface missing artifacts and validation/status problems.
- Done - Focused on per-session workflow state first.

### Phase 4: Wire Existing Commands To Workflow Actions - Complete

- Human review is not done yet.
  - The current fragment/event review flow is too large for long recorded sessions.
  - Session 21 showed that reviewing 200+ extracted event fragments is not the right primary operator experience.
  - Replace the primary review surface with a Gemma-curated summary review first.
  - The user should review and edit a coherent session summary into canon before structured database extraction is applied.
  - Event fragments should become supporting evidence or secondary detail, not the main review workload.
- Build the next review flow around:
  - Review Gemma draft canon packet.
  - Edit the narrative section into a human-approved canon summary.
  - Confirm key locations, NPCs, artifacts, lore items, combat encounters, open threads, inventory/resource notes, and timeline updates from that packet.
  - Only then apply reviewed canon to the database.
- Add a session initiation action for future sessions.
  - Capture the real-world session date.
  - Accept an uploaded audio file or a filesystem path to the audio file.
  - Create the session row and workflow run.
  - Seed ordered workflow step state from `workflows/session_workflow.yaml`.
  - Record the audio path in session/workflow state without starting transcription automatically unless explicitly confirmed.
- Add buttons for safe existing commands, such as:
  - initialize review
  - run health
  - apply review
  - write final summary
  - run summarize/postextract steps where appropriate
- Keep human approval gates explicit.
- Do not allow automated reruns to overwrite reviewed or applied canon.
- Any canon-changing rerun must end in human review before it can become canon.
- Capture command output in the same command-result style already used by the review UI.
- Prefer "Run next step" only after the graph status rules are trustworthy.

### Phase 5: Audio Ingestion - Complete

- Add audio ingestion to the workflow graph after the session review and canon workflow is stable.
- Model audio-specific steps separately, such as:
  - audio file registration
  - transcription
  - transcript cleanup
  - source artifact validation
- Keep audio ingestion upstream from canon review.
- Do not allow audio reprocessing to overwrite reviewed/applied canon without explicit human review.

### Future: Consider LangGraph Or Similar Orchestration

- Introduce LangGraph as a future workflow enhancement if the plain Python/YAML/database model starts needing more orchestration power.
- Revisit LangGraph only if the workflow needs:
  - branching
  - retries
  - resumable state
  - human-in-the-loop checkpoints
  - agentic extraction/revision loops
  - richer step memory than simple status files or DB rows
- If adopted, use LangGraph as the execution/state layer, not as a replacement for the explicit workflow definition.
- Keep the web UI as the main operator surface.
- This item is intentionally not phased yet.

### Later: Campaign-Level Maintenance

- Introduce Jinja to help with the prompts to both keep the prompts campaign agnostic and also to introduce micro-rules the shape would look like:
  - Generic base prompt: stable extractor behavior, output schema, source discipline.
  - Shared rule partials: no invention, no table chatter, evidence required, confidence rules.
  - Extractor partials: NPC rules, artifact rules, location rules, lore rules, combat rules.
  - Campaign partials/data: glossary, party exclusions, campaign-specific extraction guidance.
  - Session context: previous summary, session notes, known aliases, source files.
  - Few-short examples: optional, ideally generic by default and campaign-specific only when explicitly configured.
  
- Add campaign-level workflow graphs after per-session workflows are stable.
- Candidate maintenance workflows:
  - NPC registry cleanup - Complete
  - location normalization - Complete
  - enemy encounter tightening - Complete
  - travel timeline validation - Complete
  - open thread review - Complete
  - Wells of Magic status review - Removed
  - songbook prompt/repertoire review 

## Web Interface Improvements

### Minor Release Upgrade Candidates - Complete

- Develop NPC Registry. Done in v0.2.10 with listing, add/edit modals, delete actions, API route, and canon workflow notes.
- Develop Artifact Listing. Done in v0.2.11 with listing, add/edit modals, delete actions, API route, and artifact canon notes.
- Develop Well of Magic Lore Section. Done in v0.2.13 with editable Markdown lore backed by `knowledge/Faban/lore/wells_of_magic.md`.
- Develop Faban Songbook. Done in v0.3.15 with sidebar page, song cards, metadata, local playback, source links, lyrics pages, and API route.
- Develop Campaign Timeline. Done in v0.4.4 with read-only timeline, travel movements, major events, and API route.
- Develop Lore Items Registry. Done with sidebar page, edit/archive modes, add/edit/delete modals, API route, smoke-test coverage, and draft canon packet prompt support.

## Data Management

- Define database/schema versioning rules in practice.
- Define backup and restore expectations for local development.
- Track seed/reference data that should be treated as managed project data.
- Strengthen canon integrity checks as the review workflow grows.
- Plan and execute a deliberate PostgreSQL major-version upgrade from `postgres:16` to latest current PostgreSQL, presently PostgreSQL 18. Use dump/restore or `pg_upgrade` with a fresh volume, verify the web container `postgresql-client` major version matches the database server, restore-test the backup, and run the Project Utilities smoke test before retiring the PostgreSQL 16 volume.
- Evaluate upgrading the local development virtual environment from Python 3.9 to Python 3.11 by creating a parallel venv, installing requirements, and validating faster-whisper transcription, the worker skeleton, the web app, and the full test suite before replacing `rag-env`.

## Resolved Questions

- Workflow state should live in the database.
- The first workflow graph should be per-session.
- YAML is the canonical step definition and determines step order.
- Database rows are the runtime state for session workflows and step progress.
- Campaign-level maintenance workflows come later.
- Reruns must not overwrite reviewed/applied canon automatically.
- Audio/transcript ingestion comes later as Phase 6.

## Open Questions

- Which steps are safe to run automatically, and which must always require user confirmation?
- Which workflow status values should the web UI expose first?
- How should the UI distinguish stale artifacts from missing artifacts?
