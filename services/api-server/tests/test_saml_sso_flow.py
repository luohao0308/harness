"""
Test SAML SP-Initiated SSO Flow

Story 2.1 - SP-Initiated SSO Flow
Tests SSO login flow, SAML AuthnRequest generation, and ACS handling.
"""

from __future__ import annotations

import base64
import zlib
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
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
        decoded = zlib.decompress(base64.b64decode(saml_request), wbits=-15)
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
    decoded = zlib.decompress(base64.b64decode(saml_request), wbits=-15)
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


# Story 2.2 - SAML Assertion Validation Tests


# Test 11: Validate SAML signature with valid certificate
@patch("app.services.saml_service.OneLogin_Saml2_Auth")
def test_validate_saml_signature_success(
    mock_saml_auth: MagicMock,
    saml_provider: SAMLProvider,
) -> None:
    """Test SAML signature validation with valid IdP certificate."""
    service = SAMLService()

    # Mock successful signature validation
    mock_auth_instance = MagicMock()
    mock_auth_instance.is_authenticated.return_value = True
    mock_auth_instance.get_errors.return_value = []
    mock_saml_auth.return_value = mock_auth_instance

    # Should not raise any exception
    result = service.validate_saml_signature(
        saml_response="<valid-signed-response>",
        provider=saml_provider,
    )
    assert result is True


# Test 12: Validate SAML signature with invalid signature
@patch("app.services.saml_service.OneLogin_Saml2_Auth")
def test_validate_saml_signature_invalid(
    mock_saml_auth: MagicMock,
    saml_provider: SAMLProvider,
) -> None:
    """Test SAML signature validation with invalid signature."""
    service = SAMLService()

    # Mock signature validation failure
    mock_auth_instance = MagicMock()
    mock_auth_instance.is_authenticated.return_value = False
    mock_auth_instance.get_errors.return_value = ["invalid_signature"]
    mock_auth_instance.get_last_error_reason.return_value = "Invalid signature"
    mock_saml_auth.return_value = mock_auth_instance

    # Should raise ValueError with signature error
    with pytest.raises(ValueError) as exc_info:
        service.validate_saml_signature(
            saml_response="<invalid-signed-response>",
            provider=saml_provider,
        )
    assert "signature" in str(exc_info.value).lower()


# Test 13: Check assertion validity period - valid assertion
def test_check_assertion_validity_valid() -> None:
    """Test assertion validity check with valid NotBefore and NotAfter."""
    service = SAMLService()

    # Create assertion with valid time window
    now = datetime.now(UTC)
    not_before = now - timedelta(minutes=5)
    not_after = now + timedelta(hours=1)

    # Should not raise any exception
    result = service.check_assertion_validity(
        not_before=not_before.isoformat(),
        not_after=not_after.isoformat(),
    )
    assert result is True


# Test 14: Check assertion validity period - expired assertion
def test_check_assertion_validity_expired() -> None:
    """Test assertion validity check with expired assertion."""
    service = SAMLService()

    # Create expired assertion
    now = datetime.now(UTC)
    not_before = now - timedelta(hours=2)
    not_after = now - timedelta(hours=1)

    # Should raise ValueError
    with pytest.raises(ValueError) as exc_info:
        service.check_assertion_validity(
            not_before=not_before.isoformat(),
            not_after=not_after.isoformat(),
        )
    assert "expired" in str(exc_info.value).lower()


# Test 15: Check assertion validity period - not yet valid
def test_check_assertion_validity_not_yet_valid() -> None:
    """Test assertion validity check with future NotBefore."""
    service = SAMLService()

    # Create assertion with future NotBefore
    now = datetime.now(UTC)
    not_before = now + timedelta(minutes=10)
    not_after = now + timedelta(hours=1)

    # Should raise ValueError
    with pytest.raises(ValueError) as exc_info:
        service.check_assertion_validity(
            not_before=not_before.isoformat(),
            not_after=not_after.isoformat(),
        )
    assert "not yet valid" in str(exc_info.value).lower()


