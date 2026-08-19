from __future__ import annotations

import json
import multiprocessing
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.models import Agent, AgentEvent, AgentRun, Task, Team
from app.db.session import (
    SQLITE_BUSY_TIMEOUT_MS,
    SQLITE_JOURNAL_SIZE_LIMIT_BYTES,
    SQLITE_WAL_AUTOCHECKPOINT_PAGES,
    create_database_engine,
)
from app.db.sqlite_backup import backup_sqlite_database
from app.db.sqlite_candidate_migration import (
    create_fresh_sqlite_candidate,
    install_fresh_sqlite_template,
    migrate_sqlite_candidate,
)
from app.db.sqlite_integrity import SQLiteIntegrityError, check_sqlite_integrity
from app.db.sqlite_runtime_directory import resolve_sqlite_runtime_paths
from app.db.sqlite_runtime_lock import SQLiteRuntimeLock, SQLiteRuntimeLockUnavailable

API_SERVER_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = API_SERVER_DIR / "alembic.ini"


def test_explicit_runtime_url_and_sqlite_pragmas(tmp_path: Path) -> None:
    paths = resolve_sqlite_runtime_paths(tmp_path / "Electron User Data")
    database_url = paths.database_url()

    assert database_url.startswith("sqlite+pysqlite:////")
    assert "Electron User Data/runtime/harness.sqlite3" in database_url

    engine = create_database_engine(database_url)
    try:
        with engine.connect() as connection:
            pragmas = {
                "foreign_keys": connection.execute(text("PRAGMA foreign_keys")).scalar_one(),
                "journal_mode": connection.execute(text("PRAGMA journal_mode")).scalar_one(),
                "busy_timeout": connection.execute(text("PRAGMA busy_timeout")).scalar_one(),
                "wal_autocheckpoint": connection.execute(
                    text("PRAGMA wal_autocheckpoint")
                ).scalar_one(),
                "journal_size_limit": connection.execute(
                    text("PRAGMA journal_size_limit")
                ).scalar_one(),
            }
    finally:
        engine.dispose()

    assert pragmas == {
        "foreign_keys": 1,
        "journal_mode": "wal",
        "busy_timeout": SQLITE_BUSY_TIMEOUT_MS,
        "wal_autocheckpoint": SQLITE_WAL_AUTOCHECKPOINT_PAGES,
        "journal_size_limit": SQLITE_JOURNAL_SIZE_LIMIT_BYTES,
    }


def test_runtime_lock_rejects_second_process_before_database_open(tmp_path: Path) -> None:
    paths = resolve_sqlite_runtime_paths(tmp_path)
    parent_ready = multiprocessing.Event()
    release_parent = multiprocessing.Event()
    process = multiprocessing.Process(
        target=_hold_runtime_lock,
        args=(str(paths.lock_path), parent_ready, release_parent),
    )
    process.start()
    try:
        assert parent_ready.wait(timeout=5)
        with pytest.raises(SQLiteRuntimeLockUnavailable):
            SQLiteRuntimeLock(paths.lock_path).acquire()
        assert not paths.default_database_path.exists()
    finally:
        release_parent.set()
        process.join(timeout=5)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
    assert process.exitcode == 0


def test_backup_api_includes_committed_wal_and_integrity_check(tmp_path: Path) -> None:
    source = tmp_path / "source #1.sqlite3"
    backup = tmp_path / "backups" / "source.sqlite3"
    connection = sqlite3.connect(source)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO parent VALUES (1)")
        connection.commit()
        backup_sqlite_database(source, backup)
    finally:
        connection.close()

    copied = sqlite3.connect(backup)
    try:
        assert copied.execute("SELECT id FROM parent").fetchall() == [(1,)]
    finally:
        copied.close()
    assert check_sqlite_integrity(backup).quick_check == ("ok",)


