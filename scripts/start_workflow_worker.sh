#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

SESSION_NAME="farrlind_workflow_auto_intake"
LOG_FILE="logs/workflow_auto_intake_worker.log"
mkdir -p logs

if screen -ls | grep -q "[.]${SESSION_NAME}[[:space:]]"; then
  echo "Workflow auto-intake worker is already running in screen session ${SESSION_NAME}."
  exit 0
fi

screen -S "${SESSION_NAME}" -dm bash -lc "
  cd '$(pwd)'
  while true; do
    ./rag-env/bin/python scripts/workflow_auto_intake.py >> '${LOG_FILE}' 2>&1
    sleep 30
  done
"

echo "Started workflow auto-intake worker in screen session ${SESSION_NAME}."
echo "Worker log: ${LOG_FILE}"
