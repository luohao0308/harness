#!/usr/bin/env python3
from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MIGRATION_DIR = REPO_ROOT / "services/api-server/alembic/versions"


@dataclass(frozen=True)
class IdSeed:
    table_name: str
    value: str
    line: int


@dataclass(frozen=True)
class Violation:
    path: Path
    table_name: str
    column_length: int
    seed: IdSeed


class MigrationIdVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.table_id_lengths: dict[str, int] = {}
        self.table_names: dict[str, str] = {}
        self.constants: dict[str, object] = {}
        self.id_seeds: list[IdSeed] = []

    def visit_Assign(self, node: ast.Assign) -> None:
        value = self._literal(node.value)
        for target in node.targets:
            if isinstance(target, ast.Name) and value is not _UNKNOWN:
                self.constants[target.id] = value

        table_name = self._created_table_name(node.value) or self._sa_table_name(node.value)
        if table_name is not None:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.table_names[target.id] = table_name

        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name) and node.value is not None:
            value = self._literal(node.value)
            if value is not _UNKNOWN:
                self.constants[node.target.id] = value
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if self._is_call(node, "op.create_table"):
            table_name = self._first_string_arg(node)
            if table_name is not None:
                id_length = self._id_column_length(node)
                if id_length is not None:
                    self.table_id_lengths[table_name] = id_length
        if self._is_call(node, "op.bulk_insert") and len(node.args) >= 2:
            table_name = self._table_name(node.args[0])
            rows = self._literal(node.args[1])
            if table_name is not None:
                self.id_seeds.extend(self._extract_id_seeds(table_name, rows, node.lineno))
        self.generic_visit(node)

    def _created_table_name(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Call) and self._is_call(node, "op.create_table"):
            return self._first_string_arg(node)
        return None

    def _sa_table_name(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Call) and self._is_call(node, "sa.table"):
            return self._first_string_arg(node)
        return None

    def _first_string_arg(self, node: ast.Call) -> str | None:
        if not node.args:
            return None
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
        return None

    def _id_column_length(self, create_table: ast.Call) -> int | None:
        for arg in create_table.args[1:]:
            if not isinstance(arg, ast.Call) or not self._is_call(arg, "sa.Column"):
                continue
            if not arg.args:
                continue
            name = arg.args[0]
            if not (isinstance(name, ast.Constant) and name.value == "id"):
                continue
            for column_arg in arg.args[1:]:
                length = self._string_length(column_arg)
                if length is not None:
                    return length
        return None

    def _string_length(self, node: ast.AST) -> int | None:
        if not isinstance(node, ast.Call) or not self._is_call(node, "sa.String"):
            return None
        if node.args:
            first = self._literal(node.args[0])
            return first if isinstance(first, int) else None
        for keyword in node.keywords:
            if keyword.arg == "length":
                value = self._literal(keyword.value)
                return value if isinstance(value, int) else None
        return None

    def _table_name(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return self.table_names.get(node.id)
        if isinstance(node, ast.Call):
            return self._sa_table_name(node)
        return None

    def _extract_id_seeds(self, table_name: str, rows: object, fallback_line: int) -> list[IdSeed]:
        seeds: list[IdSeed] = []
        for item in _walk_literals(rows):
            if not isinstance(item, dict):
                continue
            seed_id = item.get("id")
            if isinstance(seed_id, str):
                seeds.append(IdSeed(table_name=table_name, value=seed_id, line=fallback_line))
        return seeds

    def _literal(self, node: ast.AST) -> object:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return self.constants.get(node.id, _UNKNOWN)
        if isinstance(node, ast.List):
            return [self._literal(item) for item in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(self._literal(item) for item in node.elts)
        if isinstance(node, ast.Set):
            return {self._literal(item) for item in node.elts}
        if isinstance(node, ast.Dict):
            values: dict[object, object] = {}
            for key_node, value_node in zip(node.keys, node.values, strict=True):
                if key_node is None:
                    continue
                key = self._literal(key_node)
                if key is _UNKNOWN:
                    continue
                values[key] = self._literal(value_node)
            return values
        try:
            return ast.literal_eval(node)
        except (ValueError, TypeError):
            return _UNKNOWN

    def _is_call(self, node: ast.Call, dotted_name: str) -> bool:
        return _dotted_name(node.func) == dotted_name


class _Unknown:
    pass


_UNKNOWN = _Unknown()


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _walk_literals(value: object) -> list[object]:
    found = [value]
    if isinstance(value, dict):
        for nested in value.values():
            found.extend(_walk_literals(nested))
    elif isinstance(value, (list, tuple, set)):
        for nested in value:
            found.extend(_walk_literals(nested))
    return found


def _migration_files(paths: list[str]) -> list[Path]:
    if not paths:
        paths = [str(DEFAULT_MIGRATION_DIR)]
    files: list[Path] = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_dir():
            files.extend(sorted(path.glob("*.py")))
        else:
            files.append(path)
    return [path for path in files if path.name != "__init__.py"]


def check_file(path: Path) -> list[Violation]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    visitor = MigrationIdVisitor()
    visitor.visit(tree)
    violations: list[Violation] = []
    for seed in visitor.id_seeds:
        column_length = visitor.table_id_lengths.get(seed.table_name)
        if column_length is None:
            continue
        if len(seed.value) > column_length:
            violations.append(
                Violation(
                    path=path,
                    table_name=seed.table_name,
                    column_length=column_length,
                    seed=seed,
                )
            )
    return violations


def main(argv: list[str] | None = None) -> int:
    paths = _migration_files(list(sys.argv[1:] if argv is None else argv))
    violations: list[Violation] = []
    for path in paths:
        violations.extend(check_file(path))

    if violations:
        for violation in violations:
            rel_path = (
                violation.path.relative_to(REPO_ROOT)
                if violation.path.is_relative_to(REPO_ROOT)
                else violation.path
            )
            print(
                f"{rel_path}:{violation.seed.line}: id {violation.seed.value!r} "
                f"(length {len(violation.seed.value)}) exceeds "
                f"{violation.table_name}.id VARCHAR({violation.column_length})",
                file=sys.stderr,
            )
        return 1

    print(f"migration id lint passed ({len(paths)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
