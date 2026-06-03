"""create subagent specialists and outputs

Revision ID: 20260528_0023
Revises: 20260527_0022
Create Date: 2026-05-28 00:00:00.000000
"""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa

from alembic import op

revision = "20260528_0023"
down_revision = "20260527_0022"
branch_labels = None
depends_on = None


_SEED_NOW = datetime(2026, 5, 28, tzinfo=timezone.utc)


_SPECIALISTS: list[dict[str, object]] = [
    {
        "id": "system-specialist-code-reviewer",
        "organization_id": None,
        "slug": "code-reviewer",
        "display_name": "代码审查专家",
        "description": "Review patches, files, and implementation risks with structured findings.",
        "role": "reviewer",
        "system_prompt": (
            "You are a code-reviewer specialist. Review only the assigned scope. "
            "Return JSON matching the output schema."
        ),
        "capability_slugs_json": ["read_file", "list_files", "git_command", "run_tests"],
        "output_schema_json": {
            "type": "object",
            "required": ["issues", "summary"],
            "properties": {
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["severity", "message"],
                        "properties": {
                            "severity": {
                                "type": "string",
                                "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                            },
                            "file": {"type": "string"},
                            "line": {"type": "integer"},
                            "message": {"type": "string"},
                        },
                    },
                },
                "summary": {"type": "string"},
            },
        },
        "budget_json": {
            "max_runtime_seconds": 900,
            "max_tokens": 12000,
            "max_tool_calls": 12,
            "max_cost_usd": 0.2,
        },
        "trigger_keywords_json": ["review", "code review", "diff", "patch", "风险", "审查"],
        "visibility": "system",
        "status": "ACTIVE",
        "created_by": None,
        "created_at": _SEED_NOW,
        "updated_at": _SEED_NOW,
    },
    {
        "id": "system-specialist-researcher",
        "organization_id": None,
        "slug": "researcher",
        "display_name": "资料研究专家",
        "description": "Collect source-backed information and produce citations.",
        "role": "researcher",
        "system_prompt": (
            "You are a researcher specialist. Gather relevant evidence and cite sources. "
            "Return JSON matching the output schema."
        ),
        "capability_slugs_json": ["read_file", "list_files", "network_request"],
        "output_schema_json": {
            "type": "object",
            "required": ["citations", "answer"],
            "properties": {
                "citations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["url", "title", "snippet"],
                        "properties": {
                            "url": {"type": "string"},
                            "title": {"type": "string"},
                            "snippet": {"type": "string"},
                        },
                    },
                },
                "answer": {"type": "string"},
            },
        },
        "budget_json": {
            "max_runtime_seconds": 900,
            "max_tokens": 16000,
            "max_tool_calls": 16,
            "max_cost_usd": 0.25,
        },
        "trigger_keywords_json": ["research", "资料", "citation", "source", "引用", "调研"],
        "visibility": "system",
        "status": "ACTIVE",
        "created_by": None,
        "created_at": _SEED_NOW,
        "updated_at": _SEED_NOW,
    },
    {
        "id": "system-specialist-safety-checker",
        "organization_id": None,
        "slug": "safety-checker",
        "display_name": "安全检查专家",
        "description": "Check outputs and plans for safety, policy, and release blockers.",
        "role": "checker",
        "system_prompt": (
            "You are a safety-checker specialist. Identify policy, safety, and release risks. "
            "Return JSON matching the output schema."
        ),
        "capability_slugs_json": ["read_file", "list_files"],
        "output_schema_json": {
            "type": "object",
            "required": ["passed", "violations", "recommendations"],
            "properties": {
                "passed": {"type": "boolean"},
                "violations": {"type": "array", "items": {"type": "string"}},
                "recommendations": {"type": "array", "items": {"type": "string"}},
            },
        },
        "budget_json": {
            "max_runtime_seconds": 600,
            "max_tokens": 8000,
            "max_tool_calls": 8,
            "max_cost_usd": 0.15,
        },
        "trigger_keywords_json": ["safety", "policy", "风险", "安全", "合规", "guardrail"],
        "visibility": "system",
        "status": "ACTIVE",
        "created_by": None,
        "created_at": _SEED_NOW,
        "updated_at": _SEED_NOW,
    },
    {
        "id": "system-specialist-synthesizer",
        "organization_id": None,
        "slug": "synthesizer",
        "display_name": "综合归纳专家",
        "description": "Aggregate sub-results into concise summaries and key points.",
        "role": "synthesizer",
        "system_prompt": (
            "You are a synthesizer specialist. Merge evidence into a concise summary. "
            "Return JSON matching the output schema."
        ),
        "capability_slugs_json": ["read_file", "list_files"],
        "output_schema_json": {
            "type": "object",
            "required": ["summary", "key_points", "confidence"],
            "properties": {
                "summary": {"type": "string"},
                "key_points": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            },
        },
        "budget_json": {
            "max_runtime_seconds": 600,
            "max_tokens": 10000,
            "max_tool_calls": 6,
            "max_cost_usd": 0.15,
        },
        "trigger_keywords_json": ["synthesize", "summary", "summarize", "归纳", "汇总", "总结"],
        "visibility": "system",
        "status": "ACTIVE",
        "created_by": None,
        "created_at": _SEED_NOW,
        "updated_at": _SEED_NOW,
    },
]


