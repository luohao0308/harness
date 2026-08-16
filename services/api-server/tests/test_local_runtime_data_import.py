from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import Column, MetaData, String, Table, Text, create_engine, select
from sqlalchemy.orm import Session

import app.local_runtime.data_import as data_import_module
from app.bootstrap.local_owner import resolve_local_principal
from app.db.models import SystemSetting, Task
from app.db.sqlite_runtime_directory import resolve_sqlite_runtime_paths
from app.local_runtime.data_import import _import_secret_markers, import_legacy_data

API_SERVER_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = API_SERVER_DIR / "alembic.ini"
OWNER_ID = "10000000-0000-4000-8000-000000000001"
ORGANIZATION_ID = "10000000-0000-4000-8000-000000000002"


def test_offline_import_dry_run_execute_and_repeat_are_idempotent(tmp_path: Path) -> None:
    source = _offline_database(tmp_path / "offline-sync.sqlite")
    source_before = source.read_bytes()
    paths = resolve_sqlite_runtime_paths(tmp_path / "user-data")

    dry_run = _import(paths, source, dry_run=True)

    assert dry_run.dry_run is True
    assert dry_run.tables["offline.tasks"].source_rows == 1
    assert dry_run.tables["offline.pending_operations"].source_rows == 1
    assert dry_run.tables["offline.tasks"].source_checksum == (
        dry_run.tables["offline.tasks"].target_checksum
    )
    assert dry_run.tables["offline.pending_operations"].source_checksum == (
        dry_run.tables["offline.pending_operations"].target_checksum
    )
    assert not paths.manifest_path.exists()
    assert list(paths.runtime_dir.glob("harness-import-*.sqlite3")) == []
    assert source.read_bytes() == source_before

    executed = _import(paths, source, dry_run=False)
    repeated = _import(paths, source, dry_run=False)

    assert repeated.source_fingerprint == executed.source_fingerprint
    assert repeated.tables == executed.tables
    assert source.read_bytes() == source_before
    assert paths.active_database_path().name == executed.candidate_database
    assert Path(paths.runtime_dir / str(executed.manifest_path)).is_file()

    engine = create_engine(paths.database_url())
    try:
        with Session(engine) as session:
            task = session.get(Task, "offline-task-1")
            assert task is not None
            assert task.created_at.isoformat().startswith("2026-08-01T10:00:00")
            assert task.organization_id == ORGANIZATION_ID
            operation = session.scalar(
                select(SystemSetting).where(SystemSetting.key == "legacy.offline.operation.7")
            )
            assert operation is not None
            assert operation.value_json["entity_id"] == task.id
            assert len(operation.value_json["dedupe_key"]) == 64
            user, organization, membership = resolve_local_principal(session)
            assert (user.id, organization.id, membership.role) == (
                OWNER_ID,
                ORGANIZATION_ID,
                "owner",
            )
    finally:
        engine.dispose()


def test_offline_import_refuses_nonfresh_target_and_cross_owner_data(tmp_path: Path) -> None:
    first = _offline_database(tmp_path / "first.sqlite")
    paths = resolve_sqlite_runtime_paths(tmp_path / "user-data")
    _import(paths, first, dry_run=False)

    second = _offline_database(tmp_path / "second.sqlite", created_by="different-user")
    with pytest.raises(RuntimeError, match="not fresh"):
        _import(paths, second, dry_run=False)

    other_paths = resolve_sqlite_runtime_paths(tmp_path / "other-user-data")
    with pytest.raises(RuntimeError, match="unselected created_by"):
        _import(other_paths, second, dry_run=True)
    assert not other_paths.manifest_path.exists()
    assert list(other_paths.runtime_dir.glob("harness-import-*.sqlite3")) == []


