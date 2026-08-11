from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

DEFAULT_DATABASE_NAME = "harness.sqlite3"
MANIFEST_VERSION = 1


@dataclass(frozen=True)
class SQLiteRuntimePaths:
    user_data_dir: Path
    runtime_dir: Path
    backups_dir: Path
    logs_dir: Path
    manifest_path: Path
    lock_path: Path

    @property
    def default_database_path(self) -> Path:
        return self.runtime_dir / DEFAULT_DATABASE_NAME

    def database_url(self, database_path: Path | None = None) -> str:
        path = (database_path or self.active_database_path()).resolve()
        return f"sqlite+pysqlite:///{path.as_posix()}"

    def active_database_path(self) -> Path:
        manifest = self.read_manifest()
        name = manifest.get("active_database", DEFAULT_DATABASE_NAME)
        return self._database_path_from_name(name)

    def previous_database_path(self) -> Path | None:
        name = self.read_manifest().get("previous_database")
        return self._database_path_from_name(name) if name else None

    def read_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            return {"manifest_version": MANIFEST_VERSION, "active_database": DEFAULT_DATABASE_NAME}
        data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        if data.get("manifest_version") != MANIFEST_VERSION:
            raise ValueError("unsupported SQLite runtime manifest version")
        self._database_path_from_name(data.get("active_database"))
        if data.get("previous_database"):
            self._database_path_from_name(data["previous_database"])
        return data

    def switch_active_database(
        self,
        active_database: Path,
        *,
        previous_database: Path | None,
        alembic_revision: str,
    ) -> None:
        active_name = self._relative_database_name(active_database)
        previous_name = (
            self._relative_database_name(previous_database) if previous_database else None
        )
        manifest = {
            "manifest_version": MANIFEST_VERSION,
            "active_database": active_name,
            "previous_database": previous_name,
            "alembic_revision": alembic_revision,
            "switched_at": datetime.now(UTC).isoformat(),
        }
        self.write_manifest(manifest)

    def write_manifest(self, manifest: dict[str, Any]) -> None:
        self._database_path_from_name(manifest.get("active_database"))
        if manifest.get("previous_database"):
            self._database_path_from_name(manifest["previous_database"])
        temporary = self.manifest_path.with_name(
            f".{self.manifest_path.name}.{os.getpid()}.{uuid4().hex}.tmp"
        )
        payload = json.dumps(manifest, sort_keys=True, indent=2) + "\n"
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.manifest_path)
            _fsync_directory(self.runtime_dir)
        finally:
            temporary.unlink(missing_ok=True)

    def remove_manifest(self) -> None:
        self.manifest_path.unlink(missing_ok=True)
        _fsync_directory(self.runtime_dir)

    def _relative_database_name(self, path: Path) -> str:
        resolved = path.resolve()
        if resolved.parent != self.runtime_dir.resolve():
            raise ValueError("runtime database must be a direct child of the runtime directory")
        return resolved.name

    def _database_path_from_name(self, name: Any) -> Path:
        if not isinstance(name, str) or not name or Path(name).name != name:
            raise ValueError("runtime manifest contains an invalid database name")
        return self.runtime_dir / name


def resolve_sqlite_runtime_paths(user_data_dir: str | Path) -> SQLiteRuntimePaths:
    """Resolve mutable SQLite paths from Electron's explicit userData directory."""
    root = Path(user_data_dir).expanduser().resolve()
    runtime_dir = root / "runtime"
    backups_dir = runtime_dir / "backups"
    logs_dir = runtime_dir / "logs"
    for directory in (runtime_dir, backups_dir, logs_dir):
        directory.mkdir(parents=True, exist_ok=True)
    return SQLiteRuntimePaths(
        user_data_dir=root,
        runtime_dir=runtime_dir,
        backups_dir=backups_dir,
        logs_dir=logs_dir,
        manifest_path=runtime_dir / "runtime.json",
        lock_path=runtime_dir / "runtime.lock",
    )


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
