"""
Test SAML SP-Initiated SSO Flow

Story 2.1 - SP-Initiated SSO Flow
Tests SSO login flow, SAML AuthnRequest generation, and ACS handling.
"""
from __future__ import annotations

import base64
import re
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.response import OneLogin_Saml2_Response
from sqlalchemy.orm import Session

from app.db.models import SAMLProvider, User
from app.main import app
from app.services.saml_provider_service import SAMLProviderService
from app.services.saml_service import SAMLService

client = TestClient(app)


@pytest.fixture
def test_organization_id() -> str:
    """Provide test organization ID."""
    return "test-org-123"


@pytest.fixture
def saml_provider(db_session: Session, test_organization_id: str) -> SAMLProvider:
    """Create a test SAML provider."""
    provider_service = SAMLProviderService(db_session)

    cert = """-----BEGIN CERTIFICATE-----
MIICXDCCAcWgAwIBAgIBADANBgkqhkiG9w0BAQ0FADBLMQswCQYDVQQGEwJ1czEL
MAkGA1UECAwCQ0ExFjAUBgNVBAcMDVNhbiBGcmFuY2lzY28xFzAVBgNVBAMMDnRl
c3QuZXhhbXBsZS5jb20wHhcNMjQwMTAxMDAwMDAwWhcNMjUwMTAxMDAwMDAwWjBL
MQswCQYDVQQGEwJ1czELMAkGA1UECAwCQ0ExFjAUBgNVBAcMDVNhbiBGcmFuY2lz
Y28xFzAVBgNVBAMMDnRlc3QuZXhhbXBsZS5jb20wgZ8wDQYJKoZIhvcNAQEBBQAD
gY0AMIGJAoGBALHXd8F6y3B0K5K5K5K5K5K5K5K5K5K5K5K5K5K5K5K5K5K5K5K5
AgMBAAGjUDBOMB0GA1UdDgQWBBQZ0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0ZMB8GA1UdIwQY
MBaAFBnRnRnRnRnRnRnRnRnRnRnRnRnRMAwGA1UdEwQFMAMBAf8wDQYJKoZIhvcN
AQENBQADgYEAb0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0
Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0Z0
-----END CERTIFICATE-----"""

    return provider_service.create_provider(
        organization_id=test_organization_id,
        name="Test IdP",
        entity_id="https://idp.example.com/metadata",
        sso_url="https://idp.example.com/sso",
        slo_url="https://idp.example.com/slo",
        x509_cert=cert,
        is_active=True,
    )


# Test 1: POST /api/auth/saml/login - Initiate SSO
def test_saml_login_initiate_success(
    db_session: Session,
    saml_provider: SAMLProvider,
) -> None:
    """Test successful SSO initiation with valid provider ID."""
    response = client.post(
        "/api/auth/saml/login",
        json={"provider_id": saml_provider.id},
    )

    assert response.status_code == 200
    data = response.json()

    # Should return redirect URL
    assert "redirect_url" in data
    assert data["redirect_url"].startswith("https://idp.example.com/sso")

    # URL should contain SAMLRequest parameter
    parsed_url = urlparse(data["redirect_url"])
    query_params = parse_qs(parsed_url.query)
    assert "SAMLRequest" in query_params

    # SAMLRequest should be base64 encoded
    saml_request = query_params["SAMLRequest"][0]
    assert len(saml_request) > 0

    # Should be decodable
    try:
        decoded = base64.b64decode(saml_request)
        assert b"AuthnRequest" in decoded or b"samlp:AuthnRequest" in decoded
    except Exception as e:
        pytest.fail(f"SAMLRequest not properly base64 encoded: {e}")


