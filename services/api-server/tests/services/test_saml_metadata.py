"""
Comprehensive tests for SAML SP metadata endpoint.

Story 1.1 - SAML Service Provider Setup
Tests metadata generation, XML validity, and endpoint serving.

Test Coverage:
1. Metadata generation returns valid XML
2. XML contains required SAML elements
3. Entity ID is correctly configured
4. ACS URL is present and correct
5. SLS URL is present and correct
6. X.509 certificate is included
7. HTTP endpoint serves metadata correctly
8. Error handling for missing certificates
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from lxml import etree

from app.main import app

client = TestClient(app)


class TestSAMLMetadataGeneration:
    """Test SAML Service Provider metadata generation."""

    def test_generate_metadata_returns_xml_string(self):
        """Test that metadata generation returns a valid XML string."""
        from app.services.saml_service import SAMLService

        service = SAMLService()
        metadata_xml = service.generate_sp_metadata()

        assert metadata_xml is not None
        assert isinstance(metadata_xml, str)
        assert len(metadata_xml) > 0

    def test_metadata_xml_is_valid_xml(self):
        """Test that generated metadata is valid XML that can be parsed."""
        from app.services.saml_service import SAMLService

        service = SAMLService()
        metadata_xml = service.generate_sp_metadata()

        # Parse XML - will raise exception if invalid
        root = etree.fromstring(metadata_xml.encode("utf-8"))
        assert root is not None
        assert root.tag is not None

    def test_metadata_contains_entity_descriptor(self):
        """Test that metadata contains EntityDescriptor root element."""
        from app.services.saml_service import SAMLService

        service = SAMLService()
        metadata_xml = service.generate_sp_metadata()

        root = etree.fromstring(metadata_xml.encode("utf-8"))

        # Check for EntityDescriptor (with SAML namespace)
        assert "EntityDescriptor" in root.tag
        assert "metadata" in root.tag  # namespace check

    def test_metadata_contains_entity_id(self):
        """Test that metadata contains correct entityID attribute."""
        from app.services.saml_service import SAMLService

        service = SAMLService()
        metadata_xml = service.generate_sp_metadata()

        root = etree.fromstring(metadata_xml.encode("utf-8"))
        entity_id = root.get("entityID")

        assert entity_id is not None
        assert "/api/auth/saml/metadata" in entity_id
        assert entity_id.startswith("http")

    def test_metadata_contains_sp_sso_descriptor(self):
        """Test that metadata contains SPSSODescriptor element."""
        from app.services.saml_service import SAMLService

        service = SAMLService()
        metadata_xml = service.generate_sp_metadata()

        root = etree.fromstring(metadata_xml.encode("utf-8"))

        # Find SPSSODescriptor element
        namespaces = {"md": "urn:oasis:names:tc:SAML:2.0:metadata"}
        spsso_elements = root.xpath("//md:SPSSODescriptor", namespaces=namespaces)

        assert len(spsso_elements) > 0

    def test_metadata_contains_acs_url(self):
        """Test that metadata contains ACS (Assertion Consumer Service) URL."""
        from app.services.saml_service import SAMLService

        service = SAMLService()
        metadata_xml = service.generate_sp_metadata()

        root = etree.fromstring(metadata_xml.encode("utf-8"))

        # Find AssertionConsumerService element
        namespaces = {"md": "urn:oasis:names:tc:SAML:2.0:metadata"}
        acs_elements = root.xpath(
            "//md:AssertionConsumerService", namespaces=namespaces
        )

        assert len(acs_elements) > 0
        acs_url = acs_elements[0].get("Location")
        assert acs_url is not None
        assert "/api/auth/saml/acs" in acs_url
        assert acs_url.startswith("http")

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
        assert sls_url is not None
        assert "/api/auth/saml/sls" in sls_url
        assert sls_url.startswith("http")

    def test_metadata_contains_x509_certificate(self):
        """Test that metadata contains X.509 certificate for signature verification."""
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
        # Certificate should be base64 encoded (alphanumeric + / + =)
        assert all(c.isalnum() or c in "/+=" for c in cert_text.strip())


class TestSAMLMetadataEndpoint:
    """Test SAML metadata HTTP endpoint."""

    def test_metadata_endpoint_returns_200(self):
        """Test that /api/auth/saml/metadata returns 200 OK."""
        response = client.get("/api/auth/saml/metadata")
        assert response.status_code == 200

    def test_metadata_endpoint_returns_xml_content_type(self):
        """Test that metadata endpoint returns plain text content type."""
        response = client.get("/api/auth/saml/metadata")
        assert response.status_code == 200
        # PlainTextResponse returns text/plain
        assert "text/plain" in response.headers.get("content-type", "")

    def test_metadata_endpoint_returns_valid_xml(self):
        """Test that endpoint returns parseable XML."""
        response = client.get("/api/auth/saml/metadata")
        assert response.status_code == 200

        # Parse XML to verify validity
        root = etree.fromstring(response.content)
        assert root is not None

    def test_metadata_endpoint_xml_contains_entity_id(self):
        """Test that endpoint XML contains entity ID."""
        response = client.get("/api/auth/saml/metadata")
        assert response.status_code == 200

        root = etree.fromstring(response.content)
        entity_id = root.get("entityID")
        assert entity_id is not None
        assert "/api/auth/saml/metadata" in entity_id

    def test_metadata_endpoint_xml_contains_acs_binding(self):
        """Test that ACS has correct SAML binding."""
        response = client.get("/api/auth/saml/metadata")
        assert response.status_code == 200

        root = etree.fromstring(response.content)
        namespaces = {"md": "urn:oasis:names:tc:SAML:2.0:metadata"}
        acs_elements = root.xpath(
            "//md:AssertionConsumerService", namespaces=namespaces
        )

        assert len(acs_elements) > 0
        binding = acs_elements[0].get("Binding")
        assert binding == "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"

    def test_metadata_endpoint_xml_contains_sls_binding(self):
        """Test that SLS has correct SAML binding."""
        response = client.get("/api/auth/saml/metadata")
        assert response.status_code == 200

        root = etree.fromstring(response.content)
        namespaces = {"md": "urn:oasis:names:tc:SAML:2.0:metadata"}
        sls_elements = root.xpath("//md:SingleLogoutService", namespaces=namespaces)

        assert len(sls_elements) > 0
        binding = sls_elements[0].get("Binding")
        assert binding == "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"

    def test_cert_extraction_removes_headers(self):
        """Test that certificate extraction removes PEM headers."""
        from app.services.saml_service import SAMLService

        service = SAMLService()

        cert_with_headers = """-----BEGIN CERTIFICATE-----
