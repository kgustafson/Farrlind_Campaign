# Farrlind Workflow Graph TODO

## Goal

Build a clear workflow graph for the Farrlind campaign pipeline, starting lightweight and only adding heavier orchestration if it earns its keep.

The workflow should eventually make it easy to see where each session is in the path from raw source material to queryable canon.

```text
audio/transcript
  -> extract
  -> filter
  -> classify
  -> normalize
  -> merge
  -> validate
  -> summarize
  -> human review
  -> apply review
  -> final summary
  -> database/canon health
```

## Current Decisions

- Workflow state should live in the database.
- Start with per-session workflow state first.
- Add campaign-level maintenance workflows later.
- Audio ingestion belongs later, not in the first workflow graph.
- Reruns must never overwrite reviewed or applied canon automatically.
- Reruns may only affect canon after explicit human review and approval.
- Which steps can run automatically versus require user approval will be decided over time.

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

### Phase 3: Show Workflow State In The Web UI

- Done - Add a read-only workflow/status view to the local web app.
- Done - Show each session's progress through the graph.
- Done - Make incomplete, blocked, stale, complete, and not-applicable steps visually distinct.
- Done - Link workflow steps back to existing review/session, lore, and registry pages where useful.
- Done - Surface missing artifacts and validation/status problems.
- Focus on per-session workflow state first.

### Phase 4: Wire Existing Commands To Workflow Actions

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

### Phase 5: Audio Ingestion

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

- Add campaign-level workflow graphs after per-session workflows are stable.
- Candidate maintenance workflows:
  - NPC registry cleanup
  - location normalization
  - enemy encounter tightening
  - travel timeline validation
  - open thread review
  - Wells of Magic status review
  - songbook prompt/repertoire review

## Web Interface Improvements

### Minor Release Upgrade Candidates

- Develop NPC Registry.
- Develop Artifact Listing.
- Develop Well of Magic Lore Section.
- Develop Faban Songbook.
- Develop Campaign Timeline.

## Data Management

- Define database/schema versioning rules in practice.
- Define backup and restore expectations for local development.
- Track seed/reference data that should be treated as managed project data.
- Strengthen canon integrity checks as the review workflow grows.
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
