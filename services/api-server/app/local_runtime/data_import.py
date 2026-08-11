from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections.abc import Callable, Iterable, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import MetaData, Table, create_engine, func, inspect, select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from app.bootstrap.local_owner import LOCAL_PRINCIPAL_SETTING_KEY
from app.db.models import (
    Agent,
    Organization,
    OrganizationMember,
    SystemSetting,
    Task,
    User,
)
from app.db.sqlite_candidate_migration import create_fresh_sqlite_candidate
from app.db.sqlite_integrity import check_sqlite_integrity
from app.db.sqlite_runtime_directory import SQLiteRuntimePaths
from app.db.sqlite_runtime_lock import SQLiteRuntimeLock

FaultInjector = Callable[[str], None]
OFFLINE_REQUIRED_TABLES = {"tasks", "sync_operations"}
IMPORT_MANIFEST_VERSION = 1
MIGRATION_SEEDED_TABLES = {
    "agent_templates",
    "alert_rules",
    "capabilities",
    "capability_versions",
    "model_pricing",
    "retention_policies",
    "subagent_specialists",
}


@dataclass(frozen=True)
class TableEvidence:
    source_rows: int
    target_rows: int
    source_checksum: str
    target_checksum: str


@dataclass(frozen=True)
class ImportResult:
    mode: str
    dry_run: bool
    source_fingerprint: str
    candidate_database: str | None
    alembic_revision: str
    principal: dict[str, str]
    tables: dict[str, TableEvidence]
    secrets_requiring_reconfiguration: int
    notes: tuple[str, ...]
    manifest_version: int = IMPORT_MANIFEST_VERSION
    manifest_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["tables"] = {name: asdict(value) for name, value in self.tables.items()}
        return payload


