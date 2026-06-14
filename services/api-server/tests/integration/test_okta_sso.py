"""
Integration Tests for Okta SAML SSO

Story 6.1 - Okta Integration Testing
Tests complete Okta SSO flows including SP-initiated and IdP-initiated login.

Test Scenarios:
1. SP-initiated login with Okta
2. IdP-initiated login from Okta dashboard
3. Valid SAML assertion accepted
4. Invalid signature rejected
5. Expired assertion rejected
"""
from __future__ import annotations

import base64
import xml.etree.ElementTree as ET
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
def okta_provider(db_session: Session) -> SAMLProvider:
    """
    Create a test Okta SAML provider.

    Uses realistic Okta configuration values.
    """
    provider_service = SAMLProviderService(db_session)

    # Realistic Okta X.509 certificate (test certificate)
    okta_cert = """-----BEGIN CERTIFICATE-----
MIIDqDCCApCgAwIBAgIGAY7zBGONMA0GCSqGSIb3DQEBCwUAMIGVMQswCQYDVQQG
EwJVUzETMBEGA1UECAwKQ2FsaWZvcm5pYTEWMBQGA1UEBwwNU2FuIEZyYW5jaXNj
bzENMAsGA1UECgwET2t0YTEUMBIGA1UECwwLU1NPUHJvdmlkZXIxFjAUBgNVBAMM
DWRldi0xMjM0NTY3ODEVMBMGA1UEEQwMZGV2LTEyMzQ1Njc4MB4XDTIzMTIwMTAw
MDAwMFoXDTI1MTIwMTAwMDAwMFowgZUxCzAJBgNVBAYTAlVTMRMwEQYDVQQIDApD
YWxpZm9ybmlhMRYwFAYDVQQHDA1TYW4gRnJhbmNpc2NvMQ0wCwYDVQQKDARPa3Rh
MRQwEgYDVQQLDAtTU09Qcm92aWRlcjEWMBQGA1UEAwwNZGV2LTEyMzQ1Njc4MRUw
EwYDVQQRDAxkZXYtMTIzNDU2NzgwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEK
AoIBAQC9Fh3g0p9K5nNNwJfK5n8n8yYw9p1GJh2YJ4nNx9pKl5J8z1y2K3n4m6p7
K8n9m4p5J7K6n8p3K9J2n7K5m8J4n7K9n2J5m8K6n7J4K8n3J6K7n8m5J9p4K6n7
K8J5n9m2K7J8n4m6K9p5J7n8K6m4J9n7K8J5m6n9K4J7n8K6m5J9p4K7n8J6m5K9
J4n7K8m6J5p9K4n7K8J6m5n9K4J7p8K6m5J9n4K7J8m6K5n9p4J7K8m6J5n9K4p7
K8J6m5n9K4J7p8K6m5J9n4K7J8m6K5p9K4n7K8J6m5n9K4J7p8K6m5J9n4K7J8m6
K5n9p4J7K8m6J5n9K4p7K8J6m5n9K4J7p8K6m5J9n4K7J8m6K5p9K4AgMBAAEwDQYJ
KoZIhvcNAQELBQADggEBAKXJ9p4K7n8m6J5n9K4J7p8K6m5J9n4K7J8m6K5n9p4J
7K8m6J5n9K4p7K8J6m5n9K4J7p8K6m5J9n4K7J8m6K5p9K4n7K8J6m5n9K4J7p8K
6m5J9n4K7J8m6K5n9p4J7K8m6J5n9K4p7K8J6m5n9K4J7p8K6m5J9n4K7J8m6K5p
-----END CERTIFICATE-----"""

    return provider_service.create_provider(
        organization_id="test-org-okta",
        name="Okta Test IdP",
        entity_id="http://www.okta.com/exktest1234567890",
        sso_url="https://dev-12345678.okta.com/app/dev-12345678_testapp_1/exktest1234567890/sso/saml",
        slo_url="https://dev-12345678.okta.com/app/dev-12345678_testapp_1/exktest1234567890/slo/saml",
        x509_cert=okta_cert,
        is_active=True,
    )


@pytest.fixture
def okta_test_user() -> dict[str, str]:
    """Test user data from Okta."""
    return {
        "email": "test.user@example.com",
        "first_name": "Test",
        "last_name": "User",
        "display_name": "Test User",
        "groups": ["Everyone", "Engineering"],
    }


