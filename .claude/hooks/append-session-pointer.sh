#!/bin/sh
# Append exactly one pointer line per session to docs/ai/session-log-pointers.md.
# Per-session notes path ensures each pointer resolves to a distinct, durable artifact.
# No LLM, no network — pure shell + date + printf.
set -eu

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
SESSION_ID="${1:-${TS}}"
SESSION_DIR="$ROOT/.omc/state/sessions/$SESSION_ID"
mkdir -p "$SESSION_DIR"
NOTES_REL=".omc/state/sessions/$SESSION_ID/notes.md"
PTR="$ROOT/docs/ai/session-log-pointers.md"

# Create pointer file with header if it doesn't exist yet
[ -f "$PTR" ] || printf '# Session Log Pointers\n\nAppend-only. One line per session-end (written by the Stop hook).\n\n' > "$PTR"

printf -- '- %s \xe2\x86\x92 %s\n' "$TS" "$NOTES_REL" >> "$PTR"
