#!/usr/bin/env python3
from __future__ import annotations

import re
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

REQUIRED_FILES = [
    "README.md",
    "docs/ai/README.md",
    "docs/ai/00-master-prompt.md",
    "docs/ai/00-execution-protocol.md",
    "docs/ai/01-task-progress.md",
    "docs/ai/task-progress.yaml",
    "docs/ai/reference/architecture-and-decisions.md",
    "docs/ai/reference/data-events-api.md",
    "docs/ai/reference/frontend-spec.md",
    "docs/ai/reference/runtime-deployment-spec.md",
    "docs/ai/reference/runtime-agent-prompts.md",
    "docs/ai/reference/tool-registry-spec.md",
    "docs/ai/reference/tool-registry.yaml",
    "docs/ai/reference/prompt-contracts.yaml",
    "docs/ai/reference/security-policy-matrix.md",
    "docs/ai/reference/database-erd-migrations.md",
    "docs/ai/reference/database-schema.yaml",
    "docs/api/openapi-contract.md",
    "docs/api/openapi.yaml",
    "docs/evals/prompt-eval-cases.yaml",
    "docs/evals/prompt-eval-runbook.md",
    "docs/runbooks/local-development.md",
    "docs/runbooks/deployment.md",
    "docs/runbooks/migrations.md",
    "docs/runbooks/rollback.md",
    "docs/runbooks/troubleshooting.md",
    "docs/security/threat-model.md",
    "docs/qa/test-strategy.md",
    "docs/demo/e2e-demo-script.md",
]

STAGE_FILES = [
    "docs/ai/02-stage-01-git-github.md",
    "docs/ai/03-stage-02-figma-design.md",
    "docs/ai/04-stage-03-repository-scaffold.md",
    "docs/ai/05-stage-04-backend-foundation.md",
    "docs/ai/06-stage-05-task-event-store.md",
    "docs/ai/07-stage-06-planner-executor.md",
    "docs/ai/08-stage-07-react-console.md",
    "docs/ai/09-stage-08-dramatiq-subagent.md",
    "docs/ai/10-stage-09-sandbox-warmpool.md",
    "docs/ai/11-stage-10-observability-deployment.md",
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def fail(message: str) -> None:
    print(f"docs validation failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def check_required_files() -> None:
    for rel in REQUIRED_FILES + STAGE_FILES:
        path = ROOT / rel
        if not path.is_file():
            fail(f"missing required file: {rel}")


def check_blocked_terms() -> None:
    targets = [ROOT / "README.md", ROOT / "docs", ROOT / ".github"]
    files: list[Path] = []
    for target in targets:
        if target.is_file():
            files.append(target)
        if target.is_dir():
            files.extend(path for path in target.rglob("*") if path.is_file())
    for path in files:
        text = read_text(path)
        for term in BLOCKED_TERMS:
            if term in text:
                fail(f"blocked term found in {path.relative_to(ROOT)}")


def check_stage_docs() -> None:
    for rel in STAGE_FILES:
        text = read_text(ROOT / rel)
        required_sections = [
            "## Required Context",
            "## AI \u6267\u884c\u63d0\u793a\u8bcd",
            "## Verification Commands",
            "## Progress Update Rule",
        ]
        for section in required_sections:
            if section not in text:
                fail(f"{rel} missing section {section}")


def check_progress_alignment() -> None:
    yaml_text = read_text(ROOT / "docs/ai/task-progress.yaml")
    stage_ids = re.findall(r"stage-\d{2}-[a-z0-9-]+", yaml_text)
    for rel in STAGE_FILES:
        if rel not in yaml_text:
            fail(f"{rel} missing from task-progress.yaml")
    for stage_id in sorted(set(stage_ids)):
        if yaml_text.count(stage_id) < 2:
            fail(f"{stage_id} has incomplete progress metadata")


def check_reference_links() -> None:
    readme = read_text(ROOT / "docs/ai/README.md")
    for rel in [
        "./00-master-prompt.md",
        "./task-progress.yaml",
        "./reference/runtime-agent-prompts.md",
        "./reference/tool-registry-spec.md",
        "./reference/tool-registry.yaml",
        "./reference/prompt-contracts.yaml",
        "./reference/security-policy-matrix.md",
        "../api/openapi-contract.md",
        "../api/openapi.yaml",
        "../evals/prompt-eval-cases.yaml",
        "../evals/prompt-eval-runbook.md",
        "../security/threat-model.md",
        "../qa/test-strategy.md",
        "../demo/e2e-demo-script.md",
        "../runbooks/local-development.md",
    ]:
        if rel not in readme:
            fail(f"AI README missing link {rel}")


def main() -> None:
    check_required_files()
    check_blocked_terms()
    check_stage_docs()
    check_progress_alignment()
    check_reference_links()
    print("docs validation passed")


if __name__ == "__main__":
    main()