def upgrade() -> None:
    specialists = op.create_table(
        "subagent_specialists",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("capability_slugs_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("output_schema_json", sa.JSON(), nullable=False),
        sa.Column("budget_json", sa.JSON(), nullable=False),
        sa.Column("trigger_keywords_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("visibility", sa.String(length=16), nullable=False, server_default="org"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ACTIVE"),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "slug",
            name="subagent_specialists_org_slug_uidx",
        ),
    )
    op.create_index(
        "ix_subagent_specialists_organization_id",
        "subagent_specialists",
        ["organization_id"],
    )
    op.create_index("ix_subagent_specialists_slug", "subagent_specialists", ["slug"])
    op.create_index(
        "ix_subagent_specialists_visibility_status",
        "subagent_specialists",
        ["visibility", "status"],
    )
    op.create_index("ix_subagent_specialists_visibility", "subagent_specialists", ["visibility"])
    op.create_index("ix_subagent_specialists_status", "subagent_specialists", ["status"])
    op.bulk_insert(specialists, _SPECIALISTS)

    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("agent_runs") as batch:
            batch.add_column(sa.Column("specialist_id", sa.String(length=36), nullable=True))
            batch.create_foreign_key(
                "fk_agent_runs_specialist_id",
                "subagent_specialists",
                ["specialist_id"],
                ["id"],
            )
            batch.create_index("ix_agent_runs_specialist_id", ["specialist_id"])
    else:
        op.add_column(
            "agent_runs",
            sa.Column("specialist_id", sa.String(length=36), nullable=True),
        )
        op.create_foreign_key(
            "fk_agent_runs_specialist_id",
            "agent_runs",
            "subagent_specialists",
            ["specialist_id"],
            ["id"],
        )
        op.create_index("ix_agent_runs_specialist_id", "agent_runs", ["specialist_id"])

    op.create_table(
        "subagent_outputs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("agent_run_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("specialist_id", sa.String(length=36), nullable=True),
        sa.Column("output_json", sa.JSON(), nullable=False),
        sa.Column("output_schema_sha256", sa.String(length=64), nullable=False),
        sa.Column("budget_consumed_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("budget_exceeded_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("written_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"]),
        sa.ForeignKeyConstraint(["specialist_id"], ["subagent_specialists.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_run_id"),
    )
    op.create_index("ix_subagent_outputs_agent_run_id", "subagent_outputs", ["agent_run_id"])
    op.create_index("ix_subagent_outputs_task_id", "subagent_outputs", ["task_id"])
    op.create_index("ix_subagent_outputs_specialist_id", "subagent_outputs", ["specialist_id"])


def downgrade() -> None:
    op.drop_index("ix_subagent_outputs_specialist_id", table_name="subagent_outputs")
    op.drop_index("ix_subagent_outputs_task_id", table_name="subagent_outputs")
    op.drop_index("ix_subagent_outputs_agent_run_id", table_name="subagent_outputs")
    op.drop_table("subagent_outputs")

    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("agent_runs") as batch:
            batch.drop_index("ix_agent_runs_specialist_id")
            batch.drop_constraint("fk_agent_runs_specialist_id", type_="foreignkey")
            batch.drop_column("specialist_id")
    else:
        op.drop_index("ix_agent_runs_specialist_id", table_name="agent_runs")
        op.drop_constraint("fk_agent_runs_specialist_id", "agent_runs", type_="foreignkey")
        op.drop_column("agent_runs", "specialist_id")

    op.drop_index("ix_subagent_specialists_status", table_name="subagent_specialists")
    op.drop_index("ix_subagent_specialists_visibility", table_name="subagent_specialists")
    op.drop_index("ix_subagent_specialists_visibility_status", table_name="subagent_specialists")
    op.drop_index("ix_subagent_specialists_slug", table_name="subagent_specialists")
    op.drop_index("ix_subagent_specialists_organization_id", table_name="subagent_specialists")
    op.drop_table("subagent_specialists")
