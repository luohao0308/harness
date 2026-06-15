"""create saml replay prevention tables

Revision ID: 20260615_0041
Revises: 20260615_0040
Create Date: 2026-06-15 02:00:00.000000

Story 6.3 - SAML Replay Attack Prevention
CRITICAL SECURITY: OWASP A04:2021 - Security Misconfiguration

Creates tables for tracking SAML assertion usage and AuthnRequest IDs
to prevent replay attacks.

Tables:
- saml_assertion_usage: Tracks used assertion IDs (prevent reuse)
- saml_authn_requests: Tracks issued AuthnRequest IDs (InResponseTo validation)

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260615_0041'
down_revision = '20260615_0040'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create saml_assertion_usage table
    op.create_table(
        'saml_assertion_usage',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('assertion_id', sa.String(length=255), nullable=False),
        sa.Column('provider_id', sa.String(length=36), nullable=False),
        sa.Column('subject_id', sa.Text(), nullable=False),
        sa.Column('session_id', sa.String(length=36), nullable=True),
        sa.Column('authn_request_id', sa.String(length=255), nullable=True),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('assertion_id', name='saml_assertion_usage_assertion_uidx'),
    )

    # Indexes for saml_assertion_usage
    op.create_index(
        'ix_saml_assertion_usage_assertion_id',
        'saml_assertion_usage',
        ['assertion_id'],
        unique=True
    )
    op.create_index(
        'ix_saml_assertion_usage_provider',
        'saml_assertion_usage',
        ['provider_id']
    )
    op.create_index(
        'ix_saml_assertion_usage_expires',
        'saml_assertion_usage',
        ['expires_at']
    )
    op.create_index(
        'ix_saml_assertion_usage_created',
        'saml_assertion_usage',
        ['used_at']
    )

    # Create saml_authn_requests table
    op.create_table(
        'saml_authn_requests',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('request_id', sa.String(length=255), nullable=False),
        sa.Column('provider_id', sa.String(length=36), nullable=False),
        sa.Column('session_id', sa.String(length=64), nullable=False),
        sa.Column('relay_state', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('request_id', name='saml_authn_requests_request_uidx'),
    )

    # Indexes for saml_authn_requests
    op.create_index(
        'ix_saml_authn_requests_request_id',
        'saml_authn_requests',
        ['request_id'],
        unique=True
    )
    op.create_index(
        'ix_saml_authn_requests_provider',
        'saml_authn_requests',
        ['provider_id']
    )
    op.create_index(
        'ix_saml_authn_requests_session',
        'saml_authn_requests',
        ['session_id']
    )
    op.create_index(
        'ix_saml_authn_requests_expires',
        'saml_authn_requests',
        ['expires_at']
    )


def downgrade() -> None:
    # Drop saml_authn_requests indexes
    op.drop_index('ix_saml_authn_requests_expires', table_name='saml_authn_requests')
    op.drop_index('ix_saml_authn_requests_session', table_name='saml_authn_requests')
    op.drop_index('ix_saml_authn_requests_provider', table_name='saml_authn_requests')
    op.drop_index('ix_saml_authn_requests_request_id', table_name='saml_authn_requests')

    # Drop saml_assertion_usage indexes
    op.drop_index('ix_saml_assertion_usage_created', table_name='saml_assertion_usage')
    op.drop_index('ix_saml_assertion_usage_expires', table_name='saml_assertion_usage')
    op.drop_index('ix_saml_assertion_usage_provider', table_name='saml_assertion_usage')
    op.drop_index('ix_saml_assertion_usage_assertion_id', table_name='saml_assertion_usage')

    # Drop tables
    op.drop_table('saml_authn_requests')
    op.drop_table('saml_assertion_usage')
