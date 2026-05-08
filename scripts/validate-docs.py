#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BLOCKED_TERMS = [
    "\x4d\x56\x50",
    "\u5efa\u8bae",
    "\u63a8\u8350",
    "\u53ef\u4ee5",
    "\u4e0d\u5efa\u8bae",
    "\u5982\u679c",
    "\u6216\u8005",
    "\u5747\u53ef",
]

TOP_LEVEL_SPECS = [
    "docs/00-product-spec.md",
    "docs/01-system-architecture.md",
    "docs/02-data-model-and-event-spec.md",
    "docs/03-api-spec.md",
    "docs/04-agent-runtime-spec.md",
    "docs/05-tool-mcp-runtime-spec.md",
    "docs/06-guardrail-policy-spec.md",
    "docs/07-eval-harness-spec.md",
    "docs/08-console-ui-spec.md",
    "docs/09-benchmark-spec.md",
    "docs/10-portfolio-demo-spec.md",
    "docs/task-progress.md",
]

STAGE_FILES = [
    "docs/ai/stages/01-agent-graph-runtime.md",
    "docs/ai/stages/02-event-store-recovery.md",
    "docs/ai/stages/03-agent-run-console.md",
    "docs/ai/stages/04-tool-mcp-runtime.md",
    "docs/ai/stages/05-guardrail-policy-engine.md",
    "docs/ai/stages/06-eval-harness.md",
    "docs/ai/stages/07-memory-context-router.md",
    "docs/ai/stages/08-warmpool-benchmark.md",
    "docs/ai/stages/09-portfolio-demo-docs.md",
]

REQUIRED_FILES = [
    "README.md",
    "docs/ai/README.md",
    "docs/ai/00-execution-protocol.md",
    "docs/ai/01-task-progress.md",
    "docs/ai/task-progress.yaml",
    "docs/human/10-task-progress.md",
    "docs/TECHNICAL-IMPLEMENTATION-PROGRESS.md",
    *TOP_LEVEL_SPECS,
    *STAGE_FILES,
]

STAGE_SECTIONS = [
    "## Goal",
    "## Input",
    "## Output",
    "## Modules",
    "## API And Schema Changes",
    "## Event Types",
    "## Frontend Display",
    "## Tests",
    "## Acceptance",
    "## Not Doing",
    "## Vertical Slice Demo",
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def fail(message: str) -> None:
    print(f"docs validation failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def check_required_files() -> None:
    for rel in REQUIRED_FILES:
        if not (ROOT / rel).is_file():
            fail(f"missing required file: {rel}")


def check_no_old_stage_docs() -> None:
    old_stage_docs = list((ROOT / "docs/ai").glob("[0-9][0-9]-stage-*.md"))
    if old_stage_docs:
        names = ", ".join(str(path.relative_to(ROOT)) for path in old_stage_docs)
        fail(f"old stage docs still present: {names}")


def check_blocked_terms() -> None:
    targets = [
        ROOT / "README.md",
        *[ROOT / rel for rel in TOP_LEVEL_SPECS],
        *[ROOT / rel for rel in STAGE_FILES],
        ROOT / "docs/ai/README.md",
        ROOT / "docs/ai/00-execution-protocol.md",
        ROOT / "docs/ai/01-task-progress.md",
        ROOT / "docs/ai/task-progress.yaml",
        ROOT / "docs/human/10-task-progress.md",
        ROOT / "docs/TECHNICAL-IMPLEMENTATION-PROGRESS.md",
        ROOT / ".github",
    ]
    files: list[Path] = []
    for target in targets:
        if target.is_file():
            files.append(target)
        if target.is_dir():
            files.extend(path for path in target.rglob("*") if path.is_file())
    for path in files:
        text = read_text(path)
        for marker in ["<<<<<<<", "=======", ">>>>>>>"]:
            if marker in text:
                fail(f"merge conflict marker found in {path.relative_to(ROOT)}")
        for term in BLOCKED_TERMS:
            if term in text:
                fail(f"blocked term found in {path.relative_to(ROOT)}")


def check_stage_docs() -> None:
    for rel in STAGE_FILES:
        text = read_text(ROOT / rel)
        for section in STAGE_SECTIONS:
            if section not in text:
                fail(f"{rel} missing section {section}")


def check_progress_alignment() -> None:
    yaml_text = read_text(ROOT / "docs/ai/task-progress.yaml")
    human_text = read_text(ROOT / "docs/human/10-task-progress.md")
    for rel in STAGE_FILES:
        if rel not in yaml_text:
            fail(f"{rel} missing from task-progress.yaml")
        stage_id = Path(rel).stem
        if stage_id not in human_text:
            fail(f"{stage_id} missing from human task progress")
    if "spec_first_stage_gated_vertical_slice" not in yaml_text:
        fail("task-progress.yaml missing spec execution mode")
    if "Eval Harness" not in human_text:
        fail("human progress missing Eval Harness")


def check_readme_links() -> None:
    readme = read_text(ROOT / "README.md")
    for rel in TOP_LEVEL_SPECS + STAGE_FILES:
        link = f"./{rel}"
        if link not in readme and rel not in readme:
            fail(f"README missing link {rel}")


def main() -> None:
    check_required_files()
    check_no_old_stage_docs()
    check_blocked_terms()
    check_stage_docs()
    check_progress_alignment()
    check_readme_links()
    print("docs validation passed")


if __name__ == "__main__":
    main()