def test_failure_after_pointer_switch_rolls_back_all_target_artifacts(tmp_path: Path) -> None:
    source = _offline_database(tmp_path / "offline.sqlite")
    paths = resolve_sqlite_runtime_paths(tmp_path / "user-data")

    with pytest.raises(RuntimeError, match="after_pointer_switch"):
        import_legacy_data(
            paths,
            alembic_ini=ALEMBIC_INI,
            owner_user_id=OWNER_ID,
            organization_id=ORGANIZATION_ID,
            offline_sqlite=source,
            dry_run=False,
            fault_injector=lambda point: _raise_at(point, "after_pointer_switch"),
        )

    assert not paths.manifest_path.exists()
    assert not paths.active_database_path().exists()
    assert list(paths.runtime_dir.glob("harness-import-*.sqlite3")) == []
    assert list(paths.runtime_dir.glob("migration-*.json")) == []


def test_postgresql_secret_metadata_is_marked_without_copying_ciphertext(db_session) -> None:
    source_engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata = MetaData()
    secrets = Table(
        "stored_secrets",
        metadata,
        Column("id", String, primary_key=True),
        Column("organization_id", String, nullable=False),
        Column("owner_user_id", String),
        Column("scope", String, nullable=False),
        Column("provider", String, nullable=False),
        Column("purpose", String, nullable=False),
        Column("status", String, nullable=False),
        Column("encrypted_value", Text, nullable=False),
        Column("encryption_key_id", String, nullable=False),
    )
    metadata.create_all(source_engine)
    try:
        with source_engine.begin() as source:
            source.execute(
                secrets.insert(),
                {
                    "id": "secret-1",
                    "organization_id": ORGANIZATION_ID,
                    "owner_user_id": OWNER_ID,
                    "scope": "user",
                    "provider": "example",
                    "purpose": "model",
                    "status": "active",
                    "encrypted_value": "ciphertext-must-not-migrate",
                    "encryption_key_id": "legacy-key",
                },
            )
        with source_engine.connect() as source:
            count, evidence = _import_secret_markers(
                source,
                metadata,
                db_session,
                owner_user_id=OWNER_ID,
            )
            db_session.flush()
        marker = db_session.scalar(
            select(SystemSetting).where(SystemSetting.key == "legacy.secret.reconfigure.secret-1")
        )
        assert count == 1
        assert evidence.source_rows == evidence.target_rows == 1
        assert evidence.source_checksum == evidence.target_checksum
        assert marker is not None
        assert marker.value_json["requires_reconfiguration"] is True
        serialized = json.dumps(marker.value_json)
        assert "ciphertext-must-not-migrate" not in serialized
        assert "legacy-key" not in serialized
    finally:
        source_engine.dispose()


def test_checksum_mismatch_aborts_before_pointer_switch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _offline_database(tmp_path / "offline.sqlite")
    paths = resolve_sqlite_runtime_paths(tmp_path / "user-data")
    original_evidence = data_import_module._evidence

    def mismatched_evidence(source_rows, target_rows):
        evidence = original_evidence(source_rows, target_rows)
        return data_import_module.TableEvidence(
            source_rows=evidence.source_rows,
            target_rows=evidence.target_rows,
            source_checksum=evidence.source_checksum,
            target_checksum="0" * 64,
        )

    monkeypatch.setattr(data_import_module, "_evidence", mismatched_evidence)

    with pytest.raises(RuntimeError, match="content checksum mismatch"):
        _import(paths, source, dry_run=False)

    assert not paths.manifest_path.exists()
    assert not paths.active_database_path().exists()
    assert list(paths.runtime_dir.glob("harness-import-*.sqlite3")) == []


def test_import_rejects_active_database_as_offline_source(tmp_path: Path) -> None:
    paths = resolve_sqlite_runtime_paths(tmp_path / "user-data")
    source = _offline_database(paths.default_database_path)

    with pytest.raises(ValueError, match="active target database"):
        _import(paths, source, dry_run=True)


def test_import_rejects_any_offline_source_inside_runtime_directory(tmp_path: Path) -> None:
    paths = resolve_sqlite_runtime_paths(tmp_path / "user-data")
    source = _offline_database(paths.runtime_dir / "legacy-offline.sqlite")

    with pytest.raises(ValueError, match="inside the target runtime directory"):
        _import(paths, source, dry_run=True)