# Test 2: POST /api/auth/saml/login - Provider not found
def test_saml_login_provider_not_found(db_session: Session) -> None:
    """Test SSO initiation with non-existent provider ID."""
    response = client.post(
        "/api/auth/saml/login",
        json={"provider_id": "non-existent-provider"},
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# Test 3: POST /api/auth/saml/login - Inactive provider
def test_saml_login_inactive_provider(
    db_session: Session,
    saml_provider: SAMLProvider,
) -> None:
    """Test SSO initiation with inactive provider."""
    # Deactivate provider
    provider_service = SAMLProviderService(db_session)
    provider_service.update_provider(saml_provider.id, is_active=False)

    response = client.post(
        "/api/auth/saml/login",
        json={"provider_id": saml_provider.id},
    )

    assert response.status_code == 400
    assert "inactive" in response.json()["detail"].lower()


# Test 4: SAMLService - Generate AuthnRequest
def test_saml_service_generate_authn_request(saml_provider: SAMLProvider) -> None:
    """Test SAML AuthnRequest generation."""
    service = SAMLService()

    # Generate AuthnRequest
    authn_request_data = service.generate_authn_request(saml_provider)

    assert "redirect_url" in authn_request_data
    assert "saml_request" in authn_request_data
    assert authn_request_data["redirect_url"].startswith(saml_provider.sso_url)

    # SAMLRequest should be base64 encoded
    saml_request = authn_request_data["saml_request"]
    decoded = base64.b64decode(saml_request)
    assert b"AuthnRequest" in decoded or b"samlp:AuthnRequest" in decoded


# Test 5: POST /api/auth/saml/acs - Handle valid SAML Response
@patch("app.services.saml_service.OneLogin_Saml2_Auth")
def test_saml_acs_valid_response(
    mock_saml_auth: MagicMock,
    db_session: Session,
    saml_provider: SAMLProvider,
) -> None:
    """Test ACS handling with valid SAML Response."""
    # Mock OneLogin SAML Auth
    mock_auth_instance = MagicMock()
    mock_auth_instance.is_authenticated.return_value = True
    mock_auth_instance.get_attributes.return_value = {
        "email": ["user@example.com"],
        "firstName": ["John"],
        "lastName": ["Doe"],
    }
    mock_auth_instance.get_nameid.return_value = "user@example.com"
    mock_auth_instance.get_errors.return_value = []
    mock_saml_auth.return_value = mock_auth_instance

    # Simulate SAML Response
    saml_response = base64.b64encode(b"<fake-saml-response>").decode("utf-8")

    response = client.post(
        "/api/auth/saml/acs",
        data={
            "SAMLResponse": saml_response,
            "RelayState": saml_provider.id,
        },
    )

    assert response.status_code == 200
    data = response.json()

    # Should return user info and session token
    assert "user" in data
    assert "session_token" in data
    assert data["user"]["email"] == "user@example.com"
    assert data["user"]["name"] == "John Doe"


# Test 6: POST /api/auth/saml/acs - Invalid SAML Response
@patch("app.services.saml_service.OneLogin_Saml2_Auth")
def test_saml_acs_invalid_response(
    mock_saml_auth: MagicMock,
    db_session: Session,
    saml_provider: SAMLProvider,
) -> None:
    """Test ACS handling with invalid SAML Response."""
    # Mock OneLogin SAML Auth with authentication failure
    mock_auth_instance = MagicMock()
    mock_auth_instance.is_authenticated.return_value = False
    mock_auth_instance.get_errors.return_value = ["Invalid signature"]
    mock_saml_auth.return_value = mock_auth_instance

    saml_response = base64.b64encode(b"<invalid-saml-response>").decode("utf-8")

    response = client.post(
        "/api/auth/saml/acs",
        data={
            "SAMLResponse": saml_response,
            "RelayState": saml_provider.id,
        },
    )

    assert response.status_code == 401
    assert "authentication failed" in response.json()["detail"].lower()


# Test 7: POST /api/auth/saml/acs - Missing email attribute
@patch("app.services.saml_service.OneLogin_Saml2_Auth")
def test_saml_acs_missing_email(
    mock_saml_auth: MagicMock,
    db_session: Session,
    saml_provider: SAMLProvider,
) -> None:
    """Test ACS handling when email attribute is missing."""
    mock_auth_instance = MagicMock()
    mock_auth_instance.is_authenticated.return_value = True
    mock_auth_instance.get_attributes.return_value = {
        "firstName": ["John"],
        "lastName": ["Doe"],
    }
    mock_auth_instance.get_nameid.return_value = None
    mock_auth_instance.get_errors.return_value = []
    mock_saml_auth.return_value = mock_auth_instance

    saml_response = base64.b64encode(b"<saml-response>").decode("utf-8")

    response = client.post(
        "/api/auth/saml/acs",
        data={
            "SAMLResponse": saml_response,
            "RelayState": saml_provider.id,
        },
    )

    assert response.status_code == 400
    assert "email" in response.json()["detail"].lower()


# Test 8: SAMLService - Extract user attributes
def test_saml_service_extract_attributes() -> None:
    """Test extracting user attributes from SAML Response."""
    service = SAMLService()

    # Mock SAML attributes
    saml_attributes = {
        "email": ["user@example.com"],
        "firstName": ["Jane"],
        "lastName": ["Smith"],
        "displayName": ["Jane Smith"],
    }

    user_attrs = service.extract_user_attributes(
        saml_attributes,
        nameid="user@example.com",
    )

    assert user_attrs["email"] == "user@example.com"
    assert user_attrs["name"] == "Jane Smith"


# Test 9: SAMLService - Create or update user session
def test_saml_service_create_session(db_session: Session) -> None:
    """Test creating user session after SAML authentication."""
    service = SAMLService()

    user_data = {
        "email": "newuser@example.com",
        "name": "New User",
    }

    session_data = service.create_or_update_session(
        db_session,
        user_data,
        organization_id="test-org-123",
    )

    assert "user_id" in session_data
    assert "session_token" in session_data
    assert "expires_at" in session_data

    # Verify user was created
    user = db_session.query(User).filter(User.email == "newuser@example.com").first()
    assert user is not None
    assert user.name == "New User"


# Test 10: SAMLService - Update existing user session
def test_saml_service_update_existing_user(db_session: Session) -> None:
    """Test updating session for existing user."""
    # Create existing user
    existing_user = User(
        id="existing-user-id",
        email="existing@example.com",
        name="Old Name",
        password_hash="dummy-hash",
        email_verified=True,
        status="active",
    )
    db_session.add(existing_user)
    db_session.commit()

    service = SAMLService()

    user_data = {
        "email": "existing@example.com",
        "name": "Updated Name",
    }

    session_data = service.create_or_update_session(
        db_session,
        user_data,
        organization_id="test-org-123",
    )

    assert session_data["user_id"] == "existing-user-id"

    # Verify user name was updated
    db_session.refresh(existing_user)
    assert existing_user.name == "Updated Name"
