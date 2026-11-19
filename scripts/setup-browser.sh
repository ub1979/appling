#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -x .appling_c/runtime/node_modules/node/bin/node ]; then
  export PATH="$PWD/.appling_c/runtime/node_modules/node/bin:$PATH"
fi
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$PWD/.appling_c/browsers}"
export npm_config_cache="${npm_config_cache:-$PWD/.appling_c/npm-cache}"
cd scripts
npm ci
npx playwright install chromium