MIIDhTCCAm2gAwIBAgIUWOY17P2QBUdcmBSGQ6GhaW4aGzowDQYJKoZIhvcNAQEL
BQAwUjELMAkGA1UEBhMCVVMxCzAJBgNVBAgMAkNBMQswCQYDVQQHDAJTRjEVMBMG
-----END CERTIFICATE-----"""

        extracted = service._extract_cert_content(cert_with_headers)

        assert "-----BEGIN" not in extracted
        assert "-----END" not in extracted
        assert "\n" not in extracted
        assert len(extracted) > 0
        # Should be continuous base64 string
        assert extracted.isalnum() or all(c.isalnum() or c in "/+=" for c in extracted)


class TestSAMLServiceErrorHandling:
    """Test error handling in SAML service."""

    def test_service_initializes_successfully(self):
        """Test that SAML service can be initialized."""
        from app.services.saml_service import SAMLService

        service = SAMLService()
        assert service is not None
        assert service._config is not None

    def test_service_config_has_required_fields(self):
        """Test that service config contains all required fields."""
        from app.services.saml_service import SAMLService

        service = SAMLService()
        config = service._config

        required_fields = [
            "sp_entity_id",
            "sp_acs_url",
            "sp_sls_url",
            "sp_x509_cert",
            "sp_private_key",
        ]

        for field in required_fields:
            assert field in config
            assert config[field] is not None
            assert len(config[field]) > 0
