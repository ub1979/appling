#!/usr/bin/env bash
# Start Lyra Lite. Builds the screen if needed and keeps the Mac awake while
# Lyra runs. Stop it with Ctrl+C.
set -euo pipefail
cd "$(dirname "$0")"
PORT="${1:-9200}"
URL="http://127.0.0.1:${PORT}/"

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Lyra Lite is already running at $URL"
  open "$URL" 2>/dev/null || true
  exit 0
fi

UI=lyra_lite/ui
if [ ! -f "$UI/dist/index.html" ] || [ -n "$(find "$UI/src" "$UI/index.html" -newer "$UI/dist/index.html" 2>/dev/null | head -1)" ]; then
  echo "Building Lyra's screen…"
  (cd "$UI" && { [ -d node_modules ] || npm install --no-audit --no-fund; } && npm run build >/dev/null)
fi

PY=.venv/bin/python
[ -x "$PY" ] || PY=venv/bin/python
"$PY" -m lyra_lite --port "$PORT" &
LYRA_PID=$!
trap 'kill "$LYRA_PID" 2>/dev/null || true' INT TERM
command -v caffeinate >/dev/null && caffeinate -i -s -w "$LYRA_PID" &
wait "$LYRA_PID"