# Test 16: Verify audience restriction - valid audience
def test_verify_audience_valid(saml_provider: SAMLProvider) -> None:
    """Test audience restriction validation with matching SP entity ID."""
    service = SAMLService()

    # Mock SP entity ID from config
    with patch("app.services.saml_service.get_saml_config") as mock_config:
        mock_config.return_value = {
            "sp_entity_id": "https://sp.example.com/metadata",
            "sp_acs_url": "https://sp.example.com/acs",
            "sp_sls_url": "https://sp.example.com/sls",
            "sp_x509_cert": "test-cert",
            "sp_private_key": "test-key",
        }
        service._config = mock_config.return_value

        # Should not raise exception
        result = service.verify_audience(
            audience="https://sp.example.com/metadata",
        )
        assert result is True


# Test 17: Verify audience restriction - mismatched audience
def test_verify_audience_mismatch(saml_provider: SAMLProvider) -> None:
    """Test audience restriction validation with mismatched SP entity ID."""
    service = SAMLService()

    # Mock SP entity ID from config
    with patch("app.services.saml_service.get_saml_config") as mock_config:
        mock_config.return_value = {
            "sp_entity_id": "https://sp.example.com/metadata",
            "sp_acs_url": "https://sp.example.com/acs",
            "sp_sls_url": "https://sp.example.com/sls",
            "sp_x509_cert": "test-cert",
            "sp_private_key": "test-key",
        }
        service._config = mock_config.return_value

        # Should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            service.verify_audience(
                audience="https://wrong-sp.example.com/metadata",
            )
        assert "audience" in str(exc_info.value).lower()


# Test 18: Extract user claims including groups
def test_extract_user_claims_with_groups() -> None:
    """Test extracting user claims including groups from SAML attributes."""
    service = SAMLService()

    saml_attributes = {
        "email": ["user@example.com"],
        "firstName": ["Alice"],
        "lastName": ["Johnson"],
        "groups": ["admin", "developers", "managers"],
    }

    claims = service.extract_user_claims(
        saml_attributes=saml_attributes,
        nameid="user@example.com",
    )

    assert claims["email"] == "user@example.com"
    assert claims["name"] == "Alice Johnson"
    assert "groups" in claims
    assert claims["groups"] == ["admin", "developers", "managers"]


# Test 19: Extract user claims without groups
def test_extract_user_claims_without_groups() -> None:
    """Test extracting user claims when groups attribute is missing."""
    service = SAMLService()

    saml_attributes = {
        "email": ["user@example.com"],
        "firstName": ["Bob"],
        "lastName": ["Smith"],
    }

    claims = service.extract_user_claims(
        saml_attributes=saml_attributes,
        nameid="user@example.com",
    )

    assert claims["email"] == "user@example.com"
    assert claims["name"] == "Bob Smith"
    assert "groups" in claims
    assert claims["groups"] == []


# Test 20: Complete validation flow with all checks
@patch("app.services.saml_service.OneLogin_Saml2_Auth")
def test_process_saml_response_with_full_validation(
    mock_saml_auth: MagicMock,
    db_session: Session,
    saml_provider: SAMLProvider,
) -> None:
    """Test complete SAML response processing with all validation checks."""
    service = SAMLService()

    # Mock OneLogin SAML Auth with full validation
    mock_auth_instance = MagicMock()
    mock_auth_instance.is_authenticated.return_value = True
    mock_auth_instance.get_errors.return_value = []

    # Mock assertion attributes
    mock_auth_instance.get_attributes.return_value = {
        "email": ["validated-user@example.com"],
        "firstName": ["Validated"],
        "lastName": ["User"],
        "groups": ["engineering", "platform"],
    }
    mock_auth_instance.get_nameid.return_value = "validated-user@example.com"

    mock_saml_auth.return_value = mock_auth_instance

    # Process SAML response
    saml_response = "base64-encoded-saml-response"
    result = service.process_saml_response(
        saml_response=saml_response,
        provider=saml_provider,
    )

    assert result["authenticated"] is True
    assert result["nameid"] == "validated-user@example.com"
    assert "groups" in result["attributes"]
    assert result["attributes"]["groups"] == ["engineering", "platform"]


# Story 4.2 - Single Logout (SLO) Tests


