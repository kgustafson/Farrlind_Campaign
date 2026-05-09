# Revision History

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
