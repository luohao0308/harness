#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${1:-$ROOT_DIR/apps/agent-console/dist}"
MAX_BYTES="${MAX_MAIN_CHUNK_BYTES:-512000}"

if [[ ! -d "$DIST_DIR/assets" ]]; then
  echo "Bundle assets directory not found: $DIST_DIR/assets" >&2
  exit 1
fi

largest_js="$(
  find "$DIST_DIR/assets" -type f -name '*.js' -print0 \
    | xargs -0 stat -f '%z %N' 2>/dev/null \
    | sort -nr \
    | head -n 1
)"

if [[ -z "$largest_js" ]]; then
  echo "No JavaScript assets found in $DIST_DIR/assets" >&2
  exit 1
fi

size="${largest_js%% *}"
path="${largest_js#* }"
echo "largest_js=$path bytes=$size max=$MAX_BYTES"

if (( size > MAX_BYTES )); then
  echo "Largest JS asset exceeds MAX_MAIN_CHUNK_BYTES" >&2
  exit 1
fi
