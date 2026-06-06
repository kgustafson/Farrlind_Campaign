# D&D Campaign Manager TODO

## Goal

Build a clear workflow graph for any campaign pipeline, starting lightweight and only adding heavier orchestration if it earns its keep.

The workflow should eventually make it easy to see where each session is in the path from raw source material to queryable canon.

```text
audio/transcript
  -> draft canon packet with gemma4:e2b
  -> dedicated entity extraction
  -> human review/apply of NPCs, locations, artifacts, lore items, combat encounters, and open threads
  -> structured database canon is locked as the golden entity truth
  -> compose human-reviewed final summary from evidence
  -> lock/write final summary markdown only
  -> database/canon health
```

## Current Decisions

- Workflow state should live in the database.
- Start with per-session workflow state first.
- Add campaign-level maintenance workflows later.
- Audio ingestion is now part of the per-session intake path, but remains upstream draft/source material.
- Reruns must never overwrite reviewed or applied canon automatically.
- Reruns may only affect canon after explicit human review and approval.
- After entity extraction reviews are applied, later final-summary review steps must not reload, reinterpret, or overwrite accepted entity database canon.
- Final-summary review is a narrative/canon-file publishing step; it writes markdown and marks the review applied, but does not run `dbload --apply`.
- Which steps can run automatically versus require user approval will be decided over time.
- Gemma curation should be treated as a draft canon packet generator, not merely a prose summarizer.
- Draft canon packets should extract coherent sections for summary, major events, NPCs/entities, locations, artifacts/items, lore items, combat encounters, open threads, timeline notes, and inventory/resource notes.

## Workflow Management

### Review Workflow Refinement

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
  - songbook prompt/repertoire review 

## Web Interface Improvements

- Continue refining the session review page around final-summary review instead of micro-event decisions.
- Improve the operator view for queued/running workflow jobs if the worker needs more visibility.
- Revisit static archive export/publish workflow after another full session cycle.

## Data Management

- Define database/schema versioning rules in practice.
- Define backup and restore expectations for local development.
- Track seed/reference data that should be treated as managed project data.
- Strengthen canon integrity checks as the review workflow grows.
- Plan and execute a deliberate PostgreSQL major-version upgrade from `postgres:16` to latest current PostgreSQL, presently PostgreSQL 18. Use dump/restore or `pg_upgrade` with a fresh volume, verify the web container `postgresql-client` major version matches the database server, restore-test the backup, and run the Project Utilities smoke test before retiring the PostgreSQL 16 volume.
- Evaluate upgrading the local development virtual environment from Python 3.9 to Python 3.11 by creating a parallel venv, installing requirements, and validating faster-whisper transcription, the worker skeleton, the web app, and the full test suite before replacing `rag-env`.

## Open Questions

- Which steps are safe to run automatically, and which must always require user confirmation?
- Which workflow status values should the web UI expose first?
- How should the UI distinguish stale artifacts from missing artifacts?
