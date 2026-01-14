
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "[run_update] folder: $SCRIPT_DIR"

# Examples:
#   ./run_update.sh 13/1/2026
#   ./run_update.sh 2026-01-13
if [ -n "${1-}" ]; then
  python update_tracker.py "$1"
else
  python update_tracker.py
fi
