"""merge current migration heads

Revision ID: 20260628_0049
Revises: 20260621_0042, 20260621_0043, 20260621_0044, 20260627_0048
Create Date: 2026-06-28 00:00:00.000000
"""

from collections.abc import Sequence

revision: str = "20260628_0049"
down_revision: tuple[str, ...] = (
    "20260621_0042",
    "20260621_0043",
    "20260621_0044",
    "20260627_0048",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