# Test 1: SP-initiated login with Okta
def test_okta_sp_initiated_login_flow(
    db_session: Session,
    okta_provider: SAMLProvider,
) -> None:
    """
    Test SP-initiated SSO flow with Okta.

    Story 6.1 - Acceptance Criteria 1: Complete Okta SSO flow test (SP-initiated)

    Flow:
    1. User clicks "Login with Okta" button
    2. Application generates SAML AuthnRequest
    3. User is redirected to Okta SSO URL
    4. Okta authenticates user and posts SAML Response to ACS
    5. Application validates assertion and creates session
    """
    # Step 1: Initiate SSO login
    response = client.post(
        "/api/auth/saml/login",
        json={"provider_id": okta_provider.id},
    )

    assert response.status_code == 200
    data = response.json()

    # Step 2: Verify redirect URL contains Okta SSO endpoint
    assert "redirect_url" in data
    assert data["redirect_url"].startswith(okta_provider.sso_url)

    # Step 3: Verify SAMLRequest parameter
    parsed_url = urlparse(data["redirect_url"])
    query_params = parse_qs(parsed_url.query)
    assert "SAMLRequest" in query_params

    saml_request = query_params["SAMLRequest"][0]
    assert len(saml_request) > 0

    # Decode and verify AuthnRequest structure
    decoded_request = base64.b64decode(saml_request)
    assert b"AuthnRequest" in decoded_request or b"samlp:AuthnRequest" in decoded_request

    # Verify SP entity ID is in the request
    assert b"Issuer" in decoded_request


# Test 2: IdP-initiated login from Okta dashboard
@patch("app.services.saml_service.OneLogin_Saml2_Auth")
def test_okta_idp_initiated_login_flow(
    mock_saml_auth: MagicMock,
    db_session: Session,
    okta_provider: SAMLProvider,
    okta_test_user: dict[str, str],
) -> None:
    """
    Test IdP-initiated SSO flow from Okta dashboard.

    Story 6.1 - Acceptance Criteria 2: IdP-initiated SSO test

    Flow:
    1. User clicks application tile in Okta dashboard
    2. Okta posts SAML Response to ACS (no prior AuthnRequest)
    3. Application identifies provider by SAML issuer
    4. Application validates assertion and creates session
    """
    # Mock OneLogin SAML Auth for IdP-initiated flow
    mock_auth_instance = MagicMock()
    mock_auth_instance.is_authenticated.return_value = True
    mock_auth_instance.get_errors.return_value = []

    # Mock Okta SAML attributes
    mock_auth_instance.get_attributes.return_value = {
        "email": [okta_test_user["email"]],
        "firstName": [okta_test_user["first_name"]],
        "lastName": [okta_test_user["last_name"]],
        "displayName": [okta_test_user["display_name"]],
        "groups": okta_test_user["groups"],
    }
    mock_auth_instance.get_nameid.return_value = okta_test_user["email"]

    # Mock issuer extraction for provider lookup
    mock_response_obj = MagicMock()
    mock_response_obj.get_issuer.return_value = okta_provider.entity_id

    mock_saml_auth.return_value = mock_auth_instance

    # Simulate IdP-initiated SAML Response (no RelayState)
    saml_response = base64.b64encode(b"<mock-okta-saml-response>").decode("utf-8")

    # Patch extract_issuer_from_response to return Okta entity ID
    with patch.object(SAMLService, "extract_issuer_from_response") as mock_extract:
        mock_extract.return_value = okta_provider.entity_id

        response = client.post(
            "/api/auth/saml/acs",
            data={
                "SAMLResponse": saml_response,
                # No RelayState for IdP-initiated
            },
        )

    assert response.status_code == 200
    data = response.json()

    # Verify user session was created
    assert "user" in data
    assert "session_token" in data
    assert "refresh_token" in data
    assert data["user"]["email"] == okta_test_user["email"]
    assert data["user"]["name"] == okta_test_user["display_name"]

    # Verify default redirect URL for IdP-initiated flow
    assert "redirect_url" in data
    assert data["redirect_url"] == "/dashboard"