def test_integrity_check_rejects_foreign_key_violations(tmp_path: Path) -> None:
    database = tmp_path / "broken.sqlite3"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            PRAGMA foreign_keys=OFF;
            CREATE TABLE parent (id INTEGER PRIMARY KEY);
            CREATE TABLE child (
                id INTEGER PRIMARY KEY,
                parent_id INTEGER REFERENCES parent(id)
            );
            INSERT INTO child VALUES (1, 99);
            """
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(SQLiteIntegrityError, match="foreign key check failed"):
        check_sqlite_integrity(database)


def test_manifest_rejects_database_path_traversal(tmp_path: Path) -> None:
    paths = resolve_sqlite_runtime_paths(tmp_path)
    paths.manifest_path.write_text(
        json.dumps({"manifest_version": 1, "active_database": "../outside.sqlite3"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid database name"):
        paths.active_database_path()


def test_fresh_candidate_migration_reaches_head_and_switches_manifest(tmp_path: Path) -> None:
    paths = resolve_sqlite_runtime_paths(tmp_path)
    candidate = migrate_sqlite_candidate(paths, alembic_ini=ALEMBIC_INI)

    assert candidate.name == "harness.sqlite3"
    assert paths.active_database_path() == candidate
    assert paths.previous_database_path() is None
    assert check_sqlite_integrity(candidate).quick_check == ("ok",)
    connection = sqlite3.connect(candidate)
    try:
        assert connection.execute("SELECT count(*) FROM alembic_version").fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM sqlite_master WHERE type = 'table' AND name = 'agent_runs'"
        ).fetchone() == (1,)
    finally:
        connection.close()

    engine = create_database_engine(paths.database_url(candidate))
    try:
        with Session(engine) as session:
            agent = Agent(
                id="sqlite-agent",
                name="SQLite Agent",
                description="migration CRUD probe",
                role="executor",
                system_prompt="Run the migration probe.",
            )
            task = Task(
                id="sqlite-task",
                agent_id=agent.id,
                title="SQLite task",
                goal="Prove migrated CRUD",
                model_provider="test",
                model_name="test-model",
            )
            run = AgentRun(
                id="sqlite-run",
                task_id=task.id,
                agent_type="executor",
                status="COMPLETED",
            )
            event = AgentEvent(
                id="sqlite-event",
                task_id=task.id,
                agent_run_id=run.id,
                sequence=1,
                event_type="migration.probed",
            )
            team = Team(id="sqlite-team", name="SQLite Team")
            for record in (agent, task, run, event, team):
                session.add(record)
                session.flush()
            session.commit()
            assert session.scalar(select(func.count()).select_from(AgentEvent)) == 1
            for record in (event, run, task, team, agent):
                session.delete(record)
                session.flush()
            session.commit()
            assert session.scalar(select(func.count()).select_from(AgentEvent)) == 0
    finally:
        engine.dispose()


def test_fresh_template_install_reaches_head_without_application_rows(tmp_path: Path) -> None:
    template = tmp_path / "runtime-template.sqlite3"
    create_fresh_sqlite_candidate(template, alembic_ini=ALEMBIC_INI)
    paths = resolve_sqlite_runtime_paths(tmp_path / "Electron User Data")

    installed = install_fresh_sqlite_template(
        paths,
        template_path=template,
        alembic_ini=ALEMBIC_INI,
    )

    assert installed == paths.default_database_path
    assert paths.active_database_path() == installed
    assert check_sqlite_integrity(installed).quick_check == ("ok",)
    connection = sqlite3.connect(installed)
    try:
        assert connection.execute("SELECT count(*) FROM alembic_version").fetchone() == (1,)
        assert connection.execute("SELECT count(*) FROM users").fetchone() == (0,)
        assert connection.execute("SELECT count(*) FROM organizations").fetchone() == (0,)
        assert connection.execute("SELECT count(*) FROM tasks").fetchone() == (0,)
    finally:
        connection.close()


def test_invalid_template_falls_back_to_canonical_migration(tmp_path: Path) -> None:
    template = tmp_path / "runtime-template.sqlite3"
    template.write_bytes(b"not sqlite")
    paths = resolve_sqlite_runtime_paths(tmp_path / "Electron User Data")

    assert install_fresh_sqlite_template(
        paths,
        template_path=template,
        alembic_ini=ALEMBIC_INI,
    ) is None
    assert not paths.default_database_path.exists()

    migrated = migrate_sqlite_candidate(paths, alembic_ini=ALEMBIC_INI)
    assert migrated == paths.default_database_path
    assert check_sqlite_integrity(migrated).quick_check == ("ok",)


def test_existing_runtime_database_bypasses_template_install(tmp_path: Path) -> None:
    paths = resolve_sqlite_runtime_paths(tmp_path / "Electron User Data")
    active = migrate_sqlite_candidate(paths, alembic_ini=ALEMBIC_INI)
    template = tmp_path / "runtime-template.sqlite3"
    create_fresh_sqlite_candidate(template, alembic_ini=ALEMBIC_INI)

    assert install_fresh_sqlite_template(
        paths,
        template_path=template,
        alembic_ini=ALEMBIC_INI,
    ) is None
    assert paths.active_database_path() == active


def test_restart_reuses_current_head_and_prunes_unreferenced_candidates(tmp_path: Path) -> None:
    paths = resolve_sqlite_runtime_paths(tmp_path)
    active = migrate_sqlite_candidate(paths, alembic_ini=ALEMBIC_INI)
    obsolete = paths.runtime_dir / "harness-candidate-obsolete.sqlite3"
    obsolete.write_bytes(b"obsolete")
    Path(f"{obsolete}-wal").write_bytes(b"obsolete-wal")

    restarted = migrate_sqlite_candidate(paths, alembic_ini=ALEMBIC_INI)

    assert restarted == active
    assert paths.active_database_path() == active
    assert paths.previous_database_path() is None
    assert not obsolete.exists()
    assert not Path(f"{obsolete}-wal").exists()
    assert list(paths.runtime_dir.glob("harness-candidate-*.sqlite3")) == []


def test_candidate_migration_preserves_caller_owned_lifetime_lock(tmp_path: Path) -> None:
    paths = resolve_sqlite_runtime_paths(tmp_path)
    runtime_lock = SQLiteRuntimeLock(paths.lock_path).acquire()
    try:
        candidate = migrate_sqlite_candidate(
            paths,
            alembic_ini=ALEMBIC_INI,
            runtime_lock=runtime_lock,
        )
        assert candidate == paths.active_database_path()
        assert runtime_lock.acquired
        with pytest.raises(SQLiteRuntimeLockUnavailable):
            SQLiteRuntimeLock(paths.lock_path).acquire()
    finally:
        runtime_lock.release()

    with SQLiteRuntimeLock(paths.lock_path):
        pass


def test_candidate_migration_rejects_unacquired_or_wrong_runtime_lock(tmp_path: Path) -> None:
    paths = resolve_sqlite_runtime_paths(tmp_path / "one")
    other_paths = resolve_sqlite_runtime_paths(tmp_path / "two")
    unacquired_lock = SQLiteRuntimeLock(paths.lock_path)
    with pytest.raises(RuntimeError, match="not acquired"):
        migrate_sqlite_candidate(
            paths,
            alembic_ini=ALEMBIC_INI,
            runtime_lock=unacquired_lock,
        )

    with SQLiteRuntimeLock(other_paths.lock_path) as wrong_lock:
        with pytest.raises(ValueError, match="different runtime"):
            migrate_sqlite_candidate(
                paths,
                alembic_ini=ALEMBIC_INI,
                runtime_lock=wrong_lock,
            )


def test_revision_boundary_failure_does_not_select_partial_candidate(tmp_path: Path) -> None:
    paths = resolve_sqlite_runtime_paths(tmp_path)
    fault_point = "after_migration:20260615_0001"

    with pytest.raises(RuntimeError, match=fault_point):
        migrate_sqlite_candidate(
            paths,
            alembic_ini=ALEMBIC_INI,
            fault_injector=lambda point: _raise_at(point, fault_point),
        )

    assert not paths.default_database_path.exists()
    assert paths.active_database_path() == paths.default_database_path
    assert not paths.manifest_path.exists()


def test_clean_install_failure_after_switch_returns_to_retryable_empty_state(
    tmp_path: Path,
) -> None:
    paths = resolve_sqlite_runtime_paths(tmp_path)
    fault_point = "after_pointer_switch"

    with pytest.raises(RuntimeError, match=fault_point):
        migrate_sqlite_candidate(
            paths,
            alembic_ini=ALEMBIC_INI,
            fault_injector=lambda point: _raise_at(point, fault_point),
        )

    assert not paths.default_database_path.exists()
    assert not paths.manifest_path.exists()


@pytest.mark.parametrize("fault_point", ["after_backup", "after_candidate_integrity"])
def test_candidate_failure_before_switch_keeps_source_active(
    tmp_path: Path,
    fault_point: str,
) -> None:
    paths = resolve_sqlite_runtime_paths(tmp_path)
    source = migrate_sqlite_candidate(paths, alembic_ini=ALEMBIC_INI)

    with pytest.raises(RuntimeError, match=fault_point):
        migrate_sqlite_candidate(
            paths,
            alembic_ini=ALEMBIC_INI,
            fault_injector=lambda point: _raise_at(point, fault_point),
        )

    assert paths.active_database_path() == source
    assert check_sqlite_integrity(source).quick_check == ("ok",)


@pytest.mark.parametrize("fault_point", ["after_pointer_switch", "before_serve"])
def test_candidate_failure_after_switch_restores_previous_pointer(
    tmp_path: Path,
    fault_point: str,
) -> None:
    paths = resolve_sqlite_runtime_paths(tmp_path)
    source = migrate_sqlite_candidate(paths, alembic_ini=ALEMBIC_INI)
    original_manifest = paths.read_manifest()

    with pytest.raises(RuntimeError, match=fault_point):
        migrate_sqlite_candidate(
            paths,
            alembic_ini=ALEMBIC_INI,
            fault_injector=lambda point: _raise_at(point, fault_point),
        )

    assert paths.read_manifest() == original_manifest
    assert paths.active_database_path() == source
    assert check_sqlite_integrity(source).quick_check == ("ok",)


def _hold_runtime_lock(
    lock_path: str,
    ready: multiprocessing.Event,
    release: multiprocessing.Event,
) -> None:
    with SQLiteRuntimeLock(lock_path):
        ready.set()
        release.wait(timeout=10)


def _raise_at(point: str, target: str) -> None:
    if point == target:
        raise RuntimeError(target)
