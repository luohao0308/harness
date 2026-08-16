#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\((?P<target>[^)]+)\)")
FENCE_PATTERN = re.compile(r"^\s*(`{3,}|~{3,})")
EXTERNAL_SCHEMES = {"data", "file", "ftp", "http", "https", "mailto", "tel"}


def markdown_files() -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "*.md"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted(
        path
        for line in completed.stdout.split("\0")
        if line and (path := ROOT / line).is_file()
    )


def prose_lines(path: Path) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    fence: str | None = None
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = FENCE_PATTERN.match(line)
        if match:
            marker = match.group(1)[0]
            fence = None if fence == marker else marker if fence is None else fence
            continue
        if fence is None:
            result.append((number, line))
    return result


def local_target(raw_target: str) -> str | None:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    elif " " in target:
        target = target.split(None, 1)[0]
    target = target.strip()
    if not target or target.startswith(("#", "/", "//")):
        return None
    parsed = urlsplit(target)
    if parsed.scheme.lower() in EXTERNAL_SCHEMES or parsed.netloc:
        return None
    path = unquote(parsed.path)
    if not path or any(marker in path for marker in ("{{", "}}", "<", ">", "$")):
        return None
    return path


def main() -> None:
    failures: list[str] = []
    checked_links = 0
    files = markdown_files()
    for source in files:
        for line_number, line in prose_lines(source):
            for match in LINK_PATTERN.finditer(line):
                target = local_target(match.group("target"))
                if target is None:
                    continue
                checked_links += 1
                destination = (source.parent / target).resolve()
                try:
                    destination.relative_to(ROOT)
                except ValueError:
                    failures.append(
                        f"{source.relative_to(ROOT)}:{line_number}: target leaves repository: {target}"
                    )
                    continue
                if not destination.exists():
                    failures.append(
                        f"{source.relative_to(ROOT)}:{line_number}: missing target: {target}"
                    )

    if failures:
        print("Markdown link validation failed:", file=sys.stderr)
        print("\n".join(f"- {failure}" for failure in failures), file=sys.stderr)
        raise SystemExit(1)
    print(f"Markdown links passed: {len(files)} files / {checked_links} local links")


if __name__ == "__main__":
    main()
