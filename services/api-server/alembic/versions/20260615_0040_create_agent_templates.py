"""create agent_templates table

Revision ID: 20260615_0040
Revises: 20260614_0039
Create Date: 2026-06-15 00:00:00.000000
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "20260615_0040"
down_revision = "20260614_0039"
branch_labels = None
depends_on = None


def utc_now() -> datetime:
    return datetime.now(UTC)


def upgrade() -> None:
    # Create agent_templates table
    op.create_table(
        "agent_templates",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("icon", sa.String(length=32), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_templates_is_active",
        "agent_templates",
        ["is_active"],
    )

    # Seed 5 default templates
    now = utc_now()
    templates = [
        {
            "id": "code-assistant",
            "name": "Code Assistant",
            "description": "A specialized agent for software development, code review, debugging, and technical problem-solving. Ideal for engineers working on coding projects.",
            "icon": "💻",
            "tags": ["coding", "development", "debugging", "technical"],
            "config": {
                "system_prompt": "You are an expert software engineer and coding assistant. Help users write clean, efficient, and well-documented code. Provide debugging support, code reviews, and technical guidance. Follow best practices and industry standards.",
                "suggested_tools": ["code_execution", "web_search", "file_operations"],
                "default_model": "claude-sonnet-4",
                "parameters": {"temperature": 0.3},
            },
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": "research-assistant",
            "name": "Research Assistant",
            "description": "An agent optimized for information gathering, research, fact-checking, and synthesizing knowledge from multiple sources.",
            "icon": "🔍",
            "tags": ["research", "information", "analysis", "investigation"],
            "config": {
                "system_prompt": "You are a thorough research assistant. Help users find accurate information, verify facts, synthesize knowledge from multiple sources, and provide well-cited summaries. Be objective and comprehensive in your research.",
                "suggested_tools": ["web_search", "web_fetch", "document_analysis"],
                "default_model": "claude-sonnet-4",
                "parameters": {"temperature": 0.5},
            },
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": "data-analyst",
            "name": "Data Analyst",
            "description": "Specialized in data analysis, visualization, statistical analysis, and extracting insights from datasets. Perfect for data-driven decision making.",
            "icon": "📊",
            "tags": ["data", "analytics", "statistics", "visualization"],
            "config": {
                "system_prompt": "You are an expert data analyst. Help users analyze datasets, perform statistical analysis, create visualizations, and extract actionable insights. Explain your methodology clearly and provide data-driven recommendations.",
                "suggested_tools": ["code_execution", "file_operations", "data_processing"],
                "default_model": "claude-sonnet-4",
                "parameters": {"temperature": 0.4},
            },
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": "devops-helper",
            "name": "DevOps Helper",
            "description": "Assists with infrastructure management, deployment automation, CI/CD pipelines, monitoring, and operational tasks.",
            "icon": "🚀",
            "tags": ["devops", "infrastructure", "deployment", "automation"],
            "config": {
                "system_prompt": "You are a DevOps and infrastructure expert. Help users with deployment automation, CI/CD pipelines, infrastructure as code, monitoring, and operational best practices. Focus on reliability, security, and scalability.",
                "suggested_tools": ["code_execution", "web_search", "file_operations", "shell_commands"],
                "default_model": "claude-sonnet-4",
                "parameters": {"temperature": 0.3},
            },
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": "general-assistant",
            "name": "General Assistant",
            "description": "A versatile all-purpose agent that can handle a wide variety of tasks. Great starting point for users who need flexible assistance.",
            "icon": "🤖",
            "tags": ["general", "versatile", "all-purpose"],
            "config": {
                "system_prompt": "You are a helpful and versatile AI assistant. Help users with a wide range of tasks including writing, research, problem-solving, brainstorming, and general assistance. Adapt your approach based on the user's needs.",
                "suggested_tools": ["web_search", "code_execution", "file_operations"],
                "default_model": "claude-sonnet-4",
                "parameters": {"temperature": 0.7},
            },
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
    ]

    op.bulk_insert(
        sa.table(
            "agent_templates",
            sa.column("id", sa.String),
            sa.column("name", sa.String),
            sa.column("description", sa.Text),
            sa.column("icon", sa.String),
            sa.column("tags", sa.JSON),
            sa.column("config", sa.JSON),
            sa.column("is_active", sa.Boolean),
            sa.column("created_at", sa.DateTime),
            sa.column("updated_at", sa.DateTime),
        ),
        templates,
    )


def downgrade() -> None:
    op.drop_index("ix_agent_templates_is_active", table_name="agent_templates")
    op.drop_table("agent_templates")
