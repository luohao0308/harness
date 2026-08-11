"""
Tests for SAML Provider Service - IdP Configuration Management.

Following TDD: These tests are written first, then implementation follows.
Story 1.2 - IdP Configuration Management
Acceptance Criteria:
1. Store IdP metadata (entity ID, SSO URL, certificate)
2. Support multiple IdPs per organization
3. CRUD endpoints for SAML providers
4. Validate IdP metadata on save
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session


@pytest.fixture
def sample_x509_cert() -> str:
    """Sample X.509 certificate for testing."""
    return """-----BEGIN CERTIFICATE-----
MIIDXTCCAkWgAwIBAgIJAKL0UG+mRKSzMA0GCSqGSIb3DQEBCwUAMEUxCzAJBgNV
BAYTAkFVMRMwEQYDVQQIDApTb21lLVN0YXRlMSEwHwYDVQQKDBhJbnRlcm5ldCBX
aWRnaXRzIFB0eSBMdGQwHhcNMTYwODI3MjEwNTEyWhcNMTcwODI3MjEwNTEyWjBF
MQswCQYDVQQGEwJBVTETMBEGA1UECAwKU29tZS1TdGF0ZTEhMB8GA1UECgwYSW50
ZXJuZXQgV2lkZ2l0cyBQdHkgTHRkMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIB
CgKCAQEAx7nFRzHJKKvYwZKEzCrMPMPDzMpyLSLxvyELPYaYRnlLVxCGJCxMxJRb
-----END CERTIFICATE-----"""


@pytest.fixture
def sample_idp_metadata() -> dict:
    """Sample IdP metadata for testing."""
    return {
        "organization_id": "org-123",
        "name": "Okta SSO",
        "entity_id": "http://www.okta.com/exk123",
        "sso_url": "https://example.okta.com/app/example_saml/exk123/sso/saml",
        "slo_url": "https://example.okta.com/app/example_saml/exk123/slo/saml",
        "x509_cert": """-----BEGIN CERTIFICATE-----