# Test 21: SAMLService - Initiate logout (generate LogoutRequest)
def test_saml_service_initiate_logout(saml_provider: SAMLProvider) -> None:
    """Test generating SAML LogoutRequest for SP-initiated SLO."""
    service = SAMLService()

    # Generate LogoutRequest
    logout_data = service.initiate_logout(
        provider=saml_provider,
        session_id="test-session-123",
        nameid="user@example.com",
    )

    assert "redirect_url" in logout_data
    assert logout_data["redirect_url"].startswith(saml_provider.slo_url)

    # URL should contain SAMLRequest parameter
    parsed_url = urlparse(logout_data["redirect_url"])
    query_params = parse_qs(parsed_url.query)
    assert "SAMLRequest" in query_params

    # SAMLRequest should be base64 encoded
    saml_request = query_params["SAMLRequest"][0]
    assert len(saml_request) > 0

    # Should be decodable and contain LogoutRequest
    try:
        decoded = zlib.decompress(base64.b64decode(saml_request), wbits=-15)
        assert b"LogoutRequest" in decoded or b"samlp:LogoutRequest" in decoded
    except Exception as e:
        pytest.fail(f"SAMLRequest not properly base64 encoded: {e}")


# Test 22: SAMLService - Handle logout response
@patch("app.services.saml_service.OneLogin_Saml2_Auth")
def test_saml_service_handle_logout_response(
    mock_saml_auth: MagicMock,
    saml_provider: SAMLProvider,
) -> None:
    """Test processing SAML LogoutResponse from IdP."""
    service = SAMLService()

    # Mock OneLogin SAML Auth
    mock_auth_instance = MagicMock()
    mock_auth_instance.get_errors.return_value = []
    mock_auth_instance.get_last_error_reason.return_value = None
    mock_saml_auth.return_value = mock_auth_instance

    # Process LogoutResponse
    saml_response = base64.b64encode(b"<fake-logout-response>").decode("utf-8")

    result = service.handle_logout_response(
        saml_response=saml_response,
        provider=saml_provider,
    )

    assert result["success"] is True


# Test 23: SAMLService - Handle logout response with error
@patch("app.services.saml_service.OneLogin_Saml2_Auth")
def test_saml_service_handle_logout_response_error(
    mock_saml_auth: MagicMock,
    saml_provider: SAMLProvider,
) -> None:
    """Test processing SAML LogoutResponse with errors."""
    service = SAMLService()

    # Mock OneLogin SAML Auth with errors
    mock_auth_instance = MagicMock()
    mock_auth_instance.get_errors.return_value = ["logout_failed"]
    mock_auth_instance.get_last_error_reason.return_value = "Logout failed at IdP"
    mock_saml_auth.return_value = mock_auth_instance

    saml_response = base64.b64encode(b"<error-logout-response>").decode("utf-8")

    with pytest.raises(ValueError) as exc_info:
        service.handle_logout_response(
            saml_response=saml_response,
            provider=saml_provider,
        )
    assert "logout" in str(exc_info.value).lower()


# Test 24: POST /api/auth/saml/logout - Initiate SLO
def test_saml_logout_initiate_success(
    db_session: Session,
    saml_provider: SAMLProvider,
) -> None:
    """Test initiating SAML Single Logout."""
    # Create a session first
    from app.services.session_service import SessionService

    session_service = SessionService(db_session)
    session_data = session_service.create_session(
        user_id="test-user-123",
        email="user@example.com",
        roles=["user"],
        ttl_hours=24,
    )

    # Extract session ID from access token
    import jwt

    from app.core.config import get_settings

    settings = get_settings()
    claims = jwt.decode(
        session_data["access_token"],
        settings.auth_jwt_secret,
        algorithms=["HS256"],
    )
    session_id = claims["jti"]

    # Initiate logout
    response = client.post(
        "/api/auth/saml/logout",
        json={
            "provider_id": saml_provider.id,
            "session_id": session_id,
            "nameid": "user@example.com",
        },
    )

    assert response.status_code == 200
    data = response.json()

    # Should return redirect URL
    assert "redirect_url" in data
    assert data["redirect_url"].startswith(saml_provider.slo_url)

    # Session should be revoked
    session = session_service.get_session(session_id)
    assert session.revoked_at is not None


