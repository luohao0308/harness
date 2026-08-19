#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIEF_ROUTE_FIXTURES = {
    "": ["project-handoff"],
    "startup context validation evidence": ["agent-startup-context-loop"],
    "agent startup context index": ["agent-startup-context-loop"],
    "large plan decomposition approval gate": ["large-plan-decomposition"],
    "大型计划拆分确认": ["large-plan-decomposition"],
    "RAG retrieval and Run Detail grounding": [
        "knowledge-rag-grounding",
        "eval-observability-groundedness",
    ],
    "frontend UI selector": ["frontend-ui-console"],
    "context router memory budget": ["context-router-memory"],
    "feature catalog status": ["feature-catalog"],
    "功能清单": ["feature-catalog"],
}
BRIEF_FEATURE_FIXTURES = {
    "RAG retrieval and Run Detail grounding": {
        "required": ["rag-grounding-citations", "run-detail"],
        "forbidden": ["release-startup-evidence"],
    },
    "Groundedness Eval regression": {
        "required": ["groundedness-eval"],
        "forbidden": ["release-startup-evidence"],
    },
    "Desktop startup P95 release evidence": {
        "required": ["release-startup-evidence"],
        "forbidden": ["rag-grounding-citations"],
    },
    "Team task graph dependency": {
        "required": ["task-graph"],
        "forbidden": ["rag-grounding-citations"],
    },
}

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
    "docs/design/product-spec.md",
    "docs/architecture/system-architecture-spec.md",
    "docs/contracts/data-model-and-event-spec.md",
    "docs/contracts/api/api-spec.md",
    "docs/architecture/agent-runtime-spec.md",
    "docs/contracts/tool-mcp-runtime-spec.md",
    "docs/contracts/guardrail-policy-spec.md",
    "docs/testing/eval-harness-spec.md",
    "docs/design/console-ui-spec.md",
    "docs/testing/benchmark-spec.md",
    "docs/design/portfolio-demo-spec.md",
]

LEGACY_DOC_DIRS = [
    "docs/adr",
    "docs/ai",
    "docs/api",
    "docs/api-reference",
    "docs/cli",
    "docs/demo",
    "docs/desktop",
    "docs/evals",
    "docs/gifs",
    "docs/human",
    "docs/mobile",
    "docs/qa",
    "docs/reports",
    "docs/runbooks",
    "docs/screenshots",
    "docs/sdk",
    "docs/security",
]

STALE_ACTIVE_DOC_MARKERS = {
    "docs/README.md": [
        "继续保持原路径作为权威来源",
    ],
    "docs/development/ai/00-master-prompt.md": [
        "docs/工作日志/archive/task-progress-human.md",
    ],
    "docs/development/git-github-workflow.md": [
        "docs/工作日志/archive/task-progress-human.md",
    ],
}

STAGE_FILES = [
    "docs/development/ai/stages/01-agent-workspace-console.md",
    "docs/development/ai/stages/02-agent-studio-config.md",
    "docs/development/ai/stages/03-harness-tool-mcp.md",
    "docs/development/ai/stages/04-event-sourcing-replay-ui.md",
    "docs/development/ai/stages/05-eval-regression.md",
    "docs/development/ai/stages/06-warmpool-infra.md",
]

