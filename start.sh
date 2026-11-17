#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -e .
if [ ! -d ui/node_modules ]; then
  (cd ui && npm ci)
fi
(cd ui && npm run build)
exec .venv/bin/python -m appling "$@"
