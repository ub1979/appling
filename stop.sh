#!/usr/bin/env bash
# Stop the APP IT started from this folder (and only that one).
set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PATTERN="$PROJECT_DIR/.venv/bin/python -m lyra_lite"

PIDS="$(pgrep -f -- "$PATTERN" || true)"
if [[ -z "$PIDS" ]]; then
  echo "APP IT is not running from this folder."
  exit 0
fi

echo "Stopping APP IT..."
kill $PIDS 2>/dev/null || true
for _ in {1..20}; do
  pgrep -f -- "$PATTERN" >/dev/null || { echo "Stopped."; exit 0; }
  sleep 0.5
done
kill -9 $(pgrep -f -- "$PATTERN") 2>/dev/null || true
echo "Stopped."
