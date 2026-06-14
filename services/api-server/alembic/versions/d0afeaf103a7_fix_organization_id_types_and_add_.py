"""Fix organization_id types and add missing tables

Revision ID: d0afeaf103a7
Revises: ac61ba5ce7d6
Create Date: 2026-06-14 16:19:54.861604
"""
from alembic import op
import sqlalchemy as sa


revision = 'd0afeaf103a7'
down_revision = 'ac61ba5ce7d6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Fix 1: Change organization_id from Integer to String(36) in 5 tables
    # saml_providers
    op.alter_column('saml_providers', 'organization_id',
                    existing_type=sa.Integer(),
                    type_=sa.String(length=36),
                    existing_nullable=False)

    # oidc_providers
    op.alter_column('oidc_providers', 'organization_id',
                    existing_type=sa.Integer(),
                    type_=sa.String(length=36),
                    existing_nullable=False)

    # scim_tokens
    op.alter_column('scim_tokens', 'organization_id',
                    existing_type=sa.Integer(),
                    type_=sa.String(length=36),
                    existing_nullable=False)

    # alert_channels
    op.alter_column('alert_channels', 'organization_id',
                    existing_type=sa.Integer(),
                    type_=sa.String(length=36),
                    existing_nullable=False)

    # span_exports
    op.alter_column('span_exports', 'organization_id',
                    existing_type=sa.Integer(),
                    type_=sa.String(length=36),
                    existing_nullable=False)

    # Fix 2: Add foreign key constraints to organizations.id
    # Note: Assuming organizations table exists with String(36) id
    op.create_foreign_key('fk_saml_providers_organization', 'saml_providers',
                          'organizations', ['organization_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('fk_oidc_providers_organization', 'oidc_providers',
                          'organizations', ['organization_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('fk_scim_tokens_organization', 'scim_tokens',
                          'organizations', ['organization_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('fk_alert_channels_organization', 'alert_channels',
                          'organizations', ['organization_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('fk_span_exports_organization', 'span_exports',
                          'organizations', ['organization_id'], ['id'], ondelete='CASCADE')

    # Fix 3: Create validation_results table (Critical for Onboarding v1)
    op.create_table(
        'validation_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('onboarding_state_id', sa.Integer(), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),  # 'system', 'configuration', 'service'
        sa.Column('check_name', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),  # 'passed', 'warning', 'failed'
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('auto_fixable', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('fixed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('checked_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['onboarding_state_id'], ['onboarding_state.id'], ondelete='CASCADE')
    )
    op.create_index('ix_validation_results_onboarding_state_id', 'validation_results', ['onboarding_state_id'])
    op.create_index('ix_validation_results_status', 'validation_results', ['status'])
    op.create_index('ix_validation_results_category', 'validation_results', ['category'])

    # Fix 4: Add missing fields to existing tables
    # Add backup_codes to mfa_enrollments
    op.add_column('mfa_enrollments', sa.Column('backup_codes', sa.JSON(), nullable=True))

    # Add last_activity_at to sessions
    op.add_column('sessions', sa.Column('last_activity_at', sa.DateTime(), nullable=True))

    # Add display fields to onboarding_templates
    op.add_column('onboarding_templates', sa.Column('icon', sa.String(length=255), nullable=True))
    op.add_column('onboarding_templates', sa.Column('tags', sa.JSON(), nullable=True))
    op.add_column('onboarding_templates', sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'))

    # Fix 5: Add composite index for performance
    op.create_index('ix_user_external_ids_user_provider', 'user_external_ids',
                    ['user_id', 'provider_type'])


def downgrade() -> None:
    # Reverse Fix 5: Drop composite index
    op.drop_index('ix_user_external_ids_user_provider', 'user_external_ids')

    # Reverse Fix 4: Remove added columns
    op.drop_column('onboarding_templates', 'display_order')
    op.drop_column('onboarding_templates', 'tags')
    op.drop_column('onboarding_templates', 'icon')
    op.drop_column('sessions', 'last_activity_at')
    op.drop_column('mfa_enrollments', 'backup_codes')

    # Reverse Fix 3: Drop validation_results table
    op.drop_index('ix_validation_results_category', 'validation_results')
    op.drop_index('ix_validation_results_status', 'validation_results')
    op.drop_index('ix_validation_results_onboarding_state_id', 'validation_results')
    op.drop_table('validation_results')

    # Reverse Fix 2: Drop foreign key constraints
    op.drop_constraint('fk_span_exports_organization', 'span_exports', type_='foreignkey')
    op.drop_constraint('fk_alert_channels_organization', 'alert_channels', type_='foreignkey')
    op.drop_constraint('fk_scim_tokens_organization', 'scim_tokens', type_='foreignkey')
    op.drop_constraint('fk_oidc_providers_organization', 'oidc_providers', type_='foreignkey')
    op.drop_constraint('fk_saml_providers_organization', 'saml_providers', type_='foreignkey')

    # Reverse Fix 1: Change organization_id back to Integer
    op.alter_column('span_exports', 'organization_id',
                    existing_type=sa.String(length=36),
                    type_=sa.Integer(),
                    existing_nullable=False)
    op.alter_column('alert_channels', 'organization_id',
                    existing_type=sa.String(length=36),
                    type_=sa.Integer(),
                    existing_nullable=False)
    op.alter_column('scim_tokens', 'organization_id',
                    existing_type=sa.String(length=36),
                    type_=sa.Integer(),
                    existing_nullable=False)
    op.alter_column('oidc_providers', 'organization_id',
                    existing_type=sa.String(length=36),
                    type_=sa.Integer(),
                    existing_nullable=False)
    op.alter_column('saml_providers', 'organization_id',
                    existing_type=sa.String(length=36),
                    type_=sa.Integer(),
                    existing_nullable=False)
