"""allow local agent multi-adapter pairing

Revision ID: 20260613_0040
Revises: 20260612_0039
Create Date: 2026-06-13 00:00:00.000000
"""

from __future__ import annotations

from alembic import op

revision = "20260613_0040"
down_revision = "20260612_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("local_agent_connections") as batch_op:
        batch_op.drop_constraint(
            "local_agent_connections_pairing_token_uidx",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "local_agent_connections_pairing_adapter_uidx",
            ["pairing_token_id", "adapter_kind"],
        )


def downgrade() -> None:
    raise RuntimeError(
        "Downgrade from local Agent multi-adapter pairing is unsafe: "
        "existing pairing tokens may legitimately have hao, codex, and "
        "claude_code connections. Archive or migrate duplicate "
        "pairing_token_id rows before manually restoring the old constraint."
    )
