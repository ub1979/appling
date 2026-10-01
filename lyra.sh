#!/usr/bin/env bash
# Kept for old habits: Lyra Lite now starts with ./start.sh.
exec "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/start.sh" "$@"
