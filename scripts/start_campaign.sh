#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CAMPAIGN_NAME_ARG="${1:-}"

if [[ -z "${CAMPAIGN_NAME_ARG}" ]]; then
  echo "Usage: $0 <campaign-name> [docker compose args...]"
  echo "Example: $0 trinyvale up -d"
  exit 2
fi
shift || true

ENV_FILE="${ROOT_DIR}/campaigns/${CAMPAIGN_NAME_ARG}/.env"
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Campaign env file not found: ${ENV_FILE}" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

CAMPAIGN_NAME="${CAMPAIGN_NAME:-${CAMPAIGN_NAME_ARG}}"
FARRLIND_CAMPAIGN="${FARRLIND_CAMPAIGN:-${CAMPAIGN_NAME}}"

if [[ "${CAMPAIGN_NAME}" != "${CAMPAIGN_NAME_ARG}" ]]; then
  echo "Warning: CAMPAIGN_NAME=${CAMPAIGN_NAME} differs from folder ${CAMPAIGN_NAME_ARG}." >&2
fi

if [[ "$#" -eq 0 ]]; then
  set -- up -d
fi

echo "Campaign: ${CAMPAIGN_NAME}"
echo "Env file: ${ENV_FILE}"
echo "Compose project: ${CAMPAIGN_NAME}"
echo "Command: docker compose -p ${CAMPAIGN_NAME} $*"

cd "${ROOT_DIR}/farrlind"
docker compose -p "${CAMPAIGN_NAME}" "$@"
