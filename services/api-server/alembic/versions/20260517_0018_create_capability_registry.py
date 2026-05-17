"""create capability registry and snapshots

Revision ID: 20260517_0018
Revises: 20260517_0017
Create Date: 2026-05-17 14:30:00.000000
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision = "20260517_0018"
down_revision = "20260517_0017"
branch_labels = None
depends_on = None

CAPABILITY_SCHEMA_VERSION = 1
FROZEN_TOOL_METADATA = [
    {
        "name": "read_file",
        "description": "读取工作区文件。",
        "category": "filesystem",
        "source": "builtin",
        "risk_level": "low",
        "requires_sandbox": False,
        "network_policy": "none",
        "timeout_seconds": 10,
        "allowed_roles": ["admin", "engineer"],
        "audit_level": "standard",
        "idempotent": True,
        "input_schema": {},
        "mcp_server": None,
        "mcp_method": None,
    },
    {
        "name": "list_files",
        "description": "列出工作区文件。",
        "category": "filesystem",
        "source": "builtin",
        "risk_level": "low",
        "requires_sandbox": False,
        "network_policy": "none",
        "timeout_seconds": 10,
        "allowed_roles": ["admin", "engineer"],
        "audit_level": "standard",
        "idempotent": True,
        "input_schema": {},
        "mcp_server": None,
        "mcp_method": None,
    },
    {
        "name": "write_file",
        "description": "在任务工作区写入任务产物。",
        "category": "filesystem",
        "source": "builtin",
        "risk_level": "high",
        "requires_sandbox": True,
        "network_policy": "none",
        "timeout_seconds": 30,
        "allowed_roles": ["admin", "engineer"],
        "audit_level": "elevated",
        "idempotent": False,
        "input_schema": {},
        "mcp_server": None,
        "mcp_method": None,
    },
    {
        "name": "run_shell",
        "description": "在 Docker 沙箱内运行 Shell 命令。",
        "category": "shell",
        "source": "builtin",
        "risk_level": "high",
        "requires_sandbox": True,
        "network_policy": "none",
        "timeout_seconds": 60,
        "allowed_roles": ["admin", "engineer"],
        "audit_level": "elevated",
        "idempotent": False,
        "input_schema": {},
        "mcp_server": None,
        "mcp_method": None,
    },
    {
        "name": "run_tests",
        "description": "在 Docker 沙箱内运行测试。",
        "category": "shell",
        "source": "builtin",
        "risk_level": "high",
        "requires_sandbox": True,
        "network_policy": "none",
        "timeout_seconds": 300,
        "allowed_roles": ["admin", "engineer"],
        "audit_level": "elevated",
        "idempotent": True,
        "input_schema": {},
        "mcp_server": None,
        "mcp_method": None,
    },
    {
        "name": "network_request",
        "description": "在 Docker 沙箱内执行受控网络请求。",
        "category": "network",
        "source": "builtin",
        "risk_level": "high",
        "requires_sandbox": True,
        "network_policy": "restricted",
        "timeout_seconds": 30,
        "allowed_roles": ["admin"],
        "audit_level": "critical",
        "idempotent": False,
        "input_schema": {},
        "mcp_server": None,
        "mcp_method": None,
    },
    {
        "name": "git_command",
        "description": "在 Docker 沙箱内运行 Git 命令。",
        "category": "git",
        "source": "builtin",
        "risk_level": "high",
        "requires_sandbox": True,
        "network_policy": "restricted",
        "timeout_seconds": 120,
        "allowed_roles": ["admin", "engineer"],
        "audit_level": "elevated",
        "idempotent": False,
        "input_schema": {},
        "mcp_server": None,
        "mcp_method": None,
    },
    {
        "name": "mcp_context_search",
        "description": "通过 MCP Adapter 查询外部上下文。",
        "category": "mcp",
        "source": "mcp",
        "risk_level": "low",
        "requires_sandbox": False,
        "network_policy": "restricted",
        "timeout_seconds": 30,
        "allowed_roles": ["admin", "engineer"],
        "audit_level": "standard",
        "idempotent": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
        "mcp_server": "local-context",
        "mcp_method": "context.search",
    },
    {
        "name": "mcp_artifact_put",
        "description": "通过 MCP Adapter 写入任务 Artifact 记录。",
        "category": "mcp",
        "source": "mcp",
        "risk_level": "medium",
        "requires_sandbox": False,
        "network_policy": "none",
        "timeout_seconds": 30,
        "allowed_roles": ["admin", "engineer"],
        "audit_level": "elevated",
        "idempotent": False,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["name", "content"],
        },
        "mcp_server": "local-artifacts",
        "mcp_method": "artifact.put",
    },
]


def _stable_json_sha256(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _tool_capability_type(source: str) -> str:
    return "mcp_tool" if source == "mcp" else "builtin_tool"


def upgrade() -> None:
    op.create_table(
        "capabilities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("capability_key", sa.String(length=128), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_version_id", sa.String(length=64), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "capability_key", name="capabilities_org_key_uidx"),
    )
    op.create_index("ix_capabilities_capability_key", "capabilities", ["capability_key"])
    op.create_index("ix_capabilities_current_version_id", "capabilities", ["current_version_id"])
    op.create_index("ix_capabilities_organization_id", "capabilities", ["organization_id"])
    op.create_index("ix_capabilities_status", "capabilities", ["status"])
    op.create_index("ix_capabilities_type", "capabilities", ["type"])

    op.create_table(
        "capability_versions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("capability_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("config_sha256", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["capability_id"], ["capabilities.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("capability_id", "version", name="capability_versions_version_uidx"),
    )
    op.create_index(
        "ix_capability_versions_capability_id", "capability_versions", ["capability_id"]
    )
    op.create_index(
        "ix_capability_versions_config_sha256", "capability_versions", ["config_sha256"]
    )
    op.create_index(
        "ix_capability_versions_content_sha256", "capability_versions", ["content_sha256"]
    )
    op.create_index("ix_capability_versions_status", "capability_versions", ["status"])
    op.create_index("ix_capability_versions_type", "capability_versions", ["type"])

    op.create_table(
        "agent_capability_attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("capability_id", sa.String(length=36), nullable=False),
        sa.Column("capability_version_id", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("attached_by", sa.String(length=36), nullable=True),
        sa.Column("attached_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["capability_id"], ["capabilities.id"]),
        sa.ForeignKeyConstraint(["capability_version_id"], ["capability_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "agent_id",
            "capability_version_id",
            name="agent_capability_attachments_agent_version_uidx",
        ),
    )
    op.create_index(
        "ix_agent_capability_attachments_agent_id",
        "agent_capability_attachments",
        ["agent_id"],
    )
    op.create_index(
        "ix_agent_capability_attachments_capability_id",
        "agent_capability_attachments",
        ["capability_id"],
    )
    op.create_index(
        "ix_agent_capability_attachments_capability_version_id",
        "agent_capability_attachments",
        ["capability_version_id"],
    )
    op.create_index(
        "ix_agent_capability_attachments_enabled",
        "agent_capability_attachments",
        ["enabled"],
    )
    op.create_index(
        "ix_agent_capability_attachments_organization_id",
        "agent_capability_attachments",
        ["organization_id"],
    )

    op.create_table(
        "capability_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=64), nullable=True),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("snapshot_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_capability_snapshots_agent_id", "capability_snapshots", ["agent_id"])
    op.create_index(
        "ix_capability_snapshots_organization_id", "capability_snapshots", ["organization_id"]
    )
    op.create_index(
        "ix_capability_snapshots_snapshot_sha256", "capability_snapshots", ["snapshot_sha256"]
    )
    op.create_index("ix_capability_snapshots_source", "capability_snapshots", ["source"])
    op.create_index("ix_capability_snapshots_task_id", "capability_snapshots", ["task_id"])

    op.add_column("tasks", sa.Column("agent_id", sa.String(length=64), nullable=True))
    op.add_column(
        "tasks",
        sa.Column("capability_snapshot_json", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_tasks_agent_id", "tasks", ["agent_id"])

    op.add_column(
        "agent_runs",
        sa.Column("capability_snapshot_json", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "model_calls",
        sa.Column("capability_snapshot_json", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column("tool_calls", sa.Column("capability_id", sa.String(length=36), nullable=True))
    op.add_column(
        "tool_calls", sa.Column("capability_version_id", sa.String(length=64), nullable=True)
    )
    op.add_column("tool_calls", sa.Column("capability_type", sa.String(length=32), nullable=True))
    op.add_column(
        "tool_calls", sa.Column("capability_content_sha256", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "tool_calls", sa.Column("capability_config_sha256", sa.String(length=64), nullable=True)
    )
    op.add_column("tool_calls", sa.Column("capability_schema_version", sa.Integer(), nullable=True))
    op.add_column(
        "tool_calls",
        sa.Column("capability_snapshot_json", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_tool_calls_capability_id", "tool_calls", ["capability_id"])
    op.create_index("ix_tool_calls_capability_version_id", "tool_calls", ["capability_version_id"])
    op.add_column(
        "eval_cases",
        sa.Column("capability_snapshot_json", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "eval_runs",
        sa.Column("capability_snapshot_json", sa.JSON(), nullable=False, server_default="{}"),
    )

    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.create_foreign_key("tasks_agent_id_fkey", "tasks", "agents", ["agent_id"], ["id"])
    _seed_builtin_capabilities_and_backfill_agents(bind)


def downgrade() -> None:
    op.drop_column("eval_runs", "capability_snapshot_json")
    op.drop_column("eval_cases", "capability_snapshot_json")
    op.drop_index("ix_tool_calls_capability_version_id", table_name="tool_calls")
    op.drop_index("ix_tool_calls_capability_id", table_name="tool_calls")
    op.drop_column("tool_calls", "capability_snapshot_json")
    op.drop_column("tool_calls", "capability_schema_version")
    op.drop_column("tool_calls", "capability_config_sha256")
    op.drop_column("tool_calls", "capability_content_sha256")
    op.drop_column("tool_calls", "capability_type")
    op.drop_column("tool_calls", "capability_version_id")
    op.drop_column("tool_calls", "capability_id")
    op.drop_column("model_calls", "capability_snapshot_json")
    op.drop_column("agent_runs", "capability_snapshot_json")
    op.drop_index("ix_tasks_agent_id", table_name="tasks")
    op.drop_column("tasks", "capability_snapshot_json")
    op.drop_column("tasks", "agent_id")
    op.drop_table("capability_snapshots")
    op.drop_table("agent_capability_attachments")
    op.drop_table("capability_versions")
    op.drop_table("capabilities")


def _seed_builtin_capabilities_and_backfill_agents(bind) -> None:
    now = datetime.now(UTC)
    capabilities = sa.table(
        "capabilities",
        sa.column("id", sa.String),
        sa.column("organization_id", sa.String),
        sa.column("capability_key", sa.String),
        sa.column("type", sa.String),
        sa.column("status", sa.String),
        sa.column("current_version_id", sa.String),
        sa.column("schema_version", sa.Integer),
        sa.column("created_by", sa.String),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    capability_versions = sa.table(
        "capability_versions",
        sa.column("id", sa.String),
        sa.column("capability_id", sa.String),
        sa.column("version", sa.Integer),
        sa.column("type", sa.String),
        sa.column("status", sa.String),
        sa.column("content_json", sa.JSON),
        sa.column("config_json", sa.JSON),
        sa.column("content_sha256", sa.String),
        sa.column("config_sha256", sa.String),
        sa.column("schema_version", sa.Integer),
        sa.column("created_by", sa.String),
        sa.column("created_at", sa.DateTime),
    )
    attachments = sa.table(
        "agent_capability_attachments",
        sa.column("id", sa.String),
        sa.column("organization_id", sa.String),
        sa.column("agent_id", sa.String),
        sa.column("capability_id", sa.String),
        sa.column("capability_version_id", sa.String),
        sa.column("enabled", sa.Boolean),
        sa.column("priority", sa.Integer),
        sa.column("attached_by", sa.String),
        sa.column("attached_at", sa.DateTime),
    )
    agents = sa.table(
        "agents",
        sa.column("id", sa.String),
        sa.column("organization_id", sa.String),
        sa.column("tools_json", sa.JSON),
    )

    versions_by_tool: dict[str, tuple[str, str]] = {}
    for metadata in FROZEN_TOOL_METADATA:
        content = {"tool_metadata": metadata}
        config = {"secret_ref": None, "secret_scope": None, "source": metadata["source"]}
        content_sha = _stable_json_sha256(content)
        config_sha = _stable_json_sha256(config)
        capability_id = str(uuid4())
        capability_type = _tool_capability_type(str(metadata["source"]))
        tool_name = str(metadata["name"])
        version_id = f"{tool_name}:{content_sha[:16]}:{config_sha[:8]}"
        bind.execute(
            capabilities.insert().values(
                id=capability_id,
                organization_id=None,
                capability_key=f"tool:{tool_name}",
                type=capability_type,
                status="active",
                current_version_id=version_id,
                schema_version=CAPABILITY_SCHEMA_VERSION,
                created_by="migration-20260517-0018",
                created_at=now,
                updated_at=now,
            )
        )
        bind.execute(
            capability_versions.insert().values(
                id=version_id,
                capability_id=capability_id,
                version=1,
                type=capability_type,
                status="active",
                content_json=content,
                config_json=config,
                content_sha256=content_sha,
                config_sha256=config_sha,
                schema_version=CAPABILITY_SCHEMA_VERSION,
                created_by="migration-20260517-0018",
                created_at=now,
            )
        )
        versions_by_tool[tool_name] = (capability_id, version_id)

    for agent in bind.execute(
        sa.select(agents.c.id, agents.c.organization_id, agents.c.tools_json)
    ):
        tools_json = agent.tools_json
        if isinstance(tools_json, str):
            try:
                tools_json = json.loads(tools_json)
            except json.JSONDecodeError:
                tools_json = []
        if not isinstance(tools_json, list):
            continue
        for index, tool_name in enumerate(tools_json):
            version = versions_by_tool.get(str(tool_name))
            if version is None:
                continue
            capability_id, version_id = version
            bind.execute(
                attachments.insert().values(
                    id=str(uuid4()),
                    organization_id=agent.organization_id,
                    agent_id=agent.id,
                    capability_id=capability_id,
                    capability_version_id=version_id,
                    enabled=True,
                    priority=index,
                    attached_by="migration-20260517-0018",
                    attached_at=now,
                )
            )
