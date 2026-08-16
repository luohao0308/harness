"""create user_sessions table

Revision ID: 20260615_0001
Revises:
Create Date: 2026-06-15 00:00:00.000000

Story 4.1 - SSO Session Lifecycle Management
Creates user_sessions table for JWT token storage and session management.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20260615_0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create user_sessions table."""
    op.create_table(
        'user_sessions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('refresh_token_hash', sa.String(length=64), nullable=False),
        sa.Column('roles_json', sa.JSON(), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id', name='user_sessions_pkey'),
    )

    # Create indexes
    op.create_index('ix_user_sessions_user_id', 'user_sessions', ['user_id'])
    op.create_index('ix_user_sessions_user_active', 'user_sessions', ['user_id', 'revoked_at'])
    op.create_index('ix_user_sessions_token_hash', 'user_sessions', ['token_hash'])
    op.create_index('ix_user_sessions_expires', 'user_sessions', ['expires_at'])


def downgrade() -> None:
    """Drop user_sessions table."""
    op.drop_index('ix_user_sessions_expires', table_name='user_sessions')
    op.drop_index('ix_user_sessions_token_hash', table_name='user_sessions')
    op.drop_index('ix_user_sessions_user_active', table_name='user_sessions')
    op.drop_index('ix_user_sessions_user_id', table_name='user_sessions')
    op.drop_table('user_sessions')
