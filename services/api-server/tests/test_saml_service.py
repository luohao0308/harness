"""
Tests for SAML service - SP metadata generation and configuration.

Following TDD: These tests are written first, then implementation follows.
Story 1.1 - SAML Service Provider Setup
Acceptance Criteria:
1. Generate SP metadata XML
2. Serve metadata at `/api/auth/saml/metadata`
3. Configure entity ID, ACS URL, SLS URL
4. Load X.509 certificate from config
"""

from pathlib import Path

import pytest
from lxml import etree


@pytest.fixture
def saml_config():
    """SAML configuration fixture for testing."""
    return {
        "sp_entity_id": "http://localhost:8000/api/auth/saml/metadata",
        "sp_acs_url": "http://localhost:8000/api/auth/saml/acs",
        "sp_sls_url": "http://localhost:8000/api/auth/saml/sls",
        "sp_x509_cert_path": "certs/saml_sp.crt",
        "sp_private_key_path": "certs/saml_sp.key",
    }


@pytest.fixture
def cert_files_exist():
    """Check if certificate files exist."""
    cert_path = Path("certs/saml_sp.crt")
    key_path = Path("certs/saml_sp.key")
    return cert_path.exists() and key_path.exists()


class TestSAMLConfiguration:
    """Test SAML configuration service."""

    def test_saml_config_has_required_fields(self, saml_config):
        """Test that SAML config contains all required fields."""
        required_fields = [
            "sp_entity_id",
            "sp_acs_url",
            "sp_sls_url",
            "sp_x509_cert_path",
            "sp_private_key_path",
        ]

        for field in required_fields:
            assert field in saml_config, f"Missing required field: {field}"

    def test_saml_config_urls_are_valid(self, saml_config):
        """Test that SAML URLs are properly formatted."""
        assert saml_config["sp_entity_id"].startswith("http")
        assert saml_config["sp_acs_url"].startswith("http")
        assert saml_config["sp_sls_url"].startswith("http")

        assert "/api/auth/saml/metadata" in saml_config["sp_entity_id"]
        assert "/api/auth/saml/acs" in saml_config["sp_acs_url"]
        assert "/api/auth/saml/sls" in saml_config["sp_sls_url"]

    def test_certificate_paths_are_configured(self, saml_config):
        """Test that certificate paths are configured."""
        assert saml_config["sp_x509_cert_path"]
        assert saml_config["sp_private_key_path"]
        assert saml_config["sp_x509_cert_path"].endswith(".crt")
        assert saml_config["sp_private_key_path"].endswith(".key")

    def test_runtime_config_loads_certificates_independent_of_cwd(
        self,
        monkeypatch,
        tmp_path,
    ):
        """Certificate loading must not depend on the process working directory."""
        from app.config.saml_config import get_saml_config

        monkeypatch.chdir(tmp_path)

        runtime_config = get_saml_config()

        assert "BEGIN CERTIFICATE" in runtime_config["sp_x509_cert"]
        assert "BEGIN PRIVATE KEY" in runtime_config["sp_private_key"]


class TestSAMLMetadataGeneration:
    """Test SAML SP metadata XML generation."""

    def test_generate_metadata_returns_xml_string(self):
        """Test that metadata generation returns a valid XML string."""
        from app.services.saml_service import SAMLService

        service = SAMLService()
        metadata_xml = service.generate_sp_metadata()

        assert metadata_xml is not None
        assert isinstance(metadata_xml, str)
        assert len(metadata_xml) > 0

    def test_metadata_xml_is_valid_xml(self):
        """Test that generated metadata is valid XML."""
        from app.services.saml_service import SAMLService

        service = SAMLService()
        metadata_xml = service.generate_sp_metadata()

        # Parse XML - will raise exception if invalid
        root = etree.fromstring(metadata_xml.encode("utf-8"))
        assert root is not None

    def test_metadata_contains_entity_descriptor(self):
        """Test that metadata contains EntityDescriptor element."""
        from app.services.saml_service import SAMLService

        service = SAMLService()
        metadata_xml = service.generate_sp_metadata()

        root = etree.fromstring(metadata_xml.encode("utf-8"))

        # Check for EntityDescriptor (may have namespace)
        assert "EntityDescriptor" in root.tag

    def test_metadata_contains_entity_id(self):
        """Test that metadata contains entityID attribute."""
        from app.services.saml_service import SAMLService

        service = SAMLService()
        metadata_xml = service.generate_sp_metadata()

        root = etree.fromstring(metadata_xml.encode("utf-8"))
        entity_id = root.get("entityID")

        assert entity_id is not None
        assert entity_id == "http://localhost:8000/api/auth/saml/metadata"

    def test_metadata_contains_acs_url(self):
        """Test that metadata contains ACS (Assertion Consumer Service) URL."""
        from app.services.saml_service import SAMLService

        service = SAMLService()
        metadata_xml = service.generate_sp_metadata()

        root = etree.fromstring(metadata_xml.encode("utf-8"))

        # Find AssertionConsumerService element
        namespaces = {"md": "urn:oasis:names:tc:SAML:2.0:metadata"}
        acs_elements = root.xpath("//md:AssertionConsumerService", namespaces=namespaces)

        assert len(acs_elements) > 0
        acs_url = acs_elements[0].get("Location")
        assert acs_url == "http://localhost:8000/api/auth/saml/acs"

    def test_metadata_contains_sls_url(self):
        """Test that metadata contains SLS (Single Logout Service) URL."""
        from app.services.saml_service import SAMLService

        service = SAMLService()
        metadata_xml = service.generate_sp_metadata()

        root = etree.fromstring(metadata_xml.encode("utf-8"))

        # Find SingleLogoutService element
        namespaces = {"md": "urn:oasis:names:tc:SAML:2.0:metadata"}
        sls_elements = root.xpath("//md:SingleLogoutService", namespaces=namespaces)

        assert len(sls_elements) > 0
        sls_url = sls_elements[0].get("Location")
        assert sls_url == "http://localhost:8000/api/auth/saml/sls"

    def test_metadata_contains_x509_certificate(self, cert_files_exist):
        """Test that metadata contains X.509 certificate."""
        if not cert_files_exist:
            pytest.skip("Certificate files not found")

        from app.services.saml_service import SAMLService

        service = SAMLService()
        metadata_xml = service.generate_sp_metadata()

        root = etree.fromstring(metadata_xml.encode("utf-8"))

        # Find X509Certificate element
        namespaces = {
            "md": "urn:oasis:names:tc:SAML:2.0:metadata",
            "ds": "http://www.w3.org/2000/09/xmldsig#",
        }
        cert_elements = root.xpath("//ds:X509Certificate", namespaces=namespaces)

        assert len(cert_elements) > 0
        cert_text = cert_elements[0].text
        assert cert_text is not None
        assert len(cert_text.strip()) > 0
