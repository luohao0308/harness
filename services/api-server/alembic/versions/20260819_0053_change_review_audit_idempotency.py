"""add database idempotency for Desktop change-review audit phases

Revision ID: 20260819_0053
Revises: 20260818_0052
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260819_0053"
down_revision: str | None = "20260818_0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "admin_audit_events_org_resource_action_uidx",
        "admin_audit_events",
        ["organization_id", "event_type", "resource_type", "resource_id", "action"],
        unique=True,
        sqlite_where=sa.text(
            "event_type = 'DESKTOP_CHANGE_REVIEW_AUDITED' "
            "AND resource_type = 'desktop_change_review'"
        ),
        postgresql_where=sa.text(
            "event_type = 'DESKTOP_CHANGE_REVIEW_AUDITED' "
            "AND resource_type = 'desktop_change_review'"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "admin_audit_events_org_resource_action_uidx",
        "admin_audit_events",
    )
