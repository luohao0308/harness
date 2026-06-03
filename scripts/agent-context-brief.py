#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STARTUP_CONTEXT = ROOT / "docs/ai/agent-startup-context.md"
CONTEXT_INDEX = ROOT / "docs/ai/context-index.json"
TASK_PROGRESS = ROOT / "docs/ai/task-progress.yaml"
GENERIC_SINGLE_TERMS = {
    "context",
    "token",
    "startup",
    "handoff",
    "selector",
    "tool",
    "memory",
    "backend",
    "port",
    "health",
    "ui",
    "menu",
    "release",
    "demo",
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_index() -> dict[str, Any]:
    return json.loads(read_text(CONTEXT_INDEX))


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def tokenize(value: str) -> list[str]:
    return [piece for piece in re.split(r"[^a-z0-9]+", normalize(value)) if piece]


def keyword_matches(needle: str, task_text: str, task_tokens: set[str]) -> bool:
    normalized = normalize(needle)
    if not normalized:
        return False
    keyword_tokens = tokenize(normalized)
    if not keyword_tokens:
        return False
    if len(keyword_tokens) == 1:
        return keyword_tokens[0] in task_tokens
    return normalized in task_text or all(piece in task_tokens for piece in keyword_tokens)


def route_score(route: dict[str, Any], task: str) -> int:
    task_text = normalize(task)
    if not task_text:
        return 0
    task_tokens = set(tokenize(task_text))
    score = 0
    for keyword in route.get("keywords", []):
        needle = normalize(str(keyword))
        if not needle:
            continue
        if keyword_matches(needle, task_text, task_tokens):
            keyword_tokens = tokenize(needle)
            if len(keyword_tokens) == 1 and keyword_tokens[0] in GENERIC_SINGLE_TERMS:
                score += 1
            else:
                score += 4 + min(len(keyword_tokens), 3)
    return score


def unique_ordered(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            result.append(path)
    return result


def extract_progress_summary() -> list[str]:
    text = read_text(TASK_PROGRESS)
    keys = [
        "current_stage",
        "current_status",
        "last_updated_at",
        "product",
        "formula",
        "website_policy",
    ]
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if any(stripped.startswith(f"{key}:") for key in keys):
            lines.append(stripped)
    return lines


def trim_startup_context(max_lines: int = 90) -> str:
    lines = read_text(STARTUP_CONTEXT).splitlines()
    return "\n".join(lines[:max_lines]).strip()


def select_routes(index: dict[str, Any], task: str, max_routes: int) -> list[dict[str, Any]]:
    routes = index.get("routes", [])
    if not task:
        fallback = next((route for route in routes if route.get("id") == "project-handoff"), routes[0])
        return [fallback]
    scored = [(route_score(route, task), route) for route in routes]
    matches = [item for item in scored if item[0] > 0]
    if not matches:
        fallback = next((route for route in routes if route.get("id") == "project-handoff"), routes[0])
        return [fallback]
    matches.sort(key=lambda item: (-item[0], str(item[1].get("id", ""))))
    top_score = matches[0][0]
    focused_matches = [item for item in matches if item[0] >= max(1, top_score // 2)]
    return [route for _, route in focused_matches[:max_routes]]


def render_list(items: list[str]) -> str:
    if not items:
        return "- none"
    return "\n".join(f"- `{item}`" for item in items)


def render_brief(task: str, max_pages: int, max_routes: int, show_startup: bool) -> str:
    index = load_index()
    routes = select_routes(index, task, max_routes)
    base_read_order = ["docs/ai/agent-startup-context.md", "docs/ai/task-progress.yaml"]
    read_first = unique_ordered(
        path for route in routes for path in route.get("read_first", [])
    )
    read_first = [path for path in read_first if path not in base_read_order][:max_pages]
    deep_read = unique_ordered(path for route in routes for path in route.get("deep_read", []))[
        :max_pages
    ]
    write_targets = unique_ordered(
        target
        for route in routes
        for target in route.get("progress_write_targets", index.get("progress_write_targets", []))
    )

    lines = [
        "# Agent Context Brief",
        "",
        "## Task",
        "",
        task.strip() if task.strip() else "No task text supplied; showing canonical startup route.",
        "",
        "## Machine Progress",
        "",
        render_list(extract_progress_summary()),
        "",
        "## Matched Context Routes",
        "",
    ]
    for route in routes:
        lines.append(f"- `{route.get('id')}`: {route.get('summary')}")

    lines.extend(
        [
            "",
            "## Required Read Order",
            "",
            *[f"- `{path}`" for path in base_read_order],
            *[f"- `{path}`" for path in read_first],
            "",
            "## Deep Read Only If Needed",
            "",
            render_list(deep_read),
            "",
            "## Completion Write-Back",
            "",
            render_list(write_targets or index.get("progress_write_targets", [])),
            "",
            "## Stop Condition",
            "",
            (
                "Stop reading when the task target, current progress, relevant wiki handoff, "
                "and required write-back targets are clear. Do not read the whole wiki unless "
                "the matched pages show a concrete gap."
            ),
        ]
    )
    if show_startup:
        lines.extend(["", "## Startup Context Excerpt", "", trim_startup_context()])
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print a low-token project context brief for a new agent task."
    )
    parser.add_argument("--task", default="", help="User task text used to select context routes.")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=5,
        help="Maximum wiki/plan/context paths to list per section.",
    )
    parser.add_argument(
        "--max-routes",
        type=int,
        default=3,
        help="Maximum matched context routes to include.",
    )
    parser.add_argument(
        "--show-startup",
        action="store_true",
        help="Append the startup context excerpt to the brief.",
    )
    args = parser.parse_args()

    max_pages = max(1, args.max_pages)
    max_routes = max(1, args.max_routes)
    print(render_brief(args.task, max_pages, max_routes, args.show_startup), end="")


if __name__ == "__main__":
    main()
