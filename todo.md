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

### Phase 2: Define The Workflow Graph

- Done - Create a plain YAML workflow definition for the Farrlind session pipeline.
- Persist workflow state in database tables rather than YAML state files.
- Model each step with:
  - stable step id
  - display name
  - dependencies
  - command, if already known
  - expected inputs
  - expected outputs
  - status rules
- Keep this deterministic and inspectable.
- Avoid introducing LangGraph or another orchestration framework until the shape of the workflow is clearer.

### Phase 3: Show Workflow State In The Web UI

- Add a read-only workflow/status view to the local web app.
- Show each session's progress through the graph.
- Make incomplete, blocked, stale, and complete steps visually distinct.
- Surface missing artifacts and validation problems.
- Link workflow steps back to existing review/session pages where useful.
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

### Phase 5: Consider LangGraph Or Similar Orchestration

- Revisit LangGraph only if the workflow needs:
  - branching
  - retries
  - resumable state
  - human-in-the-loop checkpoints
  - agentic extraction/revision loops
  - richer step memory than simple status files or DB rows
- If adopted, use LangGraph as the execution/state layer, not as a replacement for the explicit workflow definition.
- Keep the web UI as the main operator surface.

### Phase 6: Audio Ingestion

- Add audio ingestion to the workflow graph after the session review and canon workflow is stable.
- Model audio-specific steps separately, such as:
  - audio file registration
  - transcription
  - transcript cleanup
  - source artifact validation
- Keep audio ingestion upstream from canon review.
- Do not allow audio reprocessing to overwrite reviewed/applied canon without explicit human review.

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
- Campaign-level maintenance workflows come later.
- Reruns must not overwrite reviewed/applied canon automatically.
- Audio/transcript ingestion comes later as Phase 6.

## Open Questions

- Which steps are safe to run automatically, and which must always require user confirmation?
- What should the first database schema for workflow state look like?
- Should workflow state be stored as normalized rows, JSONB snapshots, or both?
- How should the UI distinguish stale artifacts from missing artifacts?
