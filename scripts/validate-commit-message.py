#!/usr/bin/env python3
"""Validate Harness commit subjects without third-party dependencies."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ALLOWED_TYPES = (
    "feat",
    "fix",
    "refactor",
    "docs",
    "test",
    "chore",
    "ci",
    "build",
    "perf",
    "revert",
)
SUBJECT_PATTERN = re.compile(
    rf"^({'|'.join(ALLOWED_TYPES)})\([a-z0-9]+(?:-[a-z0-9]+)*\): .+$"
)


def first_subject(message: str) -> str:
    for line in message.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return ""


def validate_subject(subject: str, *, allow_fixup: bool = False) -> list[str]:
    errors: list[str] = []
    candidate = subject.strip()
    if allow_fixup and candidate.startswith(("fixup! ", "squash! ")):
        candidate = candidate.split("! ", 1)[1]
    elif candidate.startswith(("fixup! ", "squash! ")):
        errors.append("fixup/squash commits must be folded before opening a PR")
        return errors

    if not candidate:
        return ["commit subject is empty"]
    if len(candidate) > 88:
        errors.append(f"commit subject is {len(candidate)} characters; maximum is 88")
    if candidate.endswith("."):
        errors.append("commit subject must not end with a period")
    if not SUBJECT_PATTERN.fullmatch(candidate):
        errors.append(
            "expected '<type>(<scope>): <summary>' with a lowercase kebab-case scope; "
            f"allowed types: {', '.join(ALLOWED_TYPES)}"
        )
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--message-file", type=Path)
    source.add_argument("--subject", action="append")
    source.add_argument("--stdin", action="store_true")
    parser.add_argument("--allow-fixup", action="store_true")
    parser.add_argument("--label", default="commit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.message_file:
        subjects = [first_subject(args.message_file.read_text())]
    elif args.subject:
        subjects = args.subject
    else:
        subjects = [line.strip() for line in sys.stdin if line.strip()]

    failures = 0
    for index, subject in enumerate(subjects, start=1):
        errors = validate_subject(subject, allow_fixup=args.allow_fixup)
        if not errors:
            continue
        failures += 1
        print(f"{args.label} {index}: {subject!r}", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
    if failures:
        print(
            "Example: feat(team): add overview and focused conversation",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
