#!/usr/bin/env python3
"""Validate, query, and render the repository feature catalog.

The catalog intentionally uses JSON so the startup and docs checks remain
standard-library-only. The adjacent JSON Schema documents the public shape;
this module owns the cross-entry semantics that JSON Schema cannot express.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "docs/development/ai/feature-catalog.json"
SCHEMA_PATH = ROOT / "docs/development/ai/feature-catalog.schema.json"
MATRIX_PATH = ROOT / "docs/FEATURE-MATRIX.md"

ITEM_LEVELS = ("domain", "capability", "feature")
IMPLEMENTATION_STATUSES = ("not_started", "in_progress", "implemented", "verified")
MATURITIES = ("prototype", "beta", "production_candidate", "production_ready", "production_proven")
PLATFORMS = ("api", "web", "desktop", "mobile", "deploy")
EVIDENCE_KINDS = ("unit", "integration", "e2e", "smoke", "release", "live", "docs")
EVIDENCE_RESULTS = ("passed", "blocked", "partial")
SEARCH_STOPWORDS = {"a", "an", "and", "for", "in", "of", "on", "or", "the", "to", "with"}
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TASK_PATTERN = re.compile(r"^[A-Z][A-Z0-9-]+$")
DATE_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
ITEM_FIELDS = {
    "id",
    "parent_id",
    "level",
    "name",
    "summary",
    "keywords",
    "platforms",
    "implementation_status",
    "maturity",
    "acceptance_criteria",
    "code_paths",
    "spec_paths",
    "test_paths",
    "evidence",
    "known_gaps",
    "task_ids",
}
EVIDENCE_FIELDS = {"kind", "command", "result", "verified_at", "commit", "ref"}


class CatalogError(ValueError):
    """A catalog error that should produce a short CLI diagnostic."""


def _fail(message: str) -> None:
    raise CatalogError(message)


def _is_string(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        _fail(f"{field} must be a non-empty string")
    return value


def _is_string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        _fail(f"{field} must be an array")
    result = [_is_string(item, f"{field}[]") for item in value]
    if len(result) != len(set(result)):
        _fail(f"{field} contains duplicates")
    return result


def _relative_path_exists(value: str, field: str) -> None:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or any(char in value for char in "*?["):
        _fail(f"{field} must be a safe repository-relative path: {value}")
    if not (ROOT / path).exists():
        _fail(f"{field} references missing path: {value}")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _fail(f"missing catalog file: {path.relative_to(ROOT)}")
    except json.JSONDecodeError as exc:
        _fail(f"invalid JSON in {path.relative_to(ROOT)}: {exc}")
    if not isinstance(value, dict):
        _fail(f"{path.relative_to(ROOT)} must contain a JSON object")
    return value


def _validate_schema_document() -> None:
    schema = _load_json(SCHEMA_PATH)
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        _fail("feature catalog schema must declare JSON Schema 2020-12")
    if schema.get("title") != "Harness Feature Catalog":
        _fail("feature catalog schema has an unexpected title")
    definitions = schema.get("$defs")
    if not isinstance(definitions, dict) or "item" not in definitions or "evidence" not in definitions:
        _fail("feature catalog schema must define item and evidence")


def _validate_evidence(item_id: str, evidence: Any) -> list[dict[str, Any]]:
    if not isinstance(evidence, list):
        _fail(f"{item_id}.evidence must be an array")
    validated: list[dict[str, Any]] = []
    for index, raw in enumerate(evidence):
        if not isinstance(raw, dict):
            _fail(f"{item_id}.evidence[{index}] must be an object")
        unknown = set(raw) - EVIDENCE_FIELDS
        if unknown:
            _fail(f"{item_id}.evidence[{index}] has unknown fields: {sorted(unknown)}")
        missing = EVIDENCE_FIELDS - set(raw)
        if missing:
            _fail(f"{item_id}.evidence[{index}] missing fields: {sorted(missing)}")
        kind = _is_string(raw["kind"], f"{item_id}.evidence[{index}].kind")
        result = _is_string(raw["result"], f"{item_id}.evidence[{index}].result")
        if kind not in EVIDENCE_KINDS:
            _fail(f"{item_id}.evidence[{index}] has unknown kind: {kind}")
        if result not in EVIDENCE_RESULTS:
            _fail(f"{item_id}.evidence[{index}] has unknown result: {result}")
        verified_at = _is_string(raw["verified_at"], f"{item_id}.evidence[{index}].verified_at")
        if not DATE_PATTERN.fullmatch(verified_at):
            _fail(f"{item_id}.evidence[{index}].verified_at must be YYYY-MM-DD")
        _is_string(raw["command"], f"{item_id}.evidence[{index}].command")
        ref = _is_string(raw["ref"], f"{item_id}.evidence[{index}].ref")
        _relative_path_exists(ref, f"{item_id}.evidence[{index}].ref")
        commit = raw["commit"]
        if commit is not None:
            _is_string(commit, f"{item_id}.evidence[{index}].commit")
        validated.append(raw)
    return validated


def _validate_item(raw: Any, index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        _fail(f"items[{index}] must be an object")
    item_id = raw.get("id", f"items[{index}]")
    _is_string(item_id, f"items[{index}].id")
    unknown = set(raw) - ITEM_FIELDS
    if unknown:
        _fail(f"{item_id} has unknown fields: {sorted(unknown)}")
    missing = ITEM_FIELDS - set(raw)
    if missing:
        _fail(f"{item_id} missing fields: {sorted(missing)}")
    if not ID_PATTERN.fullmatch(item_id):
        _fail(f"{item_id}.id must be kebab-case")
    parent_id = raw["parent_id"]
    if parent_id is not None:
        _is_string(parent_id, f"{item_id}.parent_id")
    level = _is_string(raw["level"], f"{item_id}.level")
    if level not in ITEM_LEVELS:
        _fail(f"{item_id}.level has unknown value: {level}")
    for field in ("name", "summary"):
        _is_string(raw[field], f"{item_id}.{field}")
    keywords = _is_string_list(raw["keywords"], f"{item_id}.keywords")
    platforms = _is_string_list(raw["platforms"], f"{item_id}.platforms")
    if any(platform not in PLATFORMS for platform in platforms):
        _fail(f"{item_id}.platforms has an unknown value")
    implementation_status = _is_string(raw["implementation_status"], f"{item_id}.implementation_status")
    if implementation_status not in IMPLEMENTATION_STATUSES:
        _fail(f"{item_id}.implementation_status has unknown value: {implementation_status}")
    maturity = _is_string(raw["maturity"], f"{item_id}.maturity")
    if maturity not in MATURITIES:
        _fail(f"{item_id}.maturity has unknown value: {maturity}")
    for field in ("acceptance_criteria", "code_paths", "spec_paths", "test_paths", "known_gaps"):
        _is_string_list(raw[field], f"{item_id}.{field}")
    task_ids = _is_string_list(raw["task_ids"], f"{item_id}.task_ids")
    if any(not TASK_PATTERN.fullmatch(task_id) for task_id in task_ids):
        _fail(f"{item_id}.task_ids contains an invalid task ID")
    for field in ("code_paths", "spec_paths", "test_paths"):
        for path in raw[field]:
            _relative_path_exists(path, f"{item_id}.{field}[]")
    evidence = _validate_evidence(item_id, raw["evidence"])

    if level == "domain" and parent_id is not None:
        _fail(f"{item_id}: domain entries cannot have a parent")
    if level != "domain" and parent_id is None:
        _fail(f"{item_id}: {level} entries must have a parent")
    if level == "feature":
        if not raw["acceptance_criteria"]:
            _fail(f"{item_id}: feature requires acceptance_criteria")
        if not raw["test_paths"]:
            _fail(f"{item_id}: feature requires test_paths")
        if not evidence:
            _fail(f"{item_id}: feature requires evidence")
    if implementation_status == "not_started" and maturity not in ("prototype", "beta"):
        _fail(f"{item_id}: not_started cannot claim {maturity}")
    if implementation_status == "in_progress" and maturity in ("production_ready", "production_proven"):
        _fail(f"{item_id}: in_progress cannot claim {maturity}")
    if implementation_status == "verified" and level == "feature":
        if not any(entry["result"] == "passed" for entry in evidence):
            _fail(f"{item_id}: verified feature requires passed evidence")
    if maturity == "production_candidate" and level == "feature":
        if not any(entry["result"] == "passed" for entry in evidence):
            _fail(f"{item_id}: production_candidate requires passed evidence")
    if maturity == "production_ready" and level == "feature":
        required_kinds = {"unit", "integration", "e2e", "release"}
        actual_kinds = {entry["kind"] for entry in evidence if entry["result"] == "passed"}
        if not required_kinds.issubset(actual_kinds):
            _fail(f"{item_id}: production_ready requires passed unit/integration/e2e/release evidence")
    if maturity == "production_proven" and level == "feature":
        if not any(entry["kind"] in {"release", "live"} and entry["result"] == "passed" for entry in evidence):
            _fail(f"{item_id}: production_proven requires passed release or live evidence")
    return {
        **raw,
        "keywords": keywords,
        "platforms": platforms,
        "evidence": evidence,
    }


def load_catalog() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    _validate_schema_document()
    catalog = _load_json(CATALOG_PATH)
    expected_fields = {"schema_version", "catalog_version", "updated_at", "title", "items"}
    unknown = set(catalog) - expected_fields
    if unknown:
        _fail(f"catalog has unknown fields: {sorted(unknown)}")
    if set(catalog) != expected_fields:
        _fail(f"catalog missing fields: {sorted(expected_fields - set(catalog))}")
    if catalog["schema_version"] != 1:
        _fail("catalog schema_version must be 1")
    if not isinstance(catalog["catalog_version"], int) or catalog["catalog_version"] < 1:
        _fail("catalog_version must be a positive integer")
    updated_at = _is_string(catalog["updated_at"], "catalog.updated_at")
    if not DATE_PATTERN.fullmatch(updated_at):
        _fail("catalog.updated_at must be YYYY-MM-DD")
    _is_string(catalog["title"], "catalog.title")
    if not isinstance(catalog["items"], list) or not catalog["items"]:
        _fail("catalog.items must be a non-empty array")
    items = [_validate_item(raw, index) for index, raw in enumerate(catalog["items"])]
    by_id: dict[str, dict[str, Any]] = {}
    for item in items:
        if item["id"] in by_id:
            _fail(f"duplicate item id: {item['id']}")
        by_id[item["id"]] = item
    for item in items:
        parent_id = item["parent_id"]
        if parent_id is None:
            continue
        parent = by_id.get(parent_id)
        if parent is None:
            _fail(f"{item['id']} references missing parent: {parent_id}")
        expected_parent = {"capability": "domain", "feature": "capability"}[item["level"]]
        if parent["level"] != expected_parent:
            _fail(f"{item['id']} must have a {expected_parent} parent")
    for item in items:
        seen: set[str] = set()
        current = item
        while current["parent_id"] is not None:
            if current["id"] in seen:
                _fail(f"catalog hierarchy contains a cycle at {current['id']}")
            seen.add(current["id"])
            current = by_id[current["parent_id"]]
    task_board = (ROOT / "docs/TASKS.md").read_text(encoding="utf-8")
    progress = (ROOT / "docs/development/ai/task-progress.yaml").read_text(encoding="utf-8")
    for item in items:
        for task_id in item["task_ids"]:
            if task_id not in task_board and task_id not in progress:
                _fail(f"{item['id']} references unknown task ID: {task_id}")
    return catalog, by_id


def _item_sort_key(item: dict[str, Any]) -> tuple[int, str]:
    return ({"domain": 0, "capability": 1, "feature": 2}[item["level"]], item["id"])


def ordered_items(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {item["id"]: item for item in items}
    children: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        children[item["parent_id"]].append(item)
    for values in children.values():
        values.sort(key=lambda item: item["id"])
    result: list[dict[str, Any]] = []

    def visit(parent_id: str | None) -> None:
        for item in children.get(parent_id, []):
            result.append(item)
            visit(item["id"])

    visit(None)
    if len(result) != len(by_id):
        _fail("catalog cannot be deterministically ordered")
    return result


def _plain(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _search_score(item: dict[str, Any], query: str) -> int:
    normalized = _plain(query)
    if not normalized:
        return 0
    if normalized == item["id"]:
        return 1000
    content = _plain(" ".join([
        item["id"], item["name"], item["summary"], *item["keywords"],
        *item["known_gaps"], *item["task_ids"],
    ]))
    score = 0
    if normalized in content:
        score += 20
    tokens = [
        token
        for token in re.split(r"[^a-z0-9]+", normalized)
        if token and token not in SEARCH_STOPWORDS
    ]
    score += sum(
        4
        for token in tokens
        if re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", content)
    )
    if normalized in item["platforms"]:
        score += 8
    return score


def query_catalog(query: str, limit: int) -> list[dict[str, Any]]:
    _, by_id = load_catalog()
    if limit < 1:
        _fail("query limit must be positive")
    scored = [(score, item) for item in by_id.values() if (score := _search_score(item, query)) > 0]
    scored.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    for _, item in scored:
        candidate = [item]
        parent_id = item["parent_id"]
        while parent_id is not None:
            if parent_id not in selected_ids and parent_id not in {entry["id"] for entry in candidate}:
                candidate.append(by_id[parent_id])
            parent_id = by_id[parent_id]["parent_id"]
        new_ids = {entry["id"] for entry in candidate} - selected_ids
        if selected and len(selected) + len(new_ids) > limit:
            continue
        selected.extend(entry for entry in candidate if entry["id"] not in selected_ids)
        selected_ids.update(new_ids)
        if len(selected) >= limit:
            break
    return selected[:limit]


def _md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").replace("`", "'")


def _evidence_summary(item: dict[str, Any]) -> str:
    if not item["evidence"]:
        return "—"
    return "; ".join(f"{entry['kind']}:{entry['result']}" for entry in item["evidence"])


def render_matrix(catalog: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> str:
    items = ordered_items(by_id.values())
    domains = [item for item in items if item["level"] == "domain"]
    leaves = [item for item in items if item["level"] == "feature"]
    verified = sum(item["implementation_status"] == "verified" for item in leaves)
    in_progress = sum(item["implementation_status"] == "in_progress" for item in leaves)
    lines = [
        "<!-- AUTO-GENERATED from docs/development/ai/feature-catalog.json — do not hand-edit -->",
        "<!-- Regenerate: python3 scripts/feature_catalog.py --generate -->",
        "",
        "# Harness 功能矩阵",
        "",
        f"目录版本：`{catalog['catalog_version']}` · 更新：`{catalog['updated_at']}` · 领域：`{len(domains)}` · 能力：`{sum(item['level'] == 'capability' for item in items)}` · 具体功能：`{len(leaves)}`",
        "",
        f"实现统计：已验证 `{verified}` · 进行中 `{in_progress}` · 其他 `{len(leaves) - verified - in_progress}`",
        "",
        "> 实现状态和生产成熟度是两个维度：`verified` 不等于 `production_ready`，本目录不使用人工百分比。",
        "",
        "## 领域概览",
        "",
        "| 领域 | 能力数 | 具体功能数 | 已验证 | 进行中 | 主要成熟度 | 开放缺口 |",
        "| --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for domain in domains:
        capabilities = [item for item in items if item["parent_id"] == domain["id"]]
        domain_features = [item for item in leaves if any(item["parent_id"] == capability["id"] for capability in capabilities)]
        gaps = sorted({gap for item in domain_features for gap in item["known_gaps"]})
        maturity = sorted({item["maturity"] for item in domain_features})
        lines.append(
            f"| `{domain['id']}` { _md(domain['name']) } | {len(capabilities)} | {len(domain_features)} | "
            f"{sum(item['implementation_status'] == 'verified' for item in domain_features)} | "
            f"{sum(item['implementation_status'] == 'in_progress' for item in domain_features)} | "
            f"{', '.join(maturity) or '—'} | {_md('; '.join(gaps) or '—')} |"
        )
    lines.extend(["", "## 具体功能", "", "| ID | 功能 | 实现状态 | 成熟度 | 支持端 | 验收标准 | 证据 | 已知缺口 |", "| --- | --- | --- | --- | --- | --- | --- | --- |"])
    for item in leaves:
        parent = by_id[item["parent_id"]]
        domain = by_id[parent["parent_id"]]
        criteria = "；".join(item["acceptance_criteria"])
        gaps = "；".join(item["known_gaps"]) or "—"
        lines.append(
            f"| `{item['id']}` | {_md(domain['name'])} / {_md(parent['name'])} / {_md(item['name'])} | "
            f"`{item['implementation_status']}` | `{item['maturity']}` | `{', '.join(item['platforms'])}` | "
            f"{_md(criteria)} | `{_md(_evidence_summary(item))}` | {_md(gaps)} |"
        )
    lines.extend([
        "",
        "## 字段解释",
        "",
        "- `implementation_status`：`not_started`、`in_progress`、`implemented`、`verified`。",
        "- `maturity`：`prototype`、`beta`、`production_candidate`、`production_ready`、`production_proven`。",
        "- `production_ready` 和 `production_proven` 需要对应的发布/真实环境证据；当前目录保持保守标注。",
        "",
        "## 机器入口",
        "",
        "- 校验：`python3 scripts/feature_catalog.py --validate`",
        "- 生成：`python3 scripts/feature_catalog.py --generate`",
        "- 漂移检查：`python3 scripts/feature_catalog.py --check`",
        "- 查询：`python3 scripts/feature_catalog.py --query \"RAG retrieval\"`",
        "",
    ])
    return "\n".join(lines)


def write_matrix(content: str) -> None:
    temporary = MATRIX_PATH.with_suffix(".md.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(MATRIX_PATH)


def run_validate() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    catalog, by_id = load_catalog()
    items = list(by_id.values())
    print(
        f"feature catalog valid: {len(items)} items, "
        f"{sum(item['level'] == 'domain' for item in items)} domains, "
        f"{sum(item['level'] == 'capability' for item in items)} capabilities, "
        f"{sum(item['level'] == 'feature' for item in items)} features"
    )
    return catalog, by_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and render the Harness feature catalog.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate", action="store_true", help="Validate catalog structure and semantics.")
    mode.add_argument("--generate", action="store_true", help="Validate and generate the Markdown matrix.")
    mode.add_argument("--check", action="store_true", help="Validate and check generated matrix drift.")
    mode.add_argument("--query", metavar="TEXT", help="Query matching features and required ancestors.")
    parser.add_argument("--limit", type=int, default=8, help="Maximum query results, including ancestors.")
    parser.add_argument("--json", action="store_true", help="Render query results as JSON.")
    args = parser.parse_args()
    try:
        if args.query is not None:
            matches = query_catalog(args.query, args.limit)
            if args.json:
                print(json.dumps(matches, ensure_ascii=False, indent=2, sort_keys=True))
            elif not matches:
                print("no feature matches")
            else:
                for item in matches:
                    print(
                        f"{item['id']}\t{item['level']}\t{item['implementation_status']}\t"
                        f"{item['maturity']}\t{item['name']}"
                    )
            return 0
        catalog, by_id = run_validate()
        rendered = render_matrix(catalog, by_id)
        if args.generate:
            write_matrix(rendered)
            print(f"generated {MATRIX_PATH.relative_to(ROOT)}")
        elif args.check:
            if not MATRIX_PATH.is_file():
                _fail(f"missing generated matrix: {MATRIX_PATH.relative_to(ROOT)}")
            current = MATRIX_PATH.read_text(encoding="utf-8")
            if current != rendered:
                _fail(f"generated matrix is stale: run python3 scripts/feature_catalog.py --generate")
            print(f"feature matrix current: {MATRIX_PATH.relative_to(ROOT)}")
        return 0
    except CatalogError as exc:
        print(f"feature catalog validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