# Test 25: POST /api/auth/saml/sls - Handle LogoutResponse
@patch("app.services.saml_service.OneLogin_Saml2_Auth")
def test_saml_sls_success(
    mock_saml_auth: MagicMock,
    db_session: Session,
    saml_provider: SAMLProvider,
) -> None:
    """Test handling SAML LogoutResponse at Single Logout Service endpoint."""
    # Mock OneLogin SAML Auth
    mock_auth_instance = MagicMock()
    mock_auth_instance.get_errors.return_value = []
    mock_auth_instance.get_last_error_reason.return_value = None
    mock_saml_auth.return_value = mock_auth_instance

    # Simulate SAML LogoutResponse
    saml_response = base64.b64encode(b"<fake-logout-response>").decode("utf-8")

    response = client.post(
        "/api/auth/saml/sls",
        data={
            "SAMLResponse": saml_response,
            "RelayState": saml_provider.id,
        },
    )

    assert response.status_code == 200
    data = response.json()

    # Should indicate successful logout
    assert data["success"] is True
    assert "message" in data


# Story 3.1 - IdP-Initiated (Unsolicited) SSO Tests


# Test 26: POST /api/auth/saml/acs - IdP-initiated SSO (no RelayState)
@patch("app.services.saml_service.OneLogin_Saml2_Auth")
def test_saml_acs_idp_initiated_no_relay_state(
    mock_saml_auth: MagicMock,
    db_session: Session,
    saml_provider: SAMLProvider,
) -> None:
    """Test ACS handling with IdP-initiated SAML Response (no RelayState)."""
    # Mock OneLogin SAML Auth
    mock_auth_instance = MagicMock()
    mock_auth_instance.is_authenticated.return_value = True
    mock_auth_instance.get_attributes.return_value = {
        "email": ["idp-user@example.com"],
        "firstName": ["IdP"],
        "lastName": ["User"],
    }
    mock_auth_instance.get_nameid.return_value = "idp-user@example.com"
    mock_auth_instance.get_errors.return_value = []
    mock_saml_auth.return_value = mock_auth_instance

    # Simulate SAML Response without RelayState (IdP-initiated)
    saml_response = base64.b64encode(b"<fake-saml-response>").decode("utf-8")

    # Issuer extraction is performed before provider-specific signature validation.
    with patch(
        "app.services.saml_service.SAMLService.extract_issuer_from_response",
        return_value=saml_provider.entity_id,
    ):
        response = client.post(
            "/api/auth/saml/acs",
            data={
                "SAMLResponse": saml_response,
                # No RelayState for IdP-initiated
            },
        )

    assert response.status_code == 200
    data = response.json()

    # Should return user info and session token
    assert "user" in data
    assert "session_token" in data
    assert data["user"]["email"] == "idp-user@example.com"
    assert data["user"]["name"] == "IdP User"


# Test 27: SAMLService - Process IdP-initiated response without InResponseTo
@patch("app.services.saml_service.OneLogin_Saml2_Auth")
def test_saml_service_process_idp_initiated_response(
    mock_saml_auth: MagicMock,
    saml_provider: SAMLProvider,
) -> None:
    """Test processing IdP-initiated SAML Response (no InResponseTo validation)."""
    service = SAMLService()

    # Mock OneLogin SAML Auth for IdP-initiated flow
    mock_auth_instance = MagicMock()
    mock_auth_instance.is_authenticated.return_value = True
    mock_auth_instance.get_errors.return_value = []
    mock_auth_instance.get_attributes.return_value = {
        "email": ["unsolicited@example.com"],
        "displayName": ["Unsolicited User"],
    }
    mock_auth_instance.get_nameid.return_value = "unsolicited@example.com"
    mock_saml_auth.return_value = mock_auth_instance

    # Process IdP-initiated SAML response
    saml_response = "base64-encoded-saml-response"
    result = service.process_saml_response(
        saml_response=saml_response,
        provider=saml_provider,
    )

    assert result["authenticated"] is True
    assert result["nameid"] == "unsolicited@example.com"


