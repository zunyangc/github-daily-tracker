
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "[run_update] folder: $SCRIPT_DIR"

# Load .env if present
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs) || true
fi

# Quick check token
if [ -z "${GITHUB_TOKEN-}" ]; then
  echo "[run_update] ERROR: GITHUB_TOKEN not set. Create .env with GITHUB_TOKEN=..." >&2
  exit 1
fi

# Examples:
#   ./run_update.sh 13/1/2026
#   ./run_update.sh 2026-01-13
if [ -n "${1-}" ]; then
  python update_tracker.py "$1"
else
  python update_tracker.py
fi
