#!/usr/bin/env bash
# Stop Codex Appling only (port 9201).
set -euo pipefail
APPLING_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$APPLING_DIR/scripts/appling-launch.py" codex stop
