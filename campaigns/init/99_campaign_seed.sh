#!/usr/bin/env bash
set -euo pipefail

if [[ ! -d /campaign-init ]]; then
  echo "No campaign-specific init directory mounted; skipping campaign seed."
  exit 0
fi

shopt -s nullglob
for file in /campaign-init/*; do
  case "$file" in
    *.sql)
      echo "Running campaign seed SQL: $file"
      psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f "$file"
      ;;
    *.sql.gz)
      echo "Running compressed campaign seed SQL: $file"
      gunzip -c "$file" | psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB"
      ;;
    *.sh)
      echo "Running campaign seed script: $file"
      bash "$file"
      ;;
    *)
      echo "Ignoring campaign init file: $file"
      ;;
  esac
done