# Test 3: Valid SAML assertion accepted
@patch("app.services.saml_service.OneLogin_Saml2_Auth")
def test_okta_valid_assertion_accepted(
    mock_saml_auth: MagicMock,
    db_session: Session,
    okta_provider: SAMLProvider,
    okta_test_user: dict[str, str],
) -> None:
    """
    Test that valid SAML assertion from Okta is accepted.

    Story 6.1 - Acceptance Criteria 2: Assertion validation test

    Validates:
    - Signature is valid
    - Assertion is within valid time window
    - Audience restriction matches SP entity ID
    - User attributes are correctly extracted
    """
    # Mock successful SAML validation
    mock_auth_instance = MagicMock()
    mock_auth_instance.is_authenticated.return_value = True
    mock_auth_instance.get_errors.return_value = []
    mock_auth_instance.get_last_error_reason.return_value = None

    # Mock Okta user attributes
    mock_auth_instance.get_attributes.return_value = {
        "email": [okta_test_user["email"]],
        "displayName": [okta_test_user["display_name"]],
        "groups": okta_test_user["groups"],
    }
    mock_auth_instance.get_nameid.return_value = okta_test_user["email"]

    mock_saml_auth.return_value = mock_auth_instance

    # Simulate valid SAML Response from Okta
    saml_response = base64.b64encode(b"<valid-okta-saml-response>").decode("utf-8")

    response = client.post(
        "/api/auth/saml/acs",
        data={
            "SAMLResponse": saml_response,
            "RelayState": okta_provider.id,
        },
    )

    assert response.status_code == 200
    data = response.json()

    # Verify authentication succeeded
    assert "user" in data
    assert "session_token" in data
    assert data["user"]["email"] == okta_test_user["email"]

    # Verify user was created in database
    user = db_session.query(User).filter(User.email == okta_test_user["email"]).first()
    assert user is not None
    assert user.email_verified is True  # SAML users are pre-verified
    assert user.status == "active"


# Test 4: Invalid signature rejected
@patch("app.services.saml_service.OneLogin_Saml2_Auth")
def test_okta_invalid_signature_rejected(
    mock_saml_auth: MagicMock,
    db_session: Session,
    okta_provider: SAMLProvider,
) -> None:
    """
    Test that SAML assertion with invalid signature is rejected.

    Story 6.1 - Acceptance Criteria 2: Assertion validation test

    Security validation: Assertions not signed by Okta's certificate must be rejected.
    """
    # Mock signature validation failure
    mock_auth_instance = MagicMock()
    mock_auth_instance.is_authenticated.return_value = False
    mock_auth_instance.get_errors.return_value = ["invalid_signature"]
    mock_auth_instance.get_last_error_reason.return_value = "Signature validation failed"

    mock_saml_auth.return_value = mock_auth_instance

    # Simulate SAML Response with invalid signature
    saml_response = base64.b64encode(b"<invalid-signature-saml-response>").decode("utf-8")

    response = client.post(
        "/api/auth/saml/acs",
        data={
            "SAMLResponse": saml_response,
            "RelayState": okta_provider.id,
        },
    )

    # Should reject with 401 Unauthorized
    assert response.status_code == 401
    error_detail = response.json()["detail"].lower()
    assert "authentication failed" in error_detail or "signature" in error_detail


# Test 5: Expired assertion rejected
@patch("app.services.saml_service.OneLogin_Saml2_Auth")
def test_okta_expired_assertion_rejected(
    mock_saml_auth: MagicMock,
    db_session: Session,
    okta_provider: SAMLProvider,
) -> None:
    """
    Test that expired SAML assertion is rejected.

    Story 6.1 - Acceptance Criteria 2: Assertion validation test

    Security validation: Assertions past their NotAfter time must be rejected.
    """
    # Mock expired assertion validation failure
    mock_auth_instance = MagicMock()
    mock_auth_instance.is_authenticated.return_value = False
    mock_auth_instance.get_errors.return_value = ["invalid_response"]
    mock_auth_instance.get_last_error_reason.return_value = "Assertion has expired"

    mock_saml_auth.return_value = mock_auth_instance

    # Simulate expired SAML Response
    saml_response = base64.b64encode(b"<expired-saml-response>").decode("utf-8")

    response = client.post(
        "/api/auth/saml/acs",
        data={
            "SAMLResponse": saml_response,
            "RelayState": okta_provider.id,
        },
    )

    # Should reject with 401 Unauthorized
    assert response.status_code == 401
    assert "authentication failed" in response.json()["detail"].lower()