# Test 28: POST /api/auth/saml/acs - IdP-initiated with provider lookup by issuer
@patch("app.services.saml_service.OneLogin_Saml2_Auth")
def test_saml_acs_idp_initiated_provider_lookup(
    mock_saml_auth: MagicMock,
    db_session: Session,
    saml_provider: SAMLProvider,
) -> None:
    """Test IdP-initiated SSO with provider lookup by SAML issuer."""
    # Mock OneLogin SAML Auth with issuer
    mock_auth_instance = MagicMock()
    mock_auth_instance.is_authenticated.return_value = True
    mock_auth_instance.get_attributes.return_value = {
        "email": ["lookup-user@example.com"],
        "displayName": ["Lookup User"],
    }
    mock_auth_instance.get_nameid.return_value = "lookup-user@example.com"
    mock_auth_instance.get_errors.return_value = []

    mock_saml_auth.return_value = mock_auth_instance

    saml_response = base64.b64encode(b"<saml-response>").decode("utf-8")

    with patch(
        "app.services.saml_service.SAMLService.extract_issuer_from_response",
        return_value=saml_provider.entity_id,
    ):
        response = client.post(
            "/api/auth/saml/acs",
            data={
                "SAMLResponse": saml_response,
                # No RelayState
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["user"]["email"] == "lookup-user@example.com"


# Test 29: POST /api/auth/saml/acs - IdP-initiated with unknown issuer
@patch("app.services.saml_service.OneLogin_Saml2_Auth")
def test_saml_acs_idp_initiated_unknown_issuer(
    mock_saml_auth: MagicMock,
    db_session: Session,
) -> None:
    """Test IdP-initiated SSO with unknown SAML issuer (no matching provider)."""
    saml_response = base64.b64encode(b"<saml-response>").decode("utf-8")

    with patch(
        "app.services.saml_service.SAMLService.extract_issuer_from_response",
        return_value="https://unknown-idp.example.com/metadata",
    ):
        response = client.post(
            "/api/auth/saml/acs",
            data={
                "SAMLResponse": saml_response,
                # No RelayState
            },
        )

    assert response.status_code == 404
    assert "provider" in response.json()["detail"].lower()


# Test 30: SAMLService - Security validation for IdP-initiated flow
@patch("app.services.saml_service.OneLogin_Saml2_Auth")
def test_saml_idp_initiated_security_validation(
    mock_saml_auth: MagicMock,
    saml_provider: SAMLProvider,
) -> None:
    """Test that IdP-initiated responses retain full security validation."""
    service = SAMLService()

    # Mock validation failure (invalid signature)
    mock_auth_instance = MagicMock()
    mock_auth_instance.is_authenticated.return_value = False
    mock_auth_instance.get_errors.return_value = ["invalid_signature"]
    mock_auth_instance.get_last_error_reason.return_value = "Invalid signature"
    mock_saml_auth.return_value = mock_auth_instance

    # Should raise ValueError for invalid signature
    with pytest.raises(ValueError) as exc_info:
        service.process_saml_response(
            saml_response="invalid-response",
            provider=saml_provider,
        )
    assert "authentication failed" in str(exc_info.value).lower()


# Test 31: POST /api/auth/saml/acs - IdP-initiated with default landing page redirect
@patch("app.services.saml_service.OneLogin_Saml2_Auth")
def test_saml_acs_idp_initiated_default_redirect(
    mock_saml_auth: MagicMock,
    db_session: Session,
    saml_provider: SAMLProvider,
) -> None:
    """Test IdP-initiated SSO returns default landing page URL."""
    # Mock OneLogin SAML Auth
    mock_auth_instance = MagicMock()
    mock_auth_instance.is_authenticated.return_value = True
    mock_auth_instance.get_attributes.return_value = {
        "email": ["redirect-user@example.com"],
        "displayName": ["Redirect User"],
    }
    mock_auth_instance.get_nameid.return_value = "redirect-user@example.com"
    mock_auth_instance.get_errors.return_value = []

    mock_saml_auth.return_value = mock_auth_instance

    saml_response = base64.b64encode(b"<saml-response>").decode("utf-8")

    with patch(
        "app.services.saml_service.SAMLService.extract_issuer_from_response",
        return_value=saml_provider.entity_id,
    ):
        response = client.post(
            "/api/auth/saml/acs",
            data={
                "SAMLResponse": saml_response,
                # No RelayState - should use default redirect
            },
        )

    assert response.status_code == 200
    data = response.json()

    # Check that response includes redirect_url for IdP-initiated flow
    assert "redirect_url" in data
    assert data["redirect_url"] == "/dashboard"  # Default landing page
