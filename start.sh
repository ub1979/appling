#!/usr/bin/env bash
# Start APP IT (http://127.0.0.1:9200/). Prepares everything on the first
# run, keeps the Mac awake while APP IT works, and stops with Ctrl+C or ./stop.sh.
# The classic Studio is still available as ./start-studio.sh.
set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PORT="${1:-${LYRA_LITE_PORT:-9200}}"
URL="http://127.0.0.1:${PORT}/"
cd "$PROJECT_DIR"

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Something is already running on port ${PORT} — probably APP IT: $URL"
  echo "Stop it with ./stop.sh (in the folder that started it), then try again."
  open "$URL" 2>/dev/null || true
  exit 0
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "Error: uv is required. Install it from https://docs.astral.sh/uv/ and run this again."
  exit 1
fi

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Preparing APP IT for the first run (a few minutes, only once)..."
  uv sync --extra dev --extra lyra-claude
fi

UI=lyra_lite/ui
if [[ ! -f "$UI/dist/index.html" ]] || [[ -n "$(find "$UI/src" "$UI/index.html" -newer "$UI/dist/index.html" 2>/dev/null | head -1)" ]]; then
  echo "Building APP IT's screen..."
  (cd "$UI" && { [[ -d node_modules ]] || npm install --no-audit --no-fund; } && npm run build >/dev/null)
fi

echo "Enabling the Ultimate Builder plugin..."
"$PROJECT_DIR/.venv/bin/hermes" plugins enable ultimate-builder >/dev/null 2>&1 || true

# Absolute interpreter path: stop.sh uses it to find this folder's APP IT.
"$PROJECT_DIR/.venv/bin/python" -m lyra_lite --port "$PORT" &
LYRA_PID=$!
trap 'kill "$LYRA_PID" 2>/dev/null || true' INT TERM
command -v caffeinate >/dev/null && caffeinate -i -s -w "$LYRA_PID" &
wait "$LYRA_PID"
