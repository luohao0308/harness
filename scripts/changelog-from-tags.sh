#!/usr/bin/env bash
set -euo pipefail

target_tag="${1:-}"
if [[ -z "$target_tag" ]]; then
  target_tag="$(git describe --tags --abbrev=0 2>/dev/null || true)"
fi
if [[ -z "$target_tag" ]]; then
  echo "usage: scripts/changelog-from-tags.sh <tag>" >&2
  exit 1
fi

previous_tag="$(git describe --tags --abbrev=0 "${target_tag}^" 2>/dev/null || true)"
range="$target_tag"
if [[ -n "$previous_tag" ]]; then
  range="$previous_tag..$target_tag"
fi

date_utc="$(date -u +%Y-%m-%d)"
{
  echo "## $target_tag - $date_utc"
  echo
  if [[ -n "$previous_tag" ]]; then
    echo "Changes since $previous_tag:"
  else
    echo "Initial tagged release:"
  fi
  echo
  git log --pretty=format:'- %s (%h)' "$range"
  echo
}