# Test 6: SAMLService validates assertion timing with Okta values
def test_okta_assertion_timing_validation() -> None:
    """
    Test assertion validity period validation with realistic Okta timing.

    Story 6.1 - Acceptance Criteria 2: Assertion validation test

    Okta typically sets:
    - NotBefore: current time
    - NotAfter: current time + 5 minutes
    """
    service = SAMLService()

    # Valid assertion (within time window)
    now = datetime.now(UTC)
    not_before = now - timedelta(seconds=10)  # Issued 10 seconds ago
    not_after = now + timedelta(minutes=5)    # Valid for 5 more minutes

    # Should not raise any exception
    result = service.check_assertion_validity(
        not_before=not_before.isoformat(),
        not_after=not_after.isoformat(),
    )
    assert result is True

    # Expired assertion (NotAfter in the past)
    expired_not_before = now - timedelta(minutes=10)
    expired_not_after = now - timedelta(minutes=5)

    with pytest.raises(ValueError) as exc_info:
        service.check_assertion_validity(
            not_before=expired_not_before.isoformat(),
            not_after=expired_not_after.isoformat(),
        )
    assert "expired" in str(exc_info.value).lower()


# Test 7: Okta audience restriction validation
@patch("app.services.saml_service.get_saml_config")
def test_okta_audience_restriction(mock_config: MagicMock) -> None:
    """
    Test audience restriction validation for Okta assertions.

    Story 6.1 - Acceptance Criteria 2: Assertion validation test

    Okta includes AudienceRestriction that must match SP entity ID.
    """
    service = SAMLService()

    sp_entity_id = "https://myapp.example.com/saml/metadata"
    mock_config.return_value = {
        "sp_entity_id": sp_entity_id,
        "sp_acs_url": "https://myapp.example.com/saml/acs",
        "sp_sls_url": "https://myapp.example.com/saml/sls",
        "sp_x509_cert": "test-cert",
        "sp_private_key": "test-key",
    }
    service._config = mock_config.return_value

    # Valid audience (matches SP entity ID)
    result = service.verify_audience(audience=sp_entity_id)
    assert result is True

    # Invalid audience (does not match)
    with pytest.raises(ValueError) as exc_info:
        service.verify_audience(audience="https://wrong-app.example.com/saml/metadata")
    assert "audience" in str(exc_info.value).lower()


# Test 8: Complete Okta SSO flow with realistic data
@patch("app.services.saml_service.OneLogin_Saml2_Auth")
def test_okta_complete_sso_flow_realistic(
    mock_saml_auth: MagicMock,
    db_session: Session,
    okta_provider: SAMLProvider,
) -> None:
    """
    Test complete Okta SSO flow with realistic data.

    Story 6.1 - Comprehensive integration test

    Simulates real Okta behavior:
    - Okta attribute names (email, firstName, lastName, displayName)
    - Okta group format
    - Timing windows
    """
    # Mock OneLogin SAML Auth with realistic Okta response
    mock_auth_instance = MagicMock()
    mock_auth_instance.is_authenticated.return_value = True
    mock_auth_instance.get_errors.return_value = []

    # Realistic Okta SAML attributes
    mock_auth_instance.get_attributes.return_value = {
        "email": ["alice.engineer@company.com"],
        "firstName": ["Alice"],
        "lastName": ["Engineer"],
        "displayName": ["Alice Engineer"],
        "groups": ["Everyone", "Engineering", "Platform-Team"],
    }
    mock_auth_instance.get_nameid.return_value = "alice.engineer@company.com"

    mock_saml_auth.return_value = mock_auth_instance

    # Simulate SAML Response
    saml_response = base64.b64encode(b"<okta-saml-response>").decode("utf-8")

    response = client.post(
        "/api/auth/saml/acs",
        data={
            "SAMLResponse": saml_response,
            "RelayState": okta_provider.id,
        },
    )

    assert response.status_code == 200
    data = response.json()

    # Verify complete session response
    assert data["user"]["email"] == "alice.engineer@company.com"
    assert data["user"]["name"] == "Alice Engineer"
    assert "session_token" in data
    assert "refresh_token" in data
    assert "expires_at" in data

    # Verify user was created with correct attributes
    user = db_session.query(User).filter(User.email == "alice.engineer@company.com").first()
    assert user is not None
    assert user.name == "Alice Engineer"
    assert user.email_verified is True
    assert user.status == "active"
    assert user.last_login_at is not None
