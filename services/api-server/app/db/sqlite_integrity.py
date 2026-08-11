from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


class SQLiteIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True)
class SQLiteIntegrityResult:
    quick_check: tuple[str, ...]
    foreign_key_violations: tuple[tuple[object, ...], ...]


def check_sqlite_integrity(database_path: str | Path) -> SQLiteIntegrityResult:
    path = Path(database_path)
    if not path.is_file():
        raise SQLiteIntegrityError(f"SQLite database does not exist: {path}")
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        quick_check = tuple(str(row[0]) for row in connection.execute("PRAGMA quick_check"))
        violations = tuple(connection.execute("PRAGMA foreign_key_check"))
    finally:
        connection.close()
    if quick_check != ("ok",):
        raise SQLiteIntegrityError(f"SQLite quick_check failed: {quick_check!r}")
    if violations:
        raise SQLiteIntegrityError(f"SQLite foreign key check failed: {violations!r}")
    return SQLiteIntegrityResult(quick_check, violations)
