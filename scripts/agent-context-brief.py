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
MODULE_MAP = ROOT / "docs/module-map.json"
MODULE_INDEX = ROOT / "docs/MODULE-INDEX.md"
SESSION_POINTERS = ROOT / "docs/ai/session-log-pointers.md"
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


def load_module_map() -> list[dict[str, Any]]:
    return json.loads(MODULE_MAP.read_text(encoding="utf-8"))["modules"]


def generate_module_index() -> None:
    """Generate docs/MODULE-INDEX.md from docs/module-map.json (deterministic, sortedby name)."""
    modules = sorted(load_module_map(), key=lambda m: m["name"])
    lines = [
        "<!-- AUTO-GENERATED from docs/module-map.json — do not hand-edit -->",
        "<!-- Regenerate: python3 scripts/agent-context-brief.py --gen-module-index -->",
        "",
        "# Module Index",
        "",
        "Code module → owning docs. For feature→spec mapping see [SPEC-INDEX](./SPEC-INDEX.md).",
        "",
        "| Module | Path | Summary | Docs |",
        "| --- | --- | --- | --- |",
    ]
    for m in modules:
        name = m["name"]
        path = m["path"]
        summary = m.get("summary", "")
        docs = m.get("docs", [])
        # Links are relative to docs/ (MODULE-INDEX.md location)
        doc_links = ", ".join(
            f"[{d.split('/')[-1]}](./{'/'.join(d.split('/')[1:])})" if d.startswith("docs/") else f"`{d}`"
            for d in docs
        ) if docs else "—"
        lines.append(f"| `{name}` | `{path}` | {summary} | {doc_links} |")
    lines.append("")
    MODULE_INDEX.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"Generated {MODULE_INDEX.relative_to(ROOT)} ({len(modules)} modules)")


def render_recent_sessions() -> str:
    """Return a '## Recent Sessions' section from the last 5 pointer lines (--show-sessions only)."""
    if not SESSION_POINTERS.exists():
        return ""
    pointer_lines = [
        line for line in SESSION_POINTERS.read_text(encoding="utf-8").splitlines()
        if line.startswith("- ")
    ][-5:]
    if not pointer_lines:
        return ""
    return "\n".join(["", "## Recent Sessions", ""] + pointer_lines)


def render_brief(task: str, max_pages: int, max_routes: int, show_startup: bool, show_sessions: bool = False) -> str:
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
    result = "\n".join(lines).rstrip()
    if show_sessions:
        result += render_recent_sessions()
    return result + "\n"


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
    parser.add_argument(
        "--show-sessions",
        action="store_true",
        help="Append last 5 session pointers from docs/ai/session-log-pointers.md to the brief.",
    )
    parser.add_argument(
        "--gen-module-index",
        action="store_true",
        help="Generate docs/MODULE-INDEX.md from docs/module-map.json and exit.",
    )
    args = parser.parse_args()

    if args.gen_module_index:
        generate_module_index()
        return

    max_pages = max(1, args.max_pages)
    max_routes = max(1, args.max_routes)
    print(render_brief(args.task, max_pages, max_routes, args.show_startup, args.show_sessions), end="")


if __name__ == "__main__":
    main()
