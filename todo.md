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

- Continue refining the final-summary composition step as the primary human review surface after entity extraction.
- Keep event fragments as supporting evidence only; they must not dictate session workflow status or block final-summary completion.
- Improve the summary-writing workspace so the user can more easily use the Gemma draft canon packet, entity reviews, transcript, and event fragments as evidence while writing the final canon summary.
- Consider a protected "Re-run Draft Extraction" action for sessions whose entity reviews have not yet been applied.
  - It may rerun transcript-to-draft/entity extraction artifacts.
  - It must not overwrite reviewed entity decisions, database canon, final summaries, or applied review state.
  - If entity reviews have already been applied, the action should be disabled or generate new draft candidates only.
- Keep human approval gates explicit.
- Do not allow automated reruns to overwrite reviewed or applied canon.
- Any canon-changing rerun must end in human review before it can become canon.
- Capture command output in the same command-result style already used by the review UI.

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

## Web Interface Improvements

- Continue refining the session review page around final-summary review instead of micro-event decisions.
- Improve the operator view for queued/running workflow jobs if the worker needs more visibility.
- Revisit static archive export/publish workflow after another full session cycle.

## Data Management

- Define database/schema versioning rules in practice.
- Define backup and restore expectations for local development.
- Track seed/reference data that should be treated as managed project data.
- Strengthen canon integrity checks as the review workflow grows.

## Open Questions

- Which steps are safe to run automatically, and which must always require user confirmation?
- How should the UI distinguish stale artifacts from missing artifacts?