REQUIRED_FILES = [
    "AGENTS.md",
    "README.md",
    "docs/README.md",
    "docs/PROJECT-SUMMARY.md",
    "docs/TASKS.md",
    "docs/development/ai/README.md",
    "docs/development/ai/00-execution-protocol.md",
    "docs/development/ai/agent-startup-context.md",
    "docs/development/ai/context-index.json",
    "docs/development/ai/feature-catalog.schema.json",
    "docs/development/ai/feature-catalog.json",
    "docs/development/ai/01-task-progress.md",
    "docs/development/ai/task-progress.yaml",
    "docs/plans/README.md",
    "docs/plans/TEMPLATE.md",
    "docs/contracts/SPEC-INDEX.md",
    "docs/architecture/MODULE-INDEX.md",
    "omx_wiki/index.md",
    "omx_wiki/project-handoff-current-state.md",
    *TOP_LEVEL_SPECS,
    *STAGE_FILES,
    "scripts/agent-context-brief.py",
    "scripts/feature_catalog.py",
    "scripts/test_feature_catalog.py",
    "docs/architecture/module-map.json",
    "docs/FEATURE-MATRIX.md",
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
    return path.read_text(encoding="utf-8")


def fail(message: str) -> None:
    print(f"docs validation failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def check_required_files() -> None:
    for rel in REQUIRED_FILES:
        if not (ROOT / rel).is_file():
            fail(f"missing required file: {rel}")


def check_docs_ci_contract() -> None:
    workflow = read_text(ROOT / ".github/workflows/docs.yml")
    required_markers = [
        "bash scripts/check-docs.sh",
        "git diff --exit-code docs/contracts/api-reference",
    ]
    for marker in required_markers:
        if marker not in workflow:
            fail(f"docs CI missing required command: {marker}")


def check_feature_catalog_contract() -> None:
    script = ROOT / "scripts/feature_catalog.py"
    schema = ROOT / "docs/development/ai/feature-catalog.schema.json"
    matrix = ROOT / "docs/FEATURE-MATRIX.md"
    schema_text = read_text(schema)
    for marker in ["Harness Feature Catalog", '"schema_version"', '"$defs"']:
        if marker not in schema_text:
            fail(f"feature catalog schema missing marker: {marker}")
    matrix_text = read_text(matrix)
    for marker in [
        "AUTO-GENERATED from docs/development/ai/feature-catalog.json",
        "python3 scripts/feature_catalog.py --generate",
        "# Harness 功能矩阵",
    ]:
        if marker not in matrix_text:
            fail(f"feature matrix missing marker: {marker}")
    for command in (
        [sys.executable, str(script), "--validate"],
        [sys.executable, str(script), "--check"],
        [sys.executable, "-m", "unittest", "scripts.test_feature_catalog"],
    ):
        completed = subprocess.run(command, cwd=ROOT, check=False, capture_output=True, text=True)
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            fail(f"feature catalog command failed ({' '.join(command)}): {detail}")
    check_docs_script = read_text(ROOT / "scripts/check-docs.sh")
    if "python3 -m unittest scripts.test_feature_catalog" not in check_docs_script:
        fail("scripts/check-docs.sh missing feature catalog regression command")


def check_large_plan_gate_contract() -> None:
    required_markers = {
        "AGENTS.md": [
            "Harness 大型计划拆分与确认门",
            "awaiting_user_confirmation",
            "每次只允许一个切片处于 `in_progress`",
        ],
        "docs/development/ai/00-execution-protocol.md": [
            "## Large Plan Decomposition Gate",
            "two to six ordered slices",
            "awaiting_user_confirmation",
            "exactly one slice `in_progress`",
        ],
        "docs/plans/README.md": [
            "## 大型计划确认门",
            "`2-6` 个有序",
            "`awaiting_user_confirmation`",
        ],
        "docs/plans/TEMPLATE.md": [
            "## 4. 规模判定与用户确认",
            "同一时间最多一个切片为 `in_progress`",
        ],
        "docs/development/ai/context-index.json": [
            '"id": "large-plan-decomposition"',
        ],
    }
    for rel, markers in required_markers.items():
        text = read_text(ROOT / rel)
        for marker in markers:
            if marker not in text:
                fail(f"large-plan gate missing marker in {rel}: {marker}")


def check_no_old_stage_docs() -> None:
    old_stage_docs = list((ROOT / "docs/development/ai").glob("[0-9][0-9]-stage-*.md"))
    if old_stage_docs:
        names = ", ".join(str(path.relative_to(ROOT)) for path in old_stage_docs)
        fail(f"old stage docs still present: {names}")


def check_no_legacy_doc_dirs() -> None:
    existing = [rel for rel in LEGACY_DOC_DIRS if (ROOT / rel).exists()]
    if existing:
        fail(f"legacy documentation directories still present: {', '.join(existing)}")


def check_no_stale_active_doc_markers() -> None:
    for rel, markers in STALE_ACTIVE_DOC_MARKERS.items():
        text = read_text(ROOT / rel)
        for marker in markers:
            if marker in text:
                fail(f"stale active-document marker found in {rel}: {marker}")


def check_blocked_terms() -> None:
    targets = [
        ROOT / "README.md",
        *[ROOT / rel for rel in TOP_LEVEL_SPECS],
        *[ROOT / rel for rel in STAGE_FILES],
        ROOT / "docs/development/ai/README.md",
        ROOT / "docs/development/ai/00-execution-protocol.md",
        ROOT / "docs/development/ai/01-task-progress.md",
        ROOT / "docs/development/ai/task-progress.yaml",
        ROOT / "docs/TASKS.md",
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
    yaml_text = read_text(ROOT / "docs/development/ai/task-progress.yaml")
    task_board_text = read_text(ROOT / "docs/TASKS.md")
    for rel in STAGE_FILES:
        if rel not in yaml_text:
            fail(f"{rel} missing from task-progress.yaml")
    if "spec_first_stage_gated_vertical_slice" not in yaml_text:
        fail("task-progress.yaml missing spec execution mode")
    for marker in ["## 进行中", "## 待办", "## 已完成", "## 技术债"]:
        if marker not in task_board_text:
            fail(f"docs/TASKS.md missing section {marker}")
    if "docs/development/ai/task-progress.yaml" not in task_board_text:
        fail("docs/TASKS.md missing machine progress source")


def check_agent_context_contract() -> None:
    agents_rel = "AGENTS.md"
    startup_rel = "docs/development/ai/agent-startup-context.md"
    index_rel = "docs/development/ai/context-index.json"
    script_rel = "scripts/agent-context-brief.py"
    agents_text = read_text(ROOT / agents_rel)
    startup_text = read_text(ROOT / startup_rel)
    protocol_text = read_text(ROOT / "docs/development/ai/00-execution-protocol.md")
    readme_text = read_text(ROOT / "README.md")
    wiki_index_text = read_text(ROOT / "omx_wiki/index.md")
    yaml_text = read_text(ROOT / "docs/development/ai/task-progress.yaml")

    required_startup_markers = [
        "Model + Harness = Agent",
        "docs/development/ai/task-progress.yaml",
        "scripts/agent-context-brief.py",
        "omx_wiki/project-handoff-current-state.md",
        "Completion Write-Back",
    ]
    for marker in required_startup_markers:
        if marker not in startup_text:
            fail(f"{startup_rel} missing marker {marker}")

    required_agents_markers = [
        "docs/development/ai/agent-startup-context.md",
        "docs/development/ai/task-progress.yaml",
        "scripts/agent-context-brief.py",
        "docs/development/ai/00-execution-protocol.md",
        "omx_wiki/",
    ]
    for marker in required_agents_markers:
        if marker not in agents_text:
            fail(f"{agents_rel} missing marker {marker}")

    for rel in [agents_rel, startup_rel, index_rel, script_rel]:
        if rel not in protocol_text:
            fail(f"execution protocol missing {rel}")
        if rel not in readme_text and rel != index_rel and rel != agents_rel:
            fail(f"README missing {rel}")
        if rel in [startup_rel, index_rel] and rel not in wiki_index_text:
            fail(f"wiki index missing {rel}")

    if "[[project-handoff-current-state]]" not in wiki_index_text:
        fail("wiki index missing canonical project handoff link")
    if "docs/development/ai/task-progress.yaml" not in yaml_text:
        fail("task-progress.yaml missing self-reference to machine progress source")

    try:
        context_index = json.loads(read_text(ROOT / index_rel))
    except json.JSONDecodeError as exc:
        fail(f"{index_rel} is not valid JSON: {exc}")

    if context_index.get("entrypoint") != startup_rel:
        fail(f"{index_rel} has wrong entrypoint")
    if context_index.get("machine_progress") != "docs/development/ai/task-progress.yaml":
        fail(f"{index_rel} has wrong machine progress source")

    routes = context_index.get("routes")
    if not isinstance(routes, list) or not routes:
        fail(f"{index_rel} must define at least one route")

    required_route_ids = {
        "agent-startup-context-loop",
        "feature-catalog",
        "large-plan-decomposition",
        "project-handoff",
        "knowledge-rag-grounding",
        "context-router-memory",
        "mcp-skills-capabilities",
        "eval-observability-groundedness",
        "release-demo-private-deploy",
        "frontend-ui-console",
        "local-dev-debugging",
    }
    route_ids = {str(route.get("id")) for route in routes if isinstance(route, dict)}
    missing_routes = sorted(required_route_ids - route_ids)
    if missing_routes:
        fail(f"{index_rel} missing routes: {', '.join(missing_routes)}")

    for route in routes:
        if not isinstance(route, dict):
            fail(f"{index_rel} route must be an object")
        route_id = str(route.get("id", "<missing>"))
        for field in ["summary", "keywords", "read_first", "deep_read", "progress_write_targets"]:
            if field not in route:
                fail(f"{index_rel} route {route_id} missing {field}")
        if not route.get("keywords"):
            fail(f"{index_rel} route {route_id} needs keywords")
        if not route.get("read_first"):
            fail(f"{index_rel} route {route_id} needs read_first paths")
        if "docs/development/ai/task-progress.yaml" not in route.get("progress_write_targets", []):
            fail(f"{index_rel} route {route_id} missing task-progress write target")
        for field in ["read_first", "deep_read"]:
            for rel in route.get(field, []):
                if not (ROOT / rel).exists():
                    fail(f"{index_rel} route {route_id} references missing path: {rel}")

    session_page = ROOT / "omx_wiki/session-2026-05-23-agent-startup-context-loop.md"
    session_text = read_text(session_page)
    if "status: verified" in yaml_text and "Planned validation" in session_text:
        fail("startup context session page still describes validation as planned")
    if "Completed validation" not in session_text:
        fail("startup context session page missing completed validation evidence")

    check_agent_context_brief_fixtures()


def check_agent_context_brief_fixtures() -> None:
    script = ROOT / "scripts/agent-context-brief.py"
    for task, expected_routes in BRIEF_ROUTE_FIXTURES.items():
        command = [sys.executable, str(script)]
        if task:
            command.extend(["--task", task])
        completed = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            fail(f"agent context brief failed for task {task!r}: {completed.stderr.strip()}")
        route_ids = [
            line.split("`", 2)[1]
            for line in completed.stdout.splitlines()
            if line.startswith("- `")
            and "`:" in line
            and not line.startswith("- `docs/")
            and not line.startswith("- `omx_wiki/")
            and not line.startswith("- `.omx/")
            and not line.startswith("- `scripts/")
        ]
        if route_ids != expected_routes:
            fail(
                "agent context brief route mismatch for "
                f"{task!r}: expected {expected_routes}, got {route_ids}"
            )
    for task, expectations in BRIEF_FEATURE_FIXTURES.items():
        completed = subprocess.run(
            [sys.executable, str(script), "--task", task, "--max-features", "6"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            fail(f"feature catalog brief failed for task {task!r}: {completed.stderr.strip()}")
        for feature_id in expectations["required"]:
            if f"`{feature_id}`" not in completed.stdout:
                fail(f"feature catalog brief missing {feature_id} for task {task!r}")
        for feature_id in expectations["forbidden"]:
            if f"`{feature_id}`" in completed.stdout:
                fail(f"feature catalog brief returned unrelated {feature_id} for task {task!r}")


def check_module_map() -> None:
    """Parse docs/architecture/module-map.json and assert every path/doc exists on disk (R4, R5)."""
    map_path = ROOT / "docs/architecture/module-map.json"
    try:
        data = json.loads(read_text(map_path))
    except json.JSONDecodeError as exc:
        fail(f"docs/architecture/module-map.json is not valid JSON: {exc}")
    modules = data.get("modules")
    if not isinstance(modules, list) or not modules:
        fail("docs/architecture/module-map.json must have a non-empty 'modules' list")
    for m in modules:
        name = m.get("name", "<unnamed>")
        for field in ("name", "path", "summary"):
            if not m.get(field):
                fail(f"docs/architecture/module-map.json module {name!r} missing field {field!r}")
        if not (ROOT / m["path"]).exists():
            fail(f"docs/architecture/module-map.json module {name!r} path not found: {m['path']}")
        for doc in m.get("docs", []):
            if not (ROOT / doc).exists():
                fail(f"docs/architecture/module-map.json module {name!r} references missing doc: {doc}")


def check_memory_files() -> None:
    """Assert error-registry.md and anti-patterns.md each have at least one ## heading (R4)."""
    for rel in ("docs/development/ai/error-registry.md", "docs/development/ai/anti-patterns.md"):
        path = ROOT / rel
        if not path.is_file():
            fail(f"missing memory file: {rel}")
        headings = [line for line in read_text(path).splitlines() if line.startswith("## ")]
        if not headings:
            fail(f"{rel} has no '## ' section headings — must contain at least one entry")


def check_readme_links() -> None:
    readme = read_text(ROOT / "README.md")
    for rel in TOP_LEVEL_SPECS + STAGE_FILES:
        link = f"./{rel}"
        if link not in readme and rel not in readme:
            fail(f"README missing link {rel}")


def main() -> None:
    check_required_files()
    check_docs_ci_contract()
    check_feature_catalog_contract()
    check_large_plan_gate_contract()
    check_no_old_stage_docs()
    check_no_legacy_doc_dirs()
    check_no_stale_active_doc_markers()
    check_blocked_terms()
    check_stage_docs()
    check_progress_alignment()
    check_agent_context_contract()
    check_module_map()
    check_memory_files()
    check_readme_links()
    print("docs validation passed")


if __name__ == "__main__":
    main()