def import_legacy_data(
    paths: SQLiteRuntimePaths,
    *,
    alembic_ini: str | Path,
    owner_user_id: str,
    organization_id: str,
    offline_sqlite: str | Path | None = None,
    postgres_url: str | None = None,
    owner_email: str = "local-owner@harness.invalid",
    owner_name: str = "Local Owner",
    dry_run: bool = False,
    fault_injector: FaultInjector | None = None,
) -> ImportResult:
    """Import legacy data into a fresh candidate and select it only after validation."""
    if offline_sqlite is None and postgres_url is None:
        raise ValueError("an offline SQLite path or PostgreSQL source URL is required")
    if postgres_url is not None and not postgres_url.startswith(("postgresql://", "postgresql+")):
        raise ValueError("PostgreSQL import requires an explicit postgresql source URL")
    for label, value in (
        ("owner_user_id", owner_user_id),
        ("organization_id", organization_id),
    ):
        if not value or len(value) > 36:
            raise ValueError(f"{label} must be a non-empty value of at most 36 characters")

    inject = fault_injector or (lambda _point: None)
    source_path = Path(offline_sqlite).expanduser().resolve() if offline_sqlite else None
    if source_path is not None and not source_path.is_file():
        raise FileNotFoundError(source_path)
    if source_path is not None:
        _validate_offline_source_path(paths, source_path)
    fingerprint = _source_fingerprint(source_path, postgres_url)
    mode = "postgresql+offline-sqlite" if source_path and postgres_url else (
        "postgresql" if postgres_url else "offline-sqlite"
    )

    with SQLiteRuntimeLock(paths.lock_path):
        repeated = _repeat_result(paths, fingerprint, dry_run=dry_run)
        if repeated is not None:
            return repeated
        active = paths.active_database_path()
        if active.exists() or paths.manifest_path.exists():
            raise RuntimeError("canonical import target is not fresh; refusing to merge or collide")

        candidate = paths.runtime_dir / f"harness-import-{uuid4().hex}.sqlite3"
        manifest_path = paths.runtime_dir / f"migration-{fingerprint[:16]}.json"
        manifest_existed = paths.manifest_path.exists()
        previous_manifest = paths.read_manifest()
        switched = False
        engine: Engine | None = None
        try:
            revision = create_fresh_sqlite_candidate(
                candidate,
                alembic_ini=alembic_ini,
                fault_injector=inject,
            )
            inject("after_candidate_schema")
            engine = create_engine(f"sqlite+pysqlite:///{candidate.as_posix()}")
            _require_empty_application_database(engine)

            notes: list[str] = []
            evidence: dict[str, TableEvidence] = {}
            secrets_count = 0
            with Session(engine) as session:
                if postgres_url:
                    pg_evidence, secrets_count, pg_notes = _import_postgresql(
                        session,
                        postgres_url=postgres_url,
                        owner_user_id=owner_user_id,
                        organization_id=organization_id,
                    )
                    evidence.update(pg_evidence)
                    notes.extend(pg_notes)
                else:
                    _create_offline_principal(
                        session,
                        owner_user_id=owner_user_id,
                        organization_id=organization_id,
                        owner_email=owner_email,
                        owner_name=owner_name,
                    )
                if source_path:
                    offline_evidence, offline_notes = _import_offline_sqlite(
                        session,
                        source_path=source_path,
                        owner_user_id=owner_user_id,
                        organization_id=organization_id,
                    )
                    evidence.update(offline_evidence)
                    notes.extend(offline_notes)
                principal = _write_and_validate_principal(
                    session,
                    owner_user_id=owner_user_id,
                    organization_id=organization_id,
                )
                _validate_import_evidence(evidence)
                session.commit()
            inject("after_import")
            check_sqlite_integrity(candidate)
            inject("after_validation")

            result = ImportResult(
                mode=mode,
                dry_run=dry_run,
                source_fingerprint=fingerprint,
                candidate_database=None if dry_run else candidate.name,
                alembic_revision=revision,
                principal=principal,
                tables=evidence,
                secrets_requiring_reconfiguration=secrets_count,
                notes=tuple(notes),
                manifest_path=None if dry_run else manifest_path.name,
            )
            if dry_run:
                return result

            _write_json_atomic(manifest_path, result.to_dict())
            inject("after_migration_manifest")
            paths.switch_active_database(
                candidate,
                previous_database=None,
                alembic_revision=revision,
            )
            switched = True
            runtime_manifest = paths.read_manifest()
            runtime_manifest.update(
                import_fingerprint=fingerprint,
                migration_manifest=manifest_path.name,
            )
            paths.write_manifest(runtime_manifest)
            inject("after_pointer_switch")
            check_sqlite_integrity(paths.active_database_path())
            return result
        except BaseException:
            if switched:
                if manifest_existed:
                    paths.write_manifest(previous_manifest)
                else:
                    paths.remove_manifest()
                switched = False
            manifest_path.unlink(missing_ok=True)
            raise
        finally:
            if engine is not None:
                engine.dispose()
            if dry_run or not switched:
                _remove_sqlite(candidate)


