# Version

v0.4.0

## Versioning

This project uses major.minor.revision version numbers.

- Major: breaking or foundational changes to the campaign application, canon model, workflow architecture, or database schema.
- Minor: meaningful feature additions, new archive sections, new workflow phases, new canon management capabilities, or substantial query/report expansions.
- Revision: routine fixes, styling updates, small UI improvements, test additions, Docker/config refinements, copy edits, and small canon corrections.

Each committed project change should increment the revision number unless the change intentionally bumps the major or minor version.

Every versioned change should also be tagged in Git with the matching version number, such as `v0.1.0`.

Revision details are tracked in `revision.md` with newest versions first.

## Git Tags

The current version/revision should be carried forward as a Git tag.

- Tag format: `vMAJOR.MINOR.REVISION`
- Example: `v0.1.0`
- The tag should point to the commit that contains the matching `version.md` and `revision.md` updates.
- Revision-only changes should still receive a matching tag.
- If a version number changes, update `version.md`, add the matching `revision.md` entry, commit both, and tag that commit.

## Change Categories

Revision entries should identify the kind of work being changed when useful:

- App: web UI, API routes, command wiring, Docker/runtime behavior, and developer workflow.
- Canon: curated campaign truth, session summaries, NPCs, locations, enemies, travel, wells, artifacts, open threads, and songbook material.
- Workflow: session review flow, workflow graph, human approval gates, rerun handling, and orchestration rules.
- Schema: database tables, migrations, seed data, and persistence model changes.
- Docs: documentation-only updates.

## Canon Safety Rule

Automated reruns must never overwrite reviewed or applied canon.

Canon-changing reruns may only become canonical after explicit human review and approval.

## Current Baseline

`v0.4.0` adds the Open Threads archive section with edit-mode CRUD and archive-mode read-only viewing.
