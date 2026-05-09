# Revision History

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
