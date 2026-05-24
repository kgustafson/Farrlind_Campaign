# Legacy Init Directory

Database initialization is now campaign-aware:

- Shared schema and generic lookup rows live in `../campaigns/init/`.
- Campaign-specific seed/canon SQL lives in `../campaigns/<campaign-name>/init/`.

Docker Compose mounts those paths directly. Do not put campaign canon seed data here.
