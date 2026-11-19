#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
if [ -x .appling_c/runtime/node_modules/node/bin/node ]; then
  export PATH="$PWD/.appling_c/runtime/node_modules/node/bin:$PATH"
fi
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$PWD/.appling_c/browsers}"
export npm_config_cache="${npm_config_cache:-$PWD/.appling_c/npm-cache}"
if .venv/bin/python -m appling.service status --quiet; then
  exec .venv/bin/python -m appling.service start "$@"
fi
if ! .venv/bin/python -c 'from appling.server import create_app' >/dev/null 2>&1; then
  echo "Installing missing Appling dependencies..."
  .venv/bin/python -m pip install -e '.[test]'
fi
if [ ! -d ui/node_modules ]; then
  (cd ui && npm ci)
fi
(cd ui && npm run build)
exec .venv/bin/python -m appling.service start "$@"
