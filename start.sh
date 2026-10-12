#!/usr/bin/env bash
# Start Appling (http://127.0.0.1:9200/). Prepares everything on the first
# run, keeps the Mac awake while Appling works, and stops with Ctrl+C or ./stop.sh.
# The classic Studio is still available as ./start-studio.sh.
set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PORT="${1:-${LYRA_LITE_PORT:-9200}}"
URL="http://127.0.0.1:${PORT}/"
cd "$PROJECT_DIR"

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Something is already running on port ${PORT} — probably Appling: $URL"
  echo "Stop it with ./stop.sh (in the folder that started it), then try again."
  open "$URL" 2>/dev/null || true
  exit 0
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "Error: uv is required. Install it from https://docs.astral.sh/uv/ and run this again."
  exit 1
fi

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Preparing Appling for the first run (a few minutes, only once)..."
  uv sync --extra dev --extra lyra-claude
fi

# A .venv carried over from another folder can lack the Claude engine's SDK.
if ! ".venv/bin/python" -c "import claude_agent_sdk" >/dev/null 2>&1; then
  echo "Installing the Claude engine..."
  uv pip install --python .venv/bin/python -r pyproject.toml --extra lyra-claude
fi

UI=lyra_lite/ui
if [[ ! -f "$UI/dist/index.html" ]] || [[ -n "$(find "$UI/src" "$UI/index.html" -newer "$UI/dist/index.html" 2>/dev/null | head -1)" ]]; then
  echo "Building Appling's screen..."
  (cd "$UI" && { [[ -d node_modules ]] || npm install --no-audit --no-fund; } && npm run build >/dev/null)
fi

echo "Enabling the Ultimate Builder plugin..."
"$PROJECT_DIR/.venv/bin/hermes" plugins enable ultimate-builder >/dev/null 2>&1 || true

# Runs in the background so this Terminal is free again; ./stop.sh stops it.
# Absolute interpreter path: stop.sh uses it to find this folder's Appling.
LOG_DIR="${HERMES_HOME:-$HOME/.hermes}/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/appling.log"
nohup "$PROJECT_DIR/.venv/bin/python" -m lyra_lite --port "$PORT" </dev/null >>"$LOG" 2>&1 &
LYRA_PID=$!
command -v caffeinate >/dev/null && { nohup caffeinate -i -s -w "$LYRA_PID" >/dev/null 2>&1 & }

for _ in {1..120}; do
  if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Appling is running at $URL"
    echo "Stop it with ./stop.sh. Log: $LOG"
    exit 0
  fi
  if ! kill -0 "$LYRA_PID" 2>/dev/null; then
    echo "Appling did not start. Last lines of $LOG:"
    tail -n 20 "$LOG"
    exit 1
  fi
  sleep 0.5
done
echo "Appling is still starting (pid $LYRA_PID). Watch $LOG, or stop it with ./stop.sh."
