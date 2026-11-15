#!/usr/bin/env bash
# Start Hermes Appling only (port 9200).
set -euo pipefail
APPLING_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$APPLING_DIR/scripts/appling-launch.py" hermes start
