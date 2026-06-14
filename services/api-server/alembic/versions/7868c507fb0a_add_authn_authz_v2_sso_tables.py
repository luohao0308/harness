"""Add authn_authz_v2_sso_tables

Revision ID: 7868c507fb0a
Revises: 8aaf82dbbaa1
Create Date: 2026-06-14 15:41:29.246457
"""
from alembic import op
import sqlalchemy as sa


revision = '7868c507fb0a'
down_revision = '8aaf82dbbaa1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create saml_providers table
    op.create_table(
        'saml_providers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('entity_id', sa.String(length=512), nullable=False),
        sa.Column('sso_url', sa.String(length=512), nullable=False),
        sa.Column('x509_cert', sa.Text(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'entity_id', name='uq_saml_provider_org_entity')
    )
    op.create_index('ix_saml_providers_organization_id', 'saml_providers', ['organization_id'])
    op.create_index('ix_saml_providers_enabled', 'saml_providers', ['enabled'])

    # Create oidc_providers table
    op.create_table(
        'oidc_providers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('issuer_url', sa.String(length=512), nullable=False),
        sa.Column('client_id', sa.String(length=255), nullable=False),
        sa.Column('client_secret', sa.String(length=512), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'issuer_url', name='uq_oidc_provider_org_issuer')
    )
    op.create_index('ix_oidc_providers_organization_id', 'oidc_providers', ['organization_id'])
    op.create_index('ix_oidc_providers_enabled', 'oidc_providers', ['enabled'])

    # Create user_external_ids table
    op.create_table(
        'user_external_ids',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('provider_type', sa.String(length=50), nullable=False),
        sa.Column('provider_id', sa.Integer(), nullable=False),
        sa.Column('external_id', sa.String(length=255), nullable=False),
        sa.Column('external_email', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('provider_type', 'provider_id', 'external_id', name='uq_user_external_id')
    )
    op.create_index('ix_user_external_ids_user_id', 'user_external_ids', ['user_id'])
    op.create_index('ix_user_external_ids_provider', 'user_external_ids', ['provider_type', 'provider_id'])
    op.create_index('ix_user_external_ids_external_id', 'user_external_ids', ['external_id'])

    # Create sessions table
    op.create_table(
        'sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('session_token', sa.String(length=255), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=512), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('session_token')
    )
    op.create_index('ix_sessions_user_id', 'sessions', ['user_id'])
    op.create_index('ix_sessions_session_token', 'sessions', ['session_token'])
    op.create_index('ix_sessions_expires_at', 'sessions', ['expires_at'])

    # Create mfa_enrollments table
    op.create_table(
        'mfa_enrollments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('mfa_type', sa.String(length=50), nullable=False),
        sa.Column('secret_key', sa.String(length=255), nullable=True),
        sa.Column('phone_number', sa.String(length=50), nullable=True),
        sa.Column('verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )
    op.create_index('ix_mfa_enrollments_user_id', 'mfa_enrollments', ['user_id'])
    op.create_index('ix_mfa_enrollments_mfa_type', 'mfa_enrollments', ['mfa_type'])
    op.create_index('ix_mfa_enrollments_verified', 'mfa_enrollments', ['verified'])

    # Create scim_tokens table
    op.create_table(
        'scim_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=255), nullable=False),
        sa.Column('description', sa.String(length=512), nullable=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token')
    )
    op.create_index('ix_scim_tokens_organization_id', 'scim_tokens', ['organization_id'])
    op.create_index('ix_scim_tokens_token', 'scim_tokens', ['token'])
    op.create_index('ix_scim_tokens_enabled', 'scim_tokens', ['enabled'])


def downgrade() -> None:
    op.drop_index('ix_scim_tokens_enabled', 'scim_tokens')
    op.drop_index('ix_scim_tokens_token', 'scim_tokens')
    op.drop_index('ix_scim_tokens_organization_id', 'scim_tokens')
    op.drop_table('scim_tokens')

    op.drop_index('ix_mfa_enrollments_verified', 'mfa_enrollments')
    op.drop_index('ix_mfa_enrollments_mfa_type', 'mfa_enrollments')
    op.drop_index('ix_mfa_enrollments_user_id', 'mfa_enrollments')
    op.drop_table('mfa_enrollments')

    op.drop_index('ix_sessions_expires_at', 'sessions')
    op.drop_index('ix_sessions_session_token', 'sessions')
    op.drop_index('ix_sessions_user_id', 'sessions')
    op.drop_table('sessions')

    op.drop_index('ix_user_external_ids_external_id', 'user_external_ids')
    op.drop_index('ix_user_external_ids_provider', 'user_external_ids')
    op.drop_index('ix_user_external_ids_user_id', 'user_external_ids')
    op.drop_table('user_external_ids')

    op.drop_index('ix_oidc_providers_enabled', 'oidc_providers')
    op.drop_index('ix_oidc_providers_organization_id', 'oidc_providers')
    op.drop_table('oidc_providers')

    op.drop_index('ix_saml_providers_enabled', 'saml_providers')
    op.drop_index('ix_saml_providers_organization_id', 'saml_providers')
    op.drop_table('saml_providers')
