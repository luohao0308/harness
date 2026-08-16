"""merge onboarding and local agent migration heads

Revision ID: 9e0680b286a1
Revises: 20260614_0041, 20260615_0041, 20260615_0001
Create Date: 2026-06-15 22:23:36.841348
"""
from alembic import op
import sqlalchemy as sa


revision = '9e0680b286a1'
down_revision = ('20260614_0041', '20260615_0041', '20260615_0001')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
