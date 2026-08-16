#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

git config --local core.hooksPath .githooks

echo "Installed Harness Git hooks from .githooks"
echo "Configured: $(git config --local --get core.hooksPath)"
