#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "[run_update] folder: $SCRIPT_DIR"

# Auto-activate ./venv if present and not already active.
if [ -z "${VIRTUAL_ENV-}" ] && [ -f "./venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  . ./venv/bin/activate
  echo "[run_update] activated venv: $VIRTUAL_ENV"
fi

PY="${PYTHON:-python3}"

# Examples:
#   ./run_update.sh 13/1/2026
#   ./run_update.sh 2026-01-13
if [ -n "${1-}" ]; then
  "$PY" update_tracker.py "$1"
else
  "$PY" update_tracker.py
fi
