#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${1:-$ROOT_DIR/apps/agent-console/dist}"
MAX_BYTES="${MAX_MAIN_CHUNK_BYTES:-512000}"

if [[ ! -d "$DIST_DIR/assets" ]]; then
  echo "Bundle assets directory not found: $DIST_DIR/assets" >&2
  exit 1
fi

largest_size=-1
largest_path=""

while IFS= read -r -d '' asset; do
  asset_size="$(wc -c < "$asset")"
  asset_size="${asset_size//[[:space:]]/}"
  if (( asset_size > largest_size )); then
    largest_size="$asset_size"
    largest_path="$asset"
  fi
done < <(find "$DIST_DIR/assets" -type f -name '*.js' -print0)

if (( largest_size < 0 )); then
  echo "No JavaScript assets found in $DIST_DIR/assets" >&2
  exit 1
fi

echo "largest_js=$largest_path bytes=$largest_size max=$MAX_BYTES"

if (( largest_size > MAX_BYTES )); then
  echo "Largest JS asset exceeds MAX_MAIN_CHUNK_BYTES" >&2
  exit 1
fi
