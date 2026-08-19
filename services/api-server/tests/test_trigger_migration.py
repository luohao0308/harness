from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import create_engine


def _migration_module() -> ModuleType:
    path = Path(__file__).parents[1] / "alembic" / "versions" / "20260817_0051_expand_triggers.py"
    spec = importlib.util.spec_from_file_location("trigger_migration_0051", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_trigger_migration_downgrade_guard_fails_closed_for_new_data() -> None:
    migration = _migration_module()
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE triggers ("
            "type TEXT, endpoint_path TEXT, secret_hash TEXT, name TEXT, "
            "config_json TEXT, runtime_state_json TEXT, deleted_at TEXT)"
        )
        connection.exec_driver_sql("CREATE TABLE trigger_invocations (id TEXT)")
        migration._ensure_downgrade_safe(connection)

        connection.exec_driver_sql(
            "INSERT INTO triggers VALUES ('schedule', NULL, NULL, 'schedule', '{}', '{}', NULL)"
        )
        with pytest.raises(RuntimeError, match="Cannot downgrade trigger automation"):
            migration._ensure_downgrade_safe(connection)
        connection.exec_driver_sql("DELETE FROM triggers")

        connection.exec_driver_sql(
            "INSERT INTO triggers VALUES "
            "('webhook', 'legacy-hook', 'hash', 'legacy-hook', '{}', '{}', NULL)"
        )
        migration._ensure_downgrade_safe(connection)
        connection.exec_driver_sql("INSERT INTO trigger_invocations VALUES ('inv-1')")
        with pytest.raises(RuntimeError, match="Cannot downgrade trigger automation"):
            migration._ensure_downgrade_safe(connection)


@pytest.mark.parametrize(
    ("name", "config_json", "runtime_state_json", "deleted_at"),
    [
        ("custom-name", "{}", "{}", None),
        ("legacy-hook", '{"goal":"custom"}', "{}", None),
        ("legacy-hook", "{}", '{"next_run_at":123}', None),
        ("legacy-hook", "{}", "{}", "2026-08-17T00:00:00Z"),
    ],
)
def test_trigger_migration_downgrade_guard_rejects_lossy_webhook_fields(
    name: str,
    config_json: str,
    runtime_state_json: str,
    deleted_at: str | None,
) -> None:
    migration = _migration_module()
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE triggers ("
            "type TEXT, endpoint_path TEXT, secret_hash TEXT, name TEXT, "
            "config_json TEXT, runtime_state_json TEXT, deleted_at TEXT)"
        )
        connection.exec_driver_sql("CREATE TABLE trigger_invocations (id TEXT)")
        connection.exec_driver_sql(
            "INSERT INTO triggers VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "webhook",
                "legacy-hook",
                "hash",
                name,
                config_json,
                runtime_state_json,
                deleted_at,
            ),
        )

        with pytest.raises(RuntimeError, match="Cannot downgrade trigger automation"):
            migration._ensure_downgrade_safe(connection)
