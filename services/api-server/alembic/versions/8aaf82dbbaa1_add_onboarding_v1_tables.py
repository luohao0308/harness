"""Add onboarding_v1_tables

Revision ID: 8aaf82dbbaa1
Revises: 20260610_0037
Create Date: 2026-06-14 15:41:07.082009
"""
from alembic import op
import sqlalchemy as sa


revision = '8aaf82dbbaa1'
down_revision = '20260610_0037'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create onboarding_state table
    op.create_table(
        'onboarding_state',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('current_step', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completed_steps', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('dismissed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id')
    )
    op.create_index('ix_onboarding_state_user_id', 'onboarding_state', ['user_id'])
    op.create_index('ix_onboarding_state_dismissed', 'onboarding_state', ['dismissed'])

    # Create onboarding_templates table
    op.create_table(
        'onboarding_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('agent_config', sa.JSON(), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=False),
        sa.Column('use_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index('ix_onboarding_templates_category', 'onboarding_templates', ['category'])
    op.create_index('ix_onboarding_templates_active', 'onboarding_templates', ['active'])


def downgrade() -> None:
    op.drop_index('ix_onboarding_templates_active', 'onboarding_templates')
    op.drop_index('ix_onboarding_templates_category', 'onboarding_templates')
    op.drop_table('onboarding_templates')

    op.drop_index('ix_onboarding_state_dismissed', 'onboarding_state')
    op.drop_index('ix_onboarding_state_user_id', 'onboarding_state')
    op.drop_table('onboarding_state')