MIIDXTCCAkWgAwIBAgIJAKL0UG+mRKSzMA0GCSqGSIb3DQEBCwUAMEUxCzAJBgNV
BAYTAkFVMRMwEQYDVQQIDApTb21lLVN0YXRlMSEwHwYDVQQKDBhJbnRlcm5ldCBX
aWRnaXRzIFB0eSBMdGQwHhcNMTYwODI3MjEwNTEyWhcNMTcwODI3MjEwNTEyWjBF
-----END CERTIFICATE-----""",
    }


class TestSAMLProviderServiceCreate:
    """Test SAML provider creation."""

    def test_create_provider_success(self, db_session: Session, sample_idp_metadata: dict):
        """Test successful creation of SAML provider."""
        from app.services.saml_provider_service import SAMLProviderService

        service = SAMLProviderService(db_session)
        provider = service.create_provider(**sample_idp_metadata)

        assert provider.id is not None
        assert provider.organization_id == sample_idp_metadata["organization_id"]
        assert provider.name == sample_idp_metadata["name"]
        assert provider.entity_id == sample_idp_metadata["entity_id"]
        assert provider.sso_url == sample_idp_metadata["sso_url"]
        assert provider.slo_url == sample_idp_metadata["slo_url"]
        assert provider.x509_cert == sample_idp_metadata["x509_cert"]
        assert provider.is_active is True
        assert provider.created_at is not None
        assert provider.updated_at is not None

    def test_create_provider_without_slo_url(self, db_session: Session, sample_idp_metadata: dict):
        """Test creating provider without optional SLO URL."""
        from app.services.saml_provider_service import SAMLProviderService

        service = SAMLProviderService(db_session)
        metadata = {**sample_idp_metadata, "slo_url": None}
        provider = service.create_provider(**metadata)

        assert provider.slo_url is None
        assert provider.is_active is True

    def test_create_provider_validates_entity_id(
        self, db_session: Session, sample_idp_metadata: dict
    ):
        """Test that entity ID is validated."""
        from app.services.saml_provider_service import SAMLProviderService

        service = SAMLProviderService(db_session)
        metadata = {**sample_idp_metadata, "entity_id": ""}

        with pytest.raises(ValueError, match="entity_id"):
            service.create_provider(**metadata)

    def test_create_provider_validates_sso_url(
        self, db_session: Session, sample_idp_metadata: dict
    ):
        """Test that SSO URL is validated."""
        from app.services.saml_provider_service import SAMLProviderService

        service = SAMLProviderService(db_session)
        metadata = {**sample_idp_metadata, "sso_url": "not-a-url"}

        with pytest.raises(ValueError, match="sso_url"):
            service.create_provider(**metadata)

    def test_create_provider_validates_x509_cert(
        self, db_session: Session, sample_idp_metadata: dict
    ):
        """Test that X.509 certificate is validated."""
        from app.services.saml_provider_service import SAMLProviderService

        service = SAMLProviderService(db_session)
        metadata = {**sample_idp_metadata, "x509_cert": "invalid cert"}

        with pytest.raises(ValueError, match="x509_cert"):
            service.create_provider(**metadata)


class TestSAMLProviderServiceRead:
    """Test SAML provider retrieval."""

    def test_get_provider_by_id(self, db_session: Session, sample_idp_metadata: dict):
        """Test retrieving provider by ID."""
        from app.services.saml_provider_service import SAMLProviderService

        service = SAMLProviderService(db_session)
        created = service.create_provider(**sample_idp_metadata)

        retrieved = service.get_provider_by_id(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.name == created.name

    def test_get_provider_by_id_not_found(self, db_session: Session):
        """Test retrieving non-existent provider returns None."""
        from app.services.saml_provider_service import SAMLProviderService

        service = SAMLProviderService(db_session)
        provider = service.get_provider_by_id("non-existent-id")

        assert provider is None

    def test_list_providers_by_organization(self, db_session: Session, sample_idp_metadata: dict):
        """Test listing all providers for an organization."""
        from app.services.saml_provider_service import SAMLProviderService

        service = SAMLProviderService(db_session)

        # Create multiple providers
        service.create_provider(**sample_idp_metadata)
        service.create_provider(**{**sample_idp_metadata, "name": "Azure AD SSO"})

        providers = service.list_providers_by_organization("org-123")
        assert len(providers) == 2

    def test_list_providers_empty_organization(self, db_session: Session):
        """Test listing providers for organization with no providers."""
        from app.services.saml_provider_service import SAMLProviderService

        service = SAMLProviderService(db_session)
        providers = service.list_providers_by_organization("org-empty")

        assert len(providers) == 0
        assert providers == []


class TestSAMLProviderServiceUpdate:
    """Test SAML provider updates."""

    def test_update_provider_success(self, db_session: Session, sample_idp_metadata: dict):
        """Test successful update of SAML provider."""
        from app.services.saml_provider_service import SAMLProviderService

        service = SAMLProviderService(db_session)
        created = service.create_provider(**sample_idp_metadata)
        original_updated_at = created.updated_at

        updates = {
            "name": "Updated SSO Name",
            "sso_url": "https://updated.example.com/sso",
        }
        updated = service.update_provider(created.id, **updates)

        assert updated.id == created.id
        assert updated.name == "Updated SSO Name"
        assert updated.sso_url == "https://updated.example.com/sso"
        assert updated.entity_id == created.entity_id  # Unchanged
        assert updated.updated_at >= original_updated_at

    def test_update_provider_not_found(self, db_session: Session):
        """Test updating non-existent provider raises error."""
        from app.services.saml_provider_service import SAMLProviderService

        service = SAMLProviderService(db_session)

        with pytest.raises(ValueError, match="not found"):
            service.update_provider("non-existent-id", name="New Name")

    def test_update_provider_validates_urls(self, db_session: Session, sample_idp_metadata: dict):
        """Test that URL validation applies to updates."""
        from app.services.saml_provider_service import SAMLProviderService

        service = SAMLProviderService(db_session)
        created = service.create_provider(**sample_idp_metadata)

        with pytest.raises(ValueError, match="sso_url"):
            service.update_provider(created.id, sso_url="not-a-url")


class TestSAMLProviderServiceDelete:
    """Test SAML provider deletion."""

    def test_delete_provider_success(self, db_session: Session, sample_idp_metadata: dict):
        """Test successful deletion of SAML provider."""
        from app.services.saml_provider_service import SAMLProviderService

        service = SAMLProviderService(db_session)
        created = service.create_provider(**sample_idp_metadata)

        result = service.delete_provider(created.id)
        assert result is True

        # Verify it's deleted
        deleted = service.get_provider_by_id(created.id)
        assert deleted is None

    def test_delete_provider_not_found(self, db_session: Session):
        """Test deleting non-existent provider returns False."""
        from app.services.saml_provider_service import SAMLProviderService

        service = SAMLProviderService(db_session)
        result = service.delete_provider("non-existent-id")

        assert result is False


class TestSAMLProviderServiceGetByEntityId:
    """Test SAML provider retrieval by entity ID - critical for IdP-initiated SSO."""

    def test_get_provider_by_entity_id_success(
        self,
        db_session: Session,
        sample_idp_metadata: dict,
    ):
        """Test retrieving provider by valid entity ID returns correct provider."""
        from app.services.saml_provider_service import SAMLProviderService

        service = SAMLProviderService(db_session)
        created = service.create_provider(**sample_idp_metadata)

        retrieved = service.get_provider_by_entity_id(sample_idp_metadata["entity_id"])
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.entity_id == sample_idp_metadata["entity_id"]
        assert retrieved.name == created.name

    def test_get_provider_by_entity_id_not_found(self, db_session: Session):
        """Test retrieving provider with invalid entity ID returns None."""
        from app.services.saml_provider_service import SAMLProviderService

        service = SAMLProviderService(db_session)
        provider = service.get_provider_by_entity_id("http://nonexistent.entity.id")

        assert provider is None

    def test_get_provider_by_entity_id_multiple_providers(
        self, db_session: Session, sample_idp_metadata: dict
    ):
        """Test that correct provider is returned when multiple providers exist."""
        from app.services.saml_provider_service import SAMLProviderService

        service = SAMLProviderService(db_session)

        # Create first provider
        provider1 = service.create_provider(**sample_idp_metadata)

        # Create second provider with different entity ID
        metadata2 = {
            **sample_idp_metadata,
            "name": "Azure AD SSO",
            "entity_id": "https://sts.windows.net/tenant-id/",
        }
        provider2 = service.create_provider(**metadata2)

        # Retrieve by first entity ID
        retrieved1 = service.get_provider_by_entity_id(sample_idp_metadata["entity_id"])
        assert retrieved1 is not None
        assert retrieved1.id == provider1.id
        assert retrieved1.entity_id == sample_idp_metadata["entity_id"]

        # Retrieve by second entity ID
        retrieved2 = service.get_provider_by_entity_id(metadata2["entity_id"])
        assert retrieved2 is not None
        assert retrieved2.id == provider2.id
        assert retrieved2.entity_id == metadata2["entity_id"]

    def test_get_provider_by_entity_id_case_sensitivity(
        self, db_session: Session, sample_idp_metadata: dict
    ):
        """Test that entity ID lookup is case-sensitive."""
        from app.services.saml_provider_service import SAMLProviderService

        service = SAMLProviderService(db_session)
        service.create_provider(**sample_idp_metadata)

        # Try to retrieve with different case
        uppercase_entity_id = sample_idp_metadata["entity_id"].upper()
        retrieved = service.get_provider_by_entity_id(uppercase_entity_id)

        # Should not match due to case sensitivity
        assert retrieved is None

    def test_get_provider_by_entity_id_whitespace_handling(
        self, db_session: Session, sample_idp_metadata: dict
    ):
        """Test that entity ID with extra whitespace does not match."""
        from app.services.saml_provider_service import SAMLProviderService

        service = SAMLProviderService(db_session)
        service.create_provider(**sample_idp_metadata)

        # Try to retrieve with leading/trailing whitespace
        entity_id_with_spaces = f"  {sample_idp_metadata['entity_id']}  "
        retrieved = service.get_provider_by_entity_id(entity_id_with_spaces)

        # Should not match due to whitespace
        assert retrieved is None

    def test_get_provider_by_entity_id_empty_string(self, db_session: Session):
        """Test that empty string entity ID returns None."""
        from app.services.saml_provider_service import SAMLProviderService

        service = SAMLProviderService(db_session)
        provider = service.get_provider_by_entity_id("")

        assert provider is None

    def test_get_provider_by_entity_id_inactive_provider(
        self, db_session: Session, sample_idp_metadata: dict
    ):
        """Test that inactive provider with matching entity ID is still returned."""
        from app.services.saml_provider_service import SAMLProviderService

        service = SAMLProviderService(db_session)

        # Create active provider
        created = service.create_provider(**sample_idp_metadata)

        # Mark it as inactive
        service.update_provider(created.id, is_active=False)

        # Should still return the provider (caller decides how to handle inactive status)
        retrieved = service.get_provider_by_entity_id(sample_idp_metadata["entity_id"])
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.is_active is False


class TestSAMLProviderServiceValidation:
    """Test validation logic for SAML provider metadata."""

    def test_validate_url_accepts_https(self, db_session: Session):
        """Test URL validation accepts HTTPS URLs."""
        from app.services.saml_provider_service import SAMLProviderService

        service = SAMLProviderService(db_session)
        # Should not raise
        service._validate_url("https://example.com/sso", "sso_url")

    def test_validate_url_accepts_http(self, db_session: Session):
        """Test URL validation accepts HTTP URLs."""
        from app.services.saml_provider_service import SAMLProviderService

        service = SAMLProviderService(db_session)
        # Should not raise
        service._validate_url("http://localhost:8080/sso", "sso_url")

    def test_validate_url_rejects_invalid(self, db_session: Session):
        """Test URL validation rejects invalid URLs."""
        from app.services.saml_provider_service import SAMLProviderService

        service = SAMLProviderService(db_session)

        with pytest.raises(ValueError, match="sso_url"):
            service._validate_url("not-a-url", "sso_url")

    def test_validate_x509_cert_accepts_pem_format(
        self, db_session: Session, sample_x509_cert: str
    ):
        """Test certificate validation accepts PEM format."""
        from app.services.saml_provider_service import SAMLProviderService

        service = SAMLProviderService(db_session)
        # Should not raise
        service._validate_x509_cert(sample_x509_cert)

    def test_validate_x509_cert_rejects_invalid(self, db_session: Session):
        """Test certificate validation rejects invalid certificates."""
        from app.services.saml_provider_service import SAMLProviderService

        service = SAMLProviderService(db_session)

        with pytest.raises(ValueError, match="x509_cert"):
            service._validate_x509_cert("not a certificate")

    def test_validate_x509_cert_rejects_empty(self, db_session: Session):
        """Test certificate validation rejects empty string."""
        from app.services.saml_provider_service import SAMLProviderService

        service = SAMLProviderService(db_session)

        with pytest.raises(ValueError, match="x509_cert"):
            service._validate_x509_cert("")