def _import_offline_sqlite(
    session: Session,
    *,
    source_path: Path,
    owner_user_id: str,
    organization_id: str,
) -> tuple[dict[str, TableEvidence], list[str]]:
    source = sqlite3.connect(f"{source_path.as_uri()}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    try:
        tables = {
            row[0]
            for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        missing = OFFLINE_REQUIRED_TABLES - tables
        if missing:
            raise RuntimeError(f"offline SQLite source is missing tables: {sorted(missing)!r}")
        task_rows = [dict(row) for row in source.execute("SELECT * FROM tasks ORDER BY id")]
        operation_rows = [
            dict(row)
            for row in source.execute(
                "SELECT * FROM sync_operations WHERE status != 'COMPLETED' "
                "ORDER BY created_at, id"
            )
        ]
        metadata_rows = (
            [dict(row) for row in source.execute("SELECT * FROM sync_metadata ORDER BY key")]
            if "sync_metadata" in tables
            else []
        )
    finally:
        source.close()

    referenced_agents = {row["agent_id"] for row in task_rows if row["agent_id"]}
    existing_agents = set(session.scalars(select(Agent.id).where(Agent.id.in_(referenced_agents))))
    for agent_id in sorted(referenced_agents):
        if agent_id not in existing_agents:
            session.add(
                Agent(
                    id=agent_id,
                    organization_id=organization_id,
                    name=f"Imported offline agent {agent_id}",
                    description="Placeholder retained for an imported offline task reference.",
                    role="executor",
                    system_prompt="Imported offline agent; review configuration before use.",
                )
            )
    session.flush()

    normalized_tasks: list[dict[str, Any]] = []
    for row in task_rows:
        for field, selected in (
            ("organization_id", organization_id),
            ("created_by", owner_user_id),
        ):
            if row[field] not in (None, selected):
                raise RuntimeError(f"offline task {row['id']!r} belongs to an unselected {field}")
            row[field] = selected
        row["capability_snapshot_json"] = _json_value(row["capability_snapshot_json"])
        row["enable_sandbox"] = bool(row["enable_sandbox"])
        row["enable_network"] = bool(row["enable_network"])
        for field in ("created_at", "updated_at", "completed_at"):
            row[field] = _datetime_value(row[field])
        normalized_tasks.append(
            {column.name: row[column.name] for column in Task.__table__.columns}
        )
    if normalized_tasks:
        session.execute(Task.__table__.insert(), normalized_tasks)

    operation_values: list[dict[str, Any]] = []
    for row in operation_rows:
        content = {
            **row,
            "payload_json": _json_value(row["payload_json"]),
            "dedupe_key": _checksum_rows(
                [
                    {
                        key: (
                            _json_value(row[key]) if key == "payload_json" else row[key]
                        )
                        for key in (
                            "operation_type",
                            "entity_type",
                            "entity_id",
                            "payload_json",
                            "client_timestamp",
                        )
                    }
                ]
            ),
            "requires_reconciliation": row["status"] in {"IN_PROGRESS", "FAILED"},
        }
        operation_values.append(content)
        session.add(
            SystemSetting(
                id=str(uuid5(NAMESPACE_URL, f"offline-operation:{source_path}:{row['id']}")),
                organization_id=organization_id,
                key=f"legacy.offline.operation.{row['id']}",
                value_json=content,
                updated_by=owner_user_id,
                updated_at=_datetime_value(row["created_at"]),
            )
        )
    if metadata_rows:
        session.add(
            SystemSetting(
                id=str(uuid5(NAMESPACE_URL, f"offline-metadata:{source_path}")),
                organization_id=organization_id,
                key="legacy.offline.sync_metadata",
                value_json={row["key"]: row["value"] for row in metadata_rows},
                updated_by=owner_user_id,
            )
        )
    session.flush()

    target_tasks = session.execute(select(Task.__table__).order_by(Task.id)).mappings().all()
    target_operations = [
        setting.value_json
        for setting in session.scalars(
            select(SystemSetting)
            .where(SystemSetting.key.like("legacy.offline.operation.%"))
            .order_by(SystemSetting.key)
        )
    ]
    evidence = {
        "offline.tasks": _evidence(normalized_tasks, target_tasks),
        "offline.pending_operations": _evidence(operation_values, target_operations),
    }
    notes = []
    if referenced_agents:
        notes.append(
            f"Synthesized {len(referenced_agents - existing_agents)} placeholder agent records for "
            "offline task references; agent configuration cannot be recovered from "
            "offline-sync.sqlite."
        )
    return evidence, notes


def _import_postgresql(
    session: Session,
    *,
    postgres_url: str,
    owner_user_id: str,
    organization_id: str,
) -> tuple[dict[str, TableEvidence], int, list[str]]:
    source_engine = create_engine(postgres_url, pool_pre_ping=True)
    target_engine = session.get_bind()
    source_metadata = MetaData()
    target_metadata = MetaData()
    evidence: dict[str, TableEvidence] = {}
    notes: list[str] = []
    try:
        with _postgres_consistent_snapshot(source_engine) as source:
            source_metadata.reflect(bind=source)
            target_metadata.reflect(bind=target_engine)
            _validate_postgres_principal(
                source,
                source_metadata,
                owner_user_id=owner_user_id,
                organization_id=organization_id,
            )
            source_only = sorted(
                name
                for name in source_metadata.tables
                if name not in target_metadata.tables
                and name not in {"alembic_version"}
                and _table_count(source, source_metadata.tables[name])
            )
            if source_only:
                raise RuntimeError(
                    "PostgreSQL source has populated tables with no canonical mapping: "
                    f"{source_only!r}"
                )

            for target_table in reversed(target_metadata.sorted_tables):
                if (
                    target_table.name in MIGRATION_SEEDED_TABLES
                    and target_table.name in source_metadata.tables
                ):
                    session.execute(target_table.delete())
            session.flush()

            for target_table in target_metadata.sorted_tables:
                name = target_table.name
                if name in {"alembic_version", "stored_secrets"}:
                    continue
                source_table = source_metadata.tables.get(name)
                if source_table is None:
                    continue
                rows, common = _compatible_source_rows(source, source_table, target_table)
                if rows:
                    session.execute(target_table.insert(), rows)
                session.flush()
                target_rows = session.execute(
                    select(*(target_table.c[column] for column in common))
                ).mappings().all()
                evidence[f"postgresql.{name}"] = _evidence(rows, target_rows)

            secrets_count, secret_evidence = _import_secret_markers(
                source,
                source_metadata,
                session,
                owner_user_id=owner_user_id,
            )
            session.flush()
            evidence["postgresql.stored_secrets_reconfiguration"] = secret_evidence
            return evidence, secrets_count, notes
    finally:
        source_engine.dispose()


@contextmanager
def _postgres_consistent_snapshot(engine: Engine):
    """Hold all PostgreSQL reflection and reads in one repeatable, read-only snapshot."""
    connection = engine.connect()
    transaction = connection.begin()
    try:
        connection.exec_driver_sql(
            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
        )
        yield connection
        transaction.commit()
    except BaseException:
        transaction.rollback()
        raise
    finally:
        connection.close()


def _compatible_source_rows(
    source: Connection,
    source_table: Table,
    target_table: Table,
) -> tuple[list[dict[str, Any]], list[str]]:
    source_columns = set(source_table.columns.keys())
    missing_required = [
        column.name
        for column in target_table.columns
        if column.name not in source_columns
        and not column.nullable
        and column.default is None
        and column.server_default is None
        and not column.autoincrement
    ]
    if missing_required:
        raise RuntimeError(
            f"table {target_table.name!r} cannot be imported; source lacks required columns "
            f"{missing_required!r}"
        )
    common = [column.name for column in target_table.columns if column.name in source_columns]
    statement = select(*(source_table.c[name] for name in common))
    rows = [dict(row) for row in source.execute(statement).mappings()]
    return rows, common


def _validate_postgres_principal(
    source: Connection,
    metadata: MetaData,
    *,
    owner_user_id: str,
    organization_id: str,
) -> None:
    required = {"users", "organizations", "organization_members"}
    if not required.issubset(metadata.tables):
        raise RuntimeError("PostgreSQL source lacks user/organization ownership tables")
    users = metadata.tables["users"]
    organizations = metadata.tables["organizations"]
    memberships = metadata.tables["organization_members"]
    user = source.execute(select(users).where(users.c.id == owner_user_id)).mappings().one_or_none()
    organization = source.execute(
        select(organizations).where(organizations.c.id == organization_id)
    ).mappings().one_or_none()
    membership = source.execute(
        select(memberships).where(
            memberships.c.user_id == owner_user_id,
            memberships.c.organization_id == organization_id,
        )
    ).mappings().one_or_none()
    if (
        user is None
        or user.get("status") != "active"
        or organization is None
        or organization.get("owner_user_id") != owner_user_id
        or membership is None
        or membership.get("role") != "owner"
        or membership.get("accepted_at") is None
    ):
        raise RuntimeError("selected PostgreSQL owner/org is not one active owner principal")


def _import_secret_markers(
    source: Connection,
    metadata: MetaData,
    session: Session,
    *,
    owner_user_id: str,
) -> tuple[int, TableEvidence]:
    table = metadata.tables.get("stored_secrets")
    if table is None:
        empty = _evidence([], [])
        return 0, empty
    safe_columns = [
        name
        for name in (
            "id",
            "organization_id",
            "owner_user_id",
            "scope",
            "provider",
            "purpose",
            "status",
        )
        if name in table.c
    ]
    rows = source.execute(select(*(table.c[name] for name in safe_columns))).mappings().all()
    projected = [
        {**dict(row), "requires_reconfiguration": True}
        for row in rows
    ]
    for row, value_json in zip(rows, projected, strict=True):
        session.add(
            SystemSetting(
                id=str(uuid5(NAMESPACE_URL, f"legacy-secret:{row['id']}")),
                organization_id=row.get("organization_id"),
                key=f"legacy.secret.reconfigure.{row['id']}",
                value_json=value_json,
                updated_by=owner_user_id,
            )
        )
    session.flush()
    target = [
        setting.value_json
        for setting in session.scalars(
            select(SystemSetting)
            .where(SystemSetting.key.like("legacy.secret.reconfigure.%"))
            .order_by(SystemSetting.key)
        )
    ]
    return len(rows), _evidence(projected, target)


def _create_offline_principal(
    session: Session,
    *,
    owner_user_id: str,
    organization_id: str,
    owner_email: str,
    owner_name: str,
) -> None:
    now = datetime.now(UTC)
    membership_id = str(uuid5(NAMESPACE_URL, f"local-membership:{organization_id}:{owner_user_id}"))
    session.add_all(
        [
            User(
                id=owner_user_id,
                email=owner_email,
                name=owner_name,
                password_hash="!imported-local-runtime-password-login-disabled",
                email_verified=True,
                status="active",
                created_at=now,
                updated_at=now,
            ),
            Organization(
                id=organization_id,
                name="Harness",
                slug=f"local-{organization_id[:12].lower()}",
                owner_user_id=owner_user_id,
                plan="local",
                created_at=now,
            ),
            OrganizationMember(
                id=membership_id,
                organization_id=organization_id,
                user_id=owner_user_id,
                role="owner",
                invited_at=now,
                accepted_at=now,
            ),
        ]
    )
    session.flush()


def _write_and_validate_principal(
    session: Session,
    *,
    owner_user_id: str,
    organization_id: str,
) -> dict[str, str]:
    user = session.get(User, owner_user_id)
    organization = session.get(Organization, organization_id)
    memberships = session.scalars(
        select(OrganizationMember).where(
            OrganizationMember.user_id == owner_user_id,
            OrganizationMember.organization_id == organization_id,
        )
    ).all()
    if (
        user is None
        or user.status != "active"
        or organization is None
        or organization.owner_user_id != owner_user_id
        or len(memberships) != 1
        or memberships[0].role != "owner"
        or memberships[0].accepted_at is None
    ):
        raise RuntimeError("candidate does not contain exactly one active selected local principal")
    existing = session.scalars(
        select(SystemSetting).where(SystemSetting.key == LOCAL_PRINCIPAL_SETTING_KEY)
    ).all()
    if existing:
        raise RuntimeError("candidate already contains local principal metadata")
    principal = {
        "user_id": user.id,
        "organization_id": organization.id,
        "membership_id": memberships[0].id,
    }
    session.add(
        SystemSetting(
            id=str(uuid5(NAMESPACE_URL, f"local-principal:{organization.id}:{user.id}")),
            organization_id=organization.id,
            key=LOCAL_PRINCIPAL_SETTING_KEY,
            value_json=principal,
            updated_by=user.id,
        )
    )
    session.flush()
    return principal


def _require_empty_application_database(engine: Engine) -> None:
    inspector = inspect(engine)
    with engine.connect() as connection:
        populated = {}
        for name in inspector.get_table_names():
            if name == "alembic_version" or name in MIGRATION_SEEDED_TABLES:
                continue
            table = Table(name, MetaData(), autoload_with=connection)
            populated[name] = connection.execute(
                func.count().select().select_from(table)
            ).scalar_one()
    collisions = {name: count for name, count in populated.items() if count}
    if collisions:
        raise RuntimeError(f"canonical import target is nonempty: {collisions!r}")


def _validate_offline_source_path(paths: SQLiteRuntimePaths, source_path: Path) -> None:
    runtime_dir = paths.runtime_dir.resolve()
    active = paths.active_database_path().resolve()
    if source_path == active or (active.exists() and os.path.samefile(source_path, active)):
        raise ValueError("offline SQLite source must not be the active target database")
    try:
        source_path.relative_to(runtime_dir)
    except ValueError:
        pass
    else:
        raise ValueError("offline SQLite source must not be inside the target runtime directory")
    for target in runtime_dir.glob("*.sqlite*"):
        if target.is_file() and os.path.samefile(source_path, target):
            raise ValueError("offline SQLite source aliases a target runtime database")


def _validate_import_evidence(evidence: Mapping[str, TableEvidence]) -> None:
    for table_name, table in evidence.items():
        if table.source_rows != table.target_rows:
            raise RuntimeError(
                f"row count mismatch for {table_name}: "
                f"source={table.source_rows}, target={table.target_rows}"
            )
        if table.source_checksum != table.target_checksum:
            raise RuntimeError(f"content checksum mismatch for {table_name}")


def _repeat_result(
    paths: SQLiteRuntimePaths,
    fingerprint: str,
    *,
    dry_run: bool,
) -> ImportResult | None:
    if not paths.manifest_path.exists():
        return None
    runtime_manifest = paths.read_manifest()
    if runtime_manifest.get("import_fingerprint") != fingerprint:
        return None
    report_name = runtime_manifest.get("migration_manifest")
    if not isinstance(report_name, str) or Path(report_name).name != report_name:
        raise RuntimeError("runtime import manifest reference is invalid")
    payload = json.loads((paths.runtime_dir / report_name).read_text(encoding="utf-8"))
    tables = {name: TableEvidence(**value) for name, value in payload.pop("tables").items()}
    payload["tables"] = tables
    payload["dry_run"] = dry_run
    return ImportResult(**payload)


def _source_fingerprint(source_path: Path | None, postgres_url: str | None) -> str:
    digest = hashlib.sha256()
    if source_path:
        for candidate in (source_path, Path(f"{source_path}-wal")):
            if candidate.is_file():
                with candidate.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
    if postgres_url:
        parts = urlsplit(postgres_url)
        host = parts.hostname or ""
        if parts.port is not None:
            host = f"{host}:{parts.port}"
        sanitized = urlunsplit((parts.scheme, host, parts.path, parts.query, ""))
        digest.update(sanitized.encode())
    return digest.hexdigest()


def _evidence(
    source_rows: Iterable[Mapping[str, Any]],
    target_rows: Iterable[Mapping[str, Any]],
) -> TableEvidence:
    source_values = [dict(row) for row in source_rows]
    target_values = [dict(row) for row in target_rows]
    return TableEvidence(
        source_rows=len(source_values),
        target_rows=len(target_values),
        source_checksum=_checksum_rows(source_values),
        target_checksum=_checksum_rows(target_values),
    )


def _checksum_rows(rows: Iterable[Mapping[str, Any]]) -> str:
    normalized = [_canonical_value(dict(row)) for row in rows]
    normalized.sort(key=lambda value: json.dumps(value, sort_keys=True, separators=(",", ":")))
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def _canonical_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _canonical_value(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, datetime):
        aware = value if value.tzinfo else value.replace(tzinfo=UTC)
        return aware.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, bytes):
        return {"sha256": hashlib.sha256(value).hexdigest(), "length": len(value)}
    return value


def _json_value(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _datetime_value(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _table_count(connection: Connection, table: Table) -> int:
    return int(connection.execute(select(func.count()).select_from(table)).scalar_one())


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _remove_sqlite(path: Path) -> None:
    path.unlink(missing_ok=True)
    for suffix in ("-wal", "-shm"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)
