from __future__ import annotations

import importlib.util
import io
from pathlib import Path
from types import ModuleType

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from alembic import command
from app.core.config import get_settings


def _migration_module() -> ModuleType:
    path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "20260818_0052_project_knowledge_index.py"
    )
    spec = importlib.util.spec_from_file_location("project_knowledge_migration_0052", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_migration(
    database_url: str,
    revision: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    try:
        config = Config("alembic.ini")
        config.set_main_option("script_location", "alembic")
        command.upgrade(config, revision)
    finally:
        get_settings.cache_clear()


def test_project_knowledge_migration_sqlite_upgrade_downgrade_round_trip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'project-knowledge.db'}"
    _run_migration(database_url, "20260817_0051", monkeypatch)
    engine = create_engine(database_url)
    assert "project_knowledge_indexes" not in inspect(engine).get_table_names()

    _run_migration(database_url, "20260818_0052", monkeypatch)
    inspector = inspect(engine)
    assert {
        "project_knowledge_indexes",
        "project_knowledge_files",
    }.issubset(inspector.get_table_names())
    index_columns = {
        column["name"] for column in inspector.get_columns("project_knowledge_indexes")
    }
    assert "root_identity" in index_columns
    assert "root_path" not in index_columns
    assert "snapshot_cursor" in index_columns

    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    try:
        config = Config("alembic.ini")
        config.set_main_option("script_location", "alembic")
        command.downgrade(config, "20260817_0051")
    finally:
        get_settings.cache_clear()
    assert "project_knowledge_indexes" not in inspect(engine).get_table_names()

    _run_migration(database_url, "head", monkeypatch)
    assert "project_knowledge_indexes" in inspect(engine).get_table_names()
    engine.dispose()


def test_project_knowledge_migration_postgresql_upgrade_compiles() -> None:
    migration = _migration_module()
    output = io.StringIO()
    context = MigrationContext.configure(
        url="postgresql://",
        opts={"as_sql": True, "output_buffer": output},
    )
    with Operations.context(context):
        migration.upgrade()

    sql = output.getvalue()
    assert "CREATE TABLE project_knowledge_indexes" in sql
    assert "CREATE TABLE project_knowledge_files" in sql
    assert "root_identity VARCHAR(64) NOT NULL" in sql
    assert "root_path" not in sql


def test_project_knowledge_migration_downgrade_guard_requires_unbound_rows() -> None:
    migration = _migration_module()
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE project_knowledge_indexes (status TEXT)")
        connection.exec_driver_sql(
            "INSERT INTO project_knowledge_indexes (status) VALUES ('ACTIVE')"
        )
        with pytest.raises(RuntimeError, match="active bindings exist"):
            migration._ensure_downgrade_safe(connection)

        connection.exec_driver_sql("UPDATE project_knowledge_indexes SET status = 'UNBOUND'")
        migration._ensure_downgrade_safe(connection)
