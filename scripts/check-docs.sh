#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 "$ROOT_DIR/scripts/validate-docs.py"
python3 "$ROOT_DIR/scripts/check-markdown-links.py"
test -f "$ROOT_DIR/docs/development/ai/README.md"
test -f "$ROOT_DIR/docs/development/ai/01-task-progress.md"
test -f "$ROOT_DIR/docs/development/ai/task-progress.yaml"
test -f "$ROOT_DIR/docs/design/figma-production-brief.md"
test -f "$ROOT_DIR/docs/design/design-tokens.json"
test -f "$ROOT_DIR/docs/design/page-inventory.md"

echo "docs checks passed"
