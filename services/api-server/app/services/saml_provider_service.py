"""
SAML Provider Service - IdP Configuration Management.

Handles CRUD operations for SAML Identity Provider configurations.
Validates IdP metadata including entity IDs, URLs, and X.509 certificates.

Story 1.2 - IdP Configuration Management
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import SAMLProvider


class SAMLProviderService:
    """
    Service for managing SAML Identity Provider configurations.

    Provides CRUD operations and validation for IdP metadata.
    Supports multiple IdPs per organization.
    """

    def __init__(self, db_session: Session) -> None:
        """
        Initialize SAML provider service.

        Args:
            db_session: SQLAlchemy database session.
        """
        self._db = db_session

    def create_provider(
        self,
        organization_id: str,
        name: str,
        entity_id: str,
        sso_url: str,
        x509_cert: str,
        slo_url: str | None = None,
        is_active: bool = True,
    ) -> SAMLProvider:
        """
        Create a new SAML Identity Provider configuration.

        Args:
            organization_id: Organization ID this provider belongs to.
            name: Human-readable name for the provider.
            entity_id: IdP entity ID (unique identifier).
            sso_url: Single Sign-On service URL.
            x509_cert: X.509 certificate for signature verification.
            slo_url: Optional Single Logout service URL.
            is_active: Whether the provider is active (default True).

        Returns:
            Created SAMLProvider instance.

        Raises:
            ValueError: If validation fails for any field.
        """
        # Validate inputs
        self._validate_required_string(entity_id, "entity_id")
        self._validate_url(sso_url, "sso_url")
        self._validate_x509_cert(x509_cert)

        if slo_url:
            self._validate_url(slo_url, "slo_url")

        # Create provider
        provider = SAMLProvider(
            organization_id=organization_id,
            name=name,
            entity_id=entity_id,
            sso_url=sso_url,
            slo_url=slo_url,
            x509_cert=x509_cert,
            is_active=is_active,
        )

        self._db.add(provider)
        self._db.commit()
        self._db.refresh(provider)

        return provider

    def get_provider_by_id(self, provider_id: str) -> SAMLProvider | None:
        """
        Retrieve a SAML provider by ID.

        Args:
            provider_id: Provider ID to retrieve.

        Returns:
            SAMLProvider instance if found, None otherwise.
        """
        return self._db.query(SAMLProvider).filter(SAMLProvider.id == provider_id).first()

    def list_providers_by_organization(
        self,
        organization_id: str,
        active_only: bool = False,
    ) -> list[SAMLProvider]:
        """
        List all SAML providers for an organization.

        Args:
            organization_id: Organization ID to filter by.
            active_only: If True, only return active providers.

        Returns:
            List of SAMLProvider instances.
        """
        query = self._db.query(SAMLProvider).filter(
            SAMLProvider.organization_id == organization_id
        )

        if active_only:
            query = query.filter(SAMLProvider.is_active.is_(True))

        return query.order_by(SAMLProvider.created_at.desc()).all()

    def update_provider(self, provider_id: str, **updates: Any) -> SAMLProvider:
        """
        Update an existing SAML provider.

        Args:
            provider_id: Provider ID to update.
            **updates: Fields to update (name, entity_id, sso_url, slo_url, x509_cert, is_active).

        Returns:
            Updated SAMLProvider instance.

        Raises:
            ValueError: If provider not found or validation fails.
        """
        provider = self.get_provider_by_id(provider_id)
        if not provider:
            raise ValueError(f"SAML provider with ID {provider_id} not found")

        # Validate updates
        if "entity_id" in updates:
            self._validate_required_string(updates["entity_id"], "entity_id")
            provider.entity_id = updates["entity_id"]

        if "sso_url" in updates:
            self._validate_url(updates["sso_url"], "sso_url")
            provider.sso_url = updates["sso_url"]

        if "slo_url" in updates:
            if updates["slo_url"]:
                self._validate_url(updates["slo_url"], "slo_url")
            provider.slo_url = updates["slo_url"]

        if "x509_cert" in updates:
            self._validate_x509_cert(updates["x509_cert"])
            provider.x509_cert = updates["x509_cert"]

        if "name" in updates:
            provider.name = updates["name"]

        if "is_active" in updates:
            provider.is_active = updates["is_active"]

        # Update timestamp
        provider.updated_at = datetime.now(UTC)

        self._db.commit()
        self._db.refresh(provider)

        return provider

    def delete_provider(self, provider_id: str) -> bool:
        """
        Delete a SAML provider.

        Args:
            provider_id: Provider ID to delete.

        Returns:
            True if deleted, False if not found.
        """
        provider = self.get_provider_by_id(provider_id)
        if not provider:
            return False

        self._db.delete(provider)
        self._db.commit()

        return True

    def _validate_required_string(self, value: str, field_name: str) -> None:
        """
        Validate that a required string field is not empty.

        Args:
            value: String value to validate.
            field_name: Name of the field for error messages.

        Raises:
            ValueError: If value is empty or not a string.
        """
        if not value or not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} is required and cannot be empty")

    def _validate_url(self, url: str, field_name: str) -> None:
        """
        Validate that a URL is properly formatted.

        Args:
            url: URL to validate.
            field_name: Name of the field for error messages.

        Raises:
            ValueError: If URL is invalid.
        """
        if not url or not isinstance(url, str):
            raise ValueError(f"{field_name} is required")

        # Simple URL validation - must start with http:// or https://
        url_pattern = re.compile(r"^https?://[^\s]+$")
        if not url_pattern.match(url):
            raise ValueError(f"{field_name} must be a valid HTTP or HTTPS URL")

    def _validate_x509_cert(self, cert: str) -> None:
        """
        Validate X.509 certificate format.

        Args:
            cert: Certificate string to validate.

        Raises:
            ValueError: If certificate is invalid.
        """
        if not cert or not isinstance(cert, str):
            raise ValueError("x509_cert is required")

        cert_stripped = cert.strip()
        if not cert_stripped:
            raise ValueError("x509_cert cannot be empty")

        # Check for PEM format markers
        if "-----BEGIN CERTIFICATE-----" not in cert_stripped:
            raise ValueError("x509_cert must be in PEM format (BEGIN CERTIFICATE)")

        if "-----END CERTIFICATE-----" not in cert_stripped:
            raise ValueError("x509_cert must be in PEM format (END CERTIFICATE)")

        # Basic structure check - should have header, content, and footer
        lines = cert_stripped.split("\n")
        if len(lines) < 3:
            raise ValueError("x509_cert appears to be malformed")
