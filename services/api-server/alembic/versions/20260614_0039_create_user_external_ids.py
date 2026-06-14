"""create user_external_ids table

Revision ID: 20260614_0039
Revises: 20260614_0038
Create Date: 2026-06-14 23:00:00.000000

Story 2.3 - User Provisioning from SAML
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260614_0039'
down_revision = '20260614_0038'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create user_external_ids table
    op.create_table(
        'user_external_ids',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('provider', sa.String(32), nullable=False),
        sa.Column('external_entity_id', sa.Text(), nullable=False),
        sa.Column('external_user_id', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'provider',
            'external_entity_id',
            'external_user_id',
            name='user_external_ids_provider_entity_user_uidx'
        ),
    )

    # Create indexes
    op.create_index(
        'ix_user_external_ids_user_id',
        'user_external_ids',
        ['user_id'],
    )
    op.create_index(
        'ix_user_external_ids_provider',
        'user_external_ids',
        ['provider'],
    )
    op.create_index(
        'ix_user_external_ids_user_provider',
        'user_external_ids',
        ['user_id', 'provider'],
    )
    op.create_index(
        'ix_user_external_ids_external_entity',
        'user_external_ids',
        ['external_entity_id'],
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_user_external_ids_external_entity', 'user_external_ids')
    op.drop_index('ix_user_external_ids_user_provider', 'user_external_ids')
    op.drop_index('ix_user_external_ids_provider', 'user_external_ids')
    op.drop_index('ix_user_external_ids_user_id', 'user_external_ids')

    # Drop table
    op.drop_table('user_external_ids')
