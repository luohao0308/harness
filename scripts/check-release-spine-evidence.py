#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REQUIRED_CHECKS: tuple[tuple[str, str], ...] = (
    ("package_staging.private_package_staged", "private package was staged/uploaded"),
    ("package_staging.public_package_staged", "public URL/Git package was staged"),
    (
        "package_staging.public_validation_no_execution",
        "public package validation recorded no code execution",
    ),
    ("agent.agent_created_or_cloned", "Agent was created or cloned"),
    ("agent.attachments.mcp", "Agent has an MCP capability attachment"),
    ("agent.attachments.skill", "Agent has a Skill capability attachment"),
    ("agent.attachments.tool", "Agent has a Tool capability attachment"),
    (
        "agent.attachments.knowledge_connector",
        "Agent has a knowledge connector capability attachment",
    ),
    ("knowledge_connector.usable", "knowledge connector is labeled usable"),
    ("knowledge_connector.synced_or_reindexed", "knowledge connector sync/reindex completed"),
    ("workspace.multi_agent_orchestration", "Workspace run recorded multi-agent orchestration"),
    ("workspace.subagent_run_inspectable", "Workspace run produced inspectable subagent evidence"),
    ("run_detail.capability_snapshot", "Run Detail shows capability snapshot evidence"),
    ("run_detail.orchestration_evidence", "Run Detail shows router/assignment/handoff evidence"),
    ("run_detail.knowledge_evidence", "Run Detail shows connector/citation evidence"),
    ("run_detail.context_manifest", "Run Detail shows context manifest evidence"),
    ("run_detail.token_cost_panel", "Run Detail shows token/cost evidence"),
)

TEMPLATE: dict[str, Any] = {
    "schema_version": "phase0b-release-spine-evidence.v1",
    "generated_by": "scripts/check-release-spine-evidence.py --write-template",
    "package_staging": {
        "private_package_staged": False,
        "public_package_staged": False,
        "public_validation_no_execution": False,
        "evidence_refs": [],
    },
    "agent": {
        "agent_created_or_cloned": False,
        "agent_id": "",
        "attachments": {
            "mcp": False,
            "skill": False,
            "tool": False,
            "knowledge_connector": False,
        },
    },
    "knowledge_connector": {
        "usable": False,
        "synced_or_reindexed": False,
        "source_id": "",
        "evidence_refs": [],
    },
    "workspace": {
        "run_id": "",
        "multi_agent_orchestration": False,
        "subagent_run_inspectable": False,
        "evidence_refs": [],
    },
    "run_detail": {
        "capability_snapshot": False,
        "orchestration_evidence": False,
        "knowledge_evidence": False,
        "context_manifest": False,
        "token_cost_panel": False,
        "evidence_refs": [],
    },
    "verification_commands": [],
}


def get_path(payload: dict[str, Any], dotted_path: str) -> Any:
    value: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def validate(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if payload.get("schema_version") != TEMPLATE["schema_version"]:
        failures.append(
            f"schema_version must be {TEMPLATE['schema_version']!r}; "
            f"got {payload.get('schema_version')!r}"
        )
    for dotted_path, description in REQUIRED_CHECKS:
        if get_path(payload, dotted_path) is not True:
            failures.append(f"{dotted_path}: missing true value for {description}")
    commands = payload.get("verification_commands")
    if not isinstance(commands, list) or not commands:
        failures.append(
            "verification_commands: at least one release verification command is required"
        )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Phase 0b release spine evidence without OMX runtime dependencies."
    )
    parser.add_argument("evidence", nargs="?", help="Path to Phase 0b evidence JSON")
    parser.add_argument(
        "--write-template", help="Write a blank evidence JSON template to this path"
    )
    args = parser.parse_args()

    if args.write_template:
        output = Path(args.write_template)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(TEMPLATE, indent=2, ensure_ascii=False) + "\n")
        print(f"wrote Phase 0b evidence template: {output}")
        return 0

    if not args.evidence:
        parser.error("evidence path is required unless --write-template is used")

    path = Path(args.evidence)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"release spine evidence validation failed: {exc}", file=sys.stderr)
        return 1
    if not isinstance(payload, dict):
        print(
            "release spine evidence validation failed: top-level JSON must be an object",
            file=sys.stderr,
        )
        return 1

    failures = validate(payload)
    if failures:
        print("release spine evidence validation failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("release spine evidence validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