def test_import_rejects_hardlink_alias_of_active_database(tmp_path: Path) -> None:
    paths = resolve_sqlite_runtime_paths(tmp_path / "user-data")
    active = _offline_database(paths.default_database_path)
    source_alias = tmp_path / "outside-alias.sqlite"
    source_alias.hardlink_to(active)

    with pytest.raises(ValueError, match="active target database"):
        _import(paths, source_alias, dry_run=True)


def test_postgresql_snapshot_contract_is_repeatable_read_and_read_only() -> None:
    engine = _FakePostgresEngine()

    with data_import_module._postgres_consistent_snapshot(engine) as connection:
        connection.events.append("read")

    assert connection.events == [
        "connect",
        "begin",
        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY",
        "read",
        "commit",
        "close",
    ]


def _import(paths, source: Path, *, dry_run: bool):
    return import_legacy_data(
        paths,
        alembic_ini=ALEMBIC_INI,
        owner_user_id=OWNER_ID,
        organization_id=ORGANIZATION_ID,
        offline_sqlite=source,
        dry_run=dry_run,
    )


def _offline_database(path: Path, *, created_by: str | None = None) -> Path:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE tasks (
                id TEXT PRIMARY KEY, organization_id TEXT, agent_id TEXT, created_by TEXT,
                title TEXT NOT NULL, goal TEXT NOT NULL, status TEXT NOT NULL,
                model_provider TEXT NOT NULL, model_name TEXT NOT NULL,
                max_runtime_seconds INTEGER NOT NULL, max_subagents INTEGER NOT NULL,
                enable_sandbox INTEGER NOT NULL, enable_network INTEGER NOT NULL,
                capability_snapshot_json TEXT NOT NULL, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL, completed_at TEXT, sync_version INTEGER NOT NULL,
                last_synced_at TEXT, server_updated_at TEXT, is_local_only INTEGER NOT NULL,
                has_local_changes INTEGER NOT NULL, conflict_detected INTEGER NOT NULL
            );
            CREATE TABLE sync_operations (
                id INTEGER PRIMARY KEY, operation_type TEXT NOT NULL, entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL, payload_json TEXT NOT NULL,
                client_timestamp TEXT NOT NULL, retry_count INTEGER NOT NULL,
                last_retry_at TEXT, status TEXT NOT NULL, error_message TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE sync_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT);
            """
        )
        connection.execute(
            "INSERT INTO tasks VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "offline-task-1",
                None,
                "offline-agent",
                created_by,
                "Offline task",
                "Preserve this task",
                "CREATED",
                "test",
                "test-model",
                1800,
                5,
                1,
                0,
                json.dumps({"tools": ["shell"]}),
                "2026-08-01T10:00:00Z",
                "2026-08-01T10:01:00Z",
                None,
                3,
                None,
                None,
                1,
                1,
                0,
            ),
        )
        connection.execute(
            "INSERT INTO sync_operations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                7,
                "UPDATE",
                "task",
                "offline-task-1",
                json.dumps({"status": "RUNNING"}),
                "2026-08-01T10:02:00Z",
                1,
                "2026-08-01T10:03:00Z",
                "FAILED",
                "offline",
                "2026-08-01T10:02:00Z",
            ),
        )
        connection.execute(
            "INSERT INTO sync_metadata VALUES (?, ?, ?)",
            ("last_sync_timestamp", "2026-08-01T09:00:00Z", "2026-08-01T09:00:00Z"),
        )
        connection.commit()
    finally:
        connection.close()
    return path


def _raise_at(point: str, expected: str) -> None:
    if point == expected:
        raise RuntimeError(expected)


class _FakePostgresTransaction:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def commit(self) -> None:
        self.events.append("commit")

    def rollback(self) -> None:
        self.events.append("rollback")


class _FakePostgresConnection:
    def __init__(self) -> None:
        self.events = ["connect"]

    def begin(self) -> _FakePostgresTransaction:
        self.events.append("begin")
        return _FakePostgresTransaction(self.events)

    def exec_driver_sql(self, statement: str) -> None:
        self.events.append(statement)

    def close(self) -> None:
        self.events.append("close")


class _FakePostgresEngine:
    def __init__(self) -> None:
        self.connection = _FakePostgresConnection()

    def connect(self) -> _FakePostgresConnection:
        return self.connection
