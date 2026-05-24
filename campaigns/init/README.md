# Shared Campaign Database Init

These files are mounted into `/docker-entrypoint-initdb.d` for every campaign database on first boot.

- `01_schema.sql` creates the universal tables, indexes, and campaign-neutral views.
- `02_generic_lookups.sql` loads generic lookup rows only.
- `99_campaign_seed.sh` runs any campaign-specific first-boot files mounted at `/campaign-init`.

Do not put named-campaign canon here. Put that in `campaigns/<campaign-name>/init/`.
