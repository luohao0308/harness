from __future__ import annotations

import os
import shutil
import sqlite3
from collections.abc import Callable
from contextlib import nullcontext, suppress
from pathlib import Path
from uuid import uuid4

from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command
from app.db.sqlite_backup import backup_sqlite_database
from app.db.sqlite_integrity import check_sqlite_integrity
from app.db.sqlite_runtime_directory import SQLiteRuntimePaths
from app.db.sqlite_runtime_lock import SQLiteRuntimeLock

FaultInjector = Callable[[str], None]


def migrate_sqlite_candidate(
    paths: SQLiteRuntimePaths,
    *,
    alembic_ini: str | Path,
    fault_injector: FaultInjector | None = None,
    runtime_lock: SQLiteRuntimeLock | None = None,
) -> Path:
    """Migrate a candidate and atomically select it, restoring the pointer on failure."""
    inject = fault_injector or (lambda _point: None)
    if runtime_lock is not None:
        if not runtime_lock.acquired:
            raise RuntimeError("the supplied SQLite runtime lock is not acquired")
        if runtime_lock.lock_path.resolve() != paths.lock_path.resolve():
            raise ValueError("the supplied SQLite runtime lock belongs to a different runtime")
    lock_context = (
        nullcontext(runtime_lock)
        if runtime_lock is not None
        else SQLiteRuntimeLock(paths.lock_path)
    )
    with lock_context:
        source = paths.active_database_path()
        source_exists = source.is_file()
        if source_exists:
            check_sqlite_integrity(source)
            inject("after_source_integrity")
            if fault_injector is None and _database_is_at_head(source, alembic_ini):
                _prune_obsolete_databases(paths, keep=(source, paths.previous_database_path()))
                return source
            _require_candidate_space(paths.runtime_dir, source.stat().st_size)

        candidate = (
            paths.runtime_dir / f"harness-candidate-{uuid4().hex}.sqlite3"
            if source_exists
            else paths.default_database_path
        )
        manifest_existed = paths.manifest_path.exists()
        previous_manifest = paths.read_manifest()
        switched = False
        try:
            if source_exists:
                backup_sqlite_database(source, candidate)
            else:
                sqlite3.connect(candidate).close()
            inject("after_backup")

            revision = _upgrade_to_head(candidate, alembic_ini, inject)
            inject("after_migration")
            _checkpoint_and_fsync(candidate)
            check_sqlite_integrity(candidate)
            _verify_revision(candidate, revision)
            inject("after_candidate_integrity")

            paths.switch_active_database(
                candidate,
                previous_database=source if source_exists else None,
                alembic_revision=revision,
            )
            switched = True
            inject("after_pointer_switch")
            check_sqlite_integrity(paths.active_database_path())
            inject("before_serve")
            _prune_obsolete_databases(
                paths,
                keep=(candidate, source if source_exists else None),
            )
            return candidate
        except BaseException:
            if switched:
                if manifest_existed:
                    paths.write_manifest(previous_manifest)
                else:
                    paths.remove_manifest()
            candidate.unlink(missing_ok=True)
            for suffix in ("-wal", "-shm"):
                Path(f"{candidate}{suffix}").unlink(missing_ok=True)
            raise


def create_fresh_sqlite_candidate(
    database_path: str | Path,
    *,
    alembic_ini: str | Path,
    fault_injector: FaultInjector | None = None,
) -> str:
    """Create an empty canonical SQLite candidate without selecting it."""
    candidate = Path(database_path).resolve()
    if candidate.exists():
        raise FileExistsError(candidate)
    candidate.parent.mkdir(parents=True, exist_ok=True)
    sqlite3.connect(candidate).close()
    try:
        revision = _upgrade_to_head(
            candidate,
            alembic_ini,
            fault_injector or (lambda _point: None),
        )
        _checkpoint_and_fsync(candidate)
        check_sqlite_integrity(candidate)
        _verify_revision(candidate, revision)
        return revision
    except BaseException:
        candidate.unlink(missing_ok=True)
        for suffix in ("-wal", "-shm"):
            Path(f"{candidate}{suffix}").unlink(missing_ok=True)
        raise


def _upgrade_to_head(
    database_path: Path,
    alembic_ini: str | Path,
    fault_injector: FaultInjector,
) -> str:
    config = Config(str(alembic_ini))
    config.attributes["database_url"] = (
        f"sqlite+pysqlite:///{database_path.resolve().as_posix()}"
    )

    def _after_revision(*, step: object, **_kwargs: object) -> None:
        revision = getattr(step, "up_revision_id", "unknown")
        fault_injector(f"after_migration:{revision}")

    config.attributes["on_version_apply"] = _after_revision
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"candidate migration requires one Alembic head, found {heads!r}")
    command.upgrade(config, "head")
    return heads[0]


def _verify_revision(database_path: Path, expected_revision: str) -> None:
    connection = sqlite3.connect(database_path)
    try:
        rows = connection.execute("SELECT version_num FROM alembic_version")
        revisions = tuple(row[0] for row in rows)
    finally:
        connection.close()
    if revisions != (expected_revision,):
        raise RuntimeError(
            f"candidate Alembic revision mismatch: expected {expected_revision}, got {revisions!r}"
        )


def _database_is_at_head(database_path: Path, alembic_ini: str | Path) -> bool:
    config = Config(str(alembic_ini))
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"candidate migration requires one Alembic head, found {heads!r}")
    connection = sqlite3.connect(database_path)
    try:
        revisions = tuple(
            row[0] for row in connection.execute("SELECT version_num FROM alembic_version")
        )
    except sqlite3.DatabaseError:
        return False
    finally:
        connection.close()
    return revisions == (heads[0],)


def _prune_obsolete_databases(
    paths: SQLiteRuntimePaths,
    *,
    keep: tuple[Path | None, ...],
) -> None:
    keep_names = {path.name for path in keep if path is not None}
    managed = [paths.default_database_path]
    managed.extend(paths.runtime_dir.glob("harness-candidate-*.sqlite3"))
    managed.extend(paths.runtime_dir.glob("harness-import-*.sqlite3"))
    for database in managed:
        if database.name in keep_names:
            continue
        for suffix in ("-wal", "-shm", ""):
            with suppress(OSError):
                Path(f"{database}{suffix}").unlink(missing_ok=True)


def _checkpoint_and_fsync(database_path: Path) -> None:
    connection = sqlite3.connect(database_path)
    try:
        result = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    finally:
        connection.close()
    if result is None or result[0] != 0:
        raise RuntimeError(f"candidate WAL checkpoint failed: {result!r}")
    descriptor = os.open(database_path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    if os.name != "nt":
        directory_descriptor = os.open(database_path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)


def _require_candidate_space(runtime_dir: Path, source_size: int) -> None:
    required = max(1024 * 1024, source_size * 2)
    available = shutil.disk_usage(runtime_dir).free
    if available < required:
        raise OSError(f"insufficient space for SQLite candidate: need {required}, have {available}")
    if not os.access(runtime_dir, os.W_OK):
        raise PermissionError(f"SQLite runtime directory is not writable: {runtime_dir}")
