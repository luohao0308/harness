"""Add observability_v2_tables

Revision ID: ac61ba5ce7d6
Revises: 7868c507fb0a
Create Date: 2026-06-14 15:42:10.479451
"""
from alembic import op
import sqlalchemy as sa


revision = 'ac61ba5ce7d6'
down_revision = '7868c507fb0a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create alert_channels table (new for v2)
    op.create_table(
        'alert_channels',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('channel_type', sa.String(length=50), nullable=False),
        sa.Column('config', sa.JSON(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_alert_channels_organization_id', 'alert_channels', ['organization_id'])
    op.create_index('ix_alert_channels_channel_type', 'alert_channels', ['channel_type'])
    op.create_index('ix_alert_channels_enabled', 'alert_channels', ['enabled'])

    # Skip alert_rules - already exists from previous migrations

    # Create span_exports table (new for v2 - OTLP export)
    op.create_table(
        'span_exports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('export_type', sa.String(length=50), nullable=False),
        sa.Column('endpoint', sa.String(length=512), nullable=False),
        sa.Column('headers', sa.JSON(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('last_export_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_span_exports_organization_id', 'span_exports', ['organization_id'])
    op.create_index('ix_span_exports_export_type', 'span_exports', ['export_type'])
    op.create_index('ix_span_exports_enabled', 'span_exports', ['enabled'])


def downgrade() -> None:
    op.drop_index('ix_span_exports_enabled', 'span_exports')
    op.drop_index('ix_span_exports_export_type', 'span_exports')
    op.drop_index('ix_span_exports_organization_id', 'span_exports')
    op.drop_table('span_exports')

    # Skip alert_rules - managed by earlier migrations

    op.drop_index('ix_alert_channels_enabled', 'alert_channels')
    op.drop_index('ix_alert_channels_channel_type', 'alert_channels')
    op.drop_index('ix_alert_channels_organization_id', 'alert_channels')
    op.drop_table('alert_channels')
