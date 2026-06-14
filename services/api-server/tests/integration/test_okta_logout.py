"""
Integration Tests for Okta Single Logout (SLO)

Story 6.1 - Okta Integration Testing
Tests SAML Single Logout flow with Okta.

Test Scenarios:
8. Single Logout clears session
9. LogoutRequest generation
10. LogoutResponse validation
11. Session revocation
12. Error handling during logout
"""
from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import SAMLProvider, Session as DBSession, User
from app.main import app
from app.services.saml_provider_service import SAMLProviderService
from app.services.saml_service import SAMLService
from app.services.session_service import SessionService

client = TestClient(app)


@pytest.fixture
def okta_provider(db_session: Session) -> SAMLProvider:
    """Create Okta SAML provider for SLO tests."""
    provider_service = SAMLProviderService(db_session)

    okta_cert = """-----BEGIN CERTIFICATE-----
MIIDqDCCApCgAwIBAgIGAY7zBGONMA0GCSqGSIb3DQEBCwUAMIGVMQswCQYDVQQG
EwJVUzETMBEGA1UECAwKQ2FsaWZvcm5pYTEWMBQGA1UEBwwNU2FuIEZyYW5jaXNj
bzENMAsGA1UECgwET2t0YTEUMBIGA1UECwwLU1NPUHJvdmlkZXIxFjAUBgNVBAMM
DWRldi0xMjM0NTY3ODEVMBMGA1UEEQwMZGV2LTEyMzQ1Njc4MB4XDTIzMTIwMTAw
MDAwMFoXDTI1MTIwMTAwMDAwMFowgZUxCzAJBgNVBAYTAlVTMRMwEQYDVQQIDApD
YWxpZm9ybmlhMRYwFAYDVQQHDA1TYW4gRnJhbmNpc2NvMQ0wCwYDVQQKDARPa3Rh
-----END CERTIFICATE-----"""

    return provider_service.create_provider(
        organization_id="test-org-okta-slo",
        name="Okta SLO Test IdP",
        entity_id="http://www.okta.com/exkslo1234567890",
        sso_url="https://dev-12345678.okta.com/app/testapp/sso/saml",
        slo_url="https://dev-12345678.okta.com/app/testapp/slo/saml",
        x509_cert=okta_cert,
        is_active=True,
    )


@pytest.fixture
def authenticated_user(db_session: Session) -> tuple[User, str, str]:
    """
    Create authenticated user with active session.

    Returns:
        Tuple of (user, session_id, nameid)
    """
    # Create user
    user = User(
        email="logout-test@example.com",
        name="Logout Test User",
        password_hash="dummy-hash",
        email_verified=True,
        status="active",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    # Create session
    session_service = SessionService(db_session)
    session_data = session_service.create_session(
        user_id=user.id,
        email=user.email,
        roles=["user"],
        ttl_hours=24,
    )

    # Extract session ID from token
    import jwt
    from app.core.config import get_settings

    settings = get_settings()
    claims = jwt.decode(
        session_data["access_token"],
        settings.auth_jwt_secret,
        algorithms=["HS256"],
    )
    session_id = claims["jti"]

    return user, session_id, user.email


# Test 8: Single Logout clears session
def test_okta_single_logout_clears_session(
    db_session: Session,
    okta_provider: SAMLProvider,
    authenticated_user: tuple[User, str, str],
) -> None:
    """
    Test that Single Logout properly revokes the session.

    Story 6.1 - Acceptance Criteria 5: Single Logout test

    When user initiates logout:
    1. Session is revoked in database
    2. LogoutRequest is generated
    3. User is redirected to Okta for IdP logout
    """
    user, session_id, nameid = authenticated_user

    # Verify session is active before logout
    session_service = SessionService(db_session)
    session = session_service.get_session(session_id)
    assert session is not None
    assert session.revoked_at is None

    # Initiate logout
    response = client.post(
        "/api/auth/saml/logout",
        json={
            "provider_id": okta_provider.id,
            "session_id": session_id,
            "nameid": nameid,
        },
    )

    assert response.status_code == 200
    data = response.json()

    # Verify redirect URL is returned
    assert "redirect_url" in data
    assert data["redirect_url"].startswith(okta_provider.slo_url)

    # Verify session was revoked
    db_session.refresh(session)
    assert session.revoked_at is not None

    # Verify session cannot be used anymore
    assert session_service.validate_session(session_id) is False


# Test 9: LogoutRequest generation for Okta
def test_okta_logout_request_generation(
    okta_provider: SAMLProvider,
) -> None:
    """
    Test SAML LogoutRequest generation for Okta.

    Story 6.1 - Acceptance Criteria 5: Single Logout test

    LogoutRequest should contain:
    - SAML LogoutRequest element
    - NameID from original login
    - SessionIndex (if available)
    - Signature
    """
    service = SAMLService()

    session_id = "test-session-123"
    nameid = "test-user@example.com"

    # Generate LogoutRequest
    logout_data = service.initiate_logout(
        provider=okta_provider,
        session_id=session_id,
        nameid=nameid,
    )

    assert "redirect_url" in logout_data
    assert "saml_request" in logout_data

    # Verify redirect URL points to Okta SLO endpoint
    assert logout_data["redirect_url"].startswith(okta_provider.slo_url)

    # Parse URL to extract SAMLRequest
    parsed_url = urlparse(logout_data["redirect_url"])
    query_params = parse_qs(parsed_url.query)
    assert "SAMLRequest" in query_params

    # Verify SAMLRequest is base64 encoded
    saml_request = query_params["SAMLRequest"][0]
    assert len(saml_request) > 0

    # Decode and verify LogoutRequest structure
    decoded_request = base64.b64decode(saml_request)
    assert b"LogoutRequest" in decoded_request or b"samlp:LogoutRequest" in decoded_request
    assert nameid.encode() in decoded_request or b"NameID" in decoded_request


# Test 10: LogoutResponse validation from Okta
@patch("app.services.saml_service.OneLogin_Saml2_Auth")
def test_okta_logout_response_validation(
    mock_saml_auth: MagicMock,
    db_session: Session,
    okta_provider: SAMLProvider,
) -> None:
    """
    Test handling of SAML LogoutResponse from Okta.

    Story 6.1 - Acceptance Criteria 5: Single Logout test

    After processing LogoutRequest, Okta sends LogoutResponse:
    - Validate LogoutResponse signature
    - Confirm successful logout status
    - Complete local logout flow
    """
    # Mock successful LogoutResponse processing
    mock_auth_instance = MagicMock()
    mock_auth_instance.get_errors.return_value = []
    mock_auth_instance.get_last_error_reason.return_value = None
    mock_saml_auth.return_value = mock_auth_instance

    # Simulate SAML LogoutResponse from Okta
    saml_response = base64.b64encode(b"<okta-logout-response>").decode("utf-8")

    response = client.post(
        "/api/auth/saml/sls",
        data={
            "SAMLResponse": saml_response,
            "RelayState": okta_provider.id,
        },
    )

    assert response.status_code == 200
    data = response.json()

    # Verify successful logout
    assert data["success"] is True
    assert "message" in data


# Test 11: LogoutResponse with error from Okta
@patch("app.services.saml_service.OneLogin_Saml2_Auth")
def test_okta_logout_response_error(
    mock_saml_auth: MagicMock,
    db_session: Session,
    okta_provider: SAMLProvider,
) -> None:
    """
    Test handling of SAML LogoutResponse errors from Okta.

    Story 6.1 - Error scenario testing

    If Okta logout fails:
    - LogoutResponse contains error status
    - Application should handle error gracefully
    """
    # Mock LogoutResponse with errors
    mock_auth_instance = MagicMock()
    mock_auth_instance.get_errors.return_value = ["logout_failed"]
    mock_auth_instance.get_last_error_reason.return_value = "Logout failed at IdP"
    mock_saml_auth.return_value = mock_auth_instance

    saml_response = base64.b64encode(b"<okta-logout-error-response>").decode("utf-8")

    response = client.post(
        "/api/auth/saml/sls",
        data={
            "SAMLResponse": saml_response,
            "RelayState": okta_provider.id,
        },
    )

    # Should return error
    assert response.status_code == 400
    assert "logout" in response.json()["detail"].lower()


# Test 12: Logout without SLO URL configured
def test_okta_logout_without_slo_url(
    db_session: Session,
    authenticated_user: tuple[User, str, str],
) -> None:
    """
    Test logout fails gracefully when Okta provider has no SLO URL.

    Story 6.1 - Error scenario testing

    Some Okta configurations may not have SLO enabled.
    """
    # Create provider without SLO URL
    provider_service = SAMLProviderService(db_session)
    provider_no_slo = provider_service.create_provider(
        organization_id="test-org-okta-no-slo",
        name="Okta No SLO IdP",
        entity_id="http://www.okta.com/exknoslo",
        sso_url="https://dev-12345678.okta.com/app/testapp/sso/saml",
        slo_url=None,  # No SLO URL
        x509_cert="-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----",
        is_active=True,
    )

    user, session_id, nameid = authenticated_user

    # Attempt logout
    response = client.post(
        "/api/auth/saml/logout",
        json={
            "provider_id": provider_no_slo.id,
            "session_id": session_id,
            "nameid": nameid,
        },
    )

    # Should return error
    assert response.status_code == 400
    assert "slo" in response.json()["detail"].lower()


# Test 13: Logout with invalid session
def test_okta_logout_invalid_session(
    db_session: Session,
    okta_provider: SAMLProvider,
) -> None:
    """
    Test logout fails when session does not exist.

    Story 6.1 - Error scenario testing
    """
    response = client.post(
        "/api/auth/saml/logout",
        json={
            "provider_id": okta_provider.id,
            "session_id": "non-existent-session-id",
            "nameid": "test@example.com",
        },
    )

    # Should return 404 for non-existent session
    assert response.status_code == 404
    assert "session" in response.json()["detail"].lower()


# Test 14: Logout with invalid provider
def test_okta_logout_invalid_provider(
    db_session: Session,
    authenticated_user: tuple[User, str, str],
) -> None:
    """
    Test logout fails when provider does not exist.

    Story 6.1 - Error scenario testing
    """
    user, session_id, nameid = authenticated_user

    response = client.post(
        "/api/auth/saml/logout",
        json={
            "provider_id": "non-existent-provider-id",
            "session_id": session_id,
            "nameid": nameid,
        },
    )

    # Should return 404 for non-existent provider
    assert response.status_code == 404
    assert "provider" in response.json()["detail"].lower()


# Test 15: Complete SLO flow with Okta
@patch("app.services.saml_service.OneLogin_Saml2_Auth")
def test_okta_complete_slo_flow(
    mock_saml_auth: MagicMock,
    db_session: Session,
    okta_provider: SAMLProvider,
    authenticated_user: tuple[User, str, str],
) -> None:
    """
    Test complete Single Logout flow with Okta.

    Story 6.1 - Acceptance Criteria 5: Single Logout test

    Complete flow:
    1. User initiates logout
    2. Application revokes local session
    3. Application generates LogoutRequest
    4. User is redirected to Okta
    5. Okta processes logout and sends LogoutResponse
    6. Application validates LogoutResponse
    7. Logout completes successfully
    """
    user, session_id, nameid = authenticated_user

    # Step 1-3: Initiate logout
    response = client.post(
        "/api/auth/saml/logout",
        json={
            "provider_id": okta_provider.id,
            "session_id": session_id,
            "nameid": nameid,
        },
    )

    assert response.status_code == 200
    logout_init_data = response.json()

    # Verify LogoutRequest redirect URL
    assert logout_init_data["redirect_url"].startswith(okta_provider.slo_url)

    # Verify session was revoked
    session_service = SessionService(db_session)
    session = session_service.get_session(session_id)
    assert session.revoked_at is not None

    # Step 4-6: Okta processes logout and sends response
    mock_auth_instance = MagicMock()
    mock_auth_instance.get_errors.return_value = []
    mock_auth_instance.get_last_error_reason.return_value = None
    mock_saml_auth.return_value = mock_auth_instance

    saml_response = base64.b64encode(b"<okta-logout-response-success>").decode("utf-8")

    response = client.post(
        "/api/auth/saml/sls",
        data={
            "SAMLResponse": saml_response,
            "RelayState": okta_provider.id,
        },
    )

    # Step 7: Verify logout completed
    assert response.status_code == 200
    sls_data = response.json()
    assert sls_data["success"] is True


# Test 16: Session management after logout
def test_okta_session_management_after_logout(
    db_session: Session,
    okta_provider: SAMLProvider,
    authenticated_user: tuple[User, str, str],
) -> None:
    """
    Test session state after logout.

    Story 6.1 - Acceptance Criteria 7: Session management

    After logout:
    - Session is marked as revoked
    - Session cannot be validated
    - New login creates new session
    """
    user, session_id, nameid = authenticated_user
    session_service = SessionService(db_session)

    # Verify session is valid before logout
    assert session_service.validate_session(session_id) is True

    # Perform logout
    response = client.post(
        "/api/auth/saml/logout",
        json={
            "provider_id": okta_provider.id,
            "session_id": session_id,
            "nameid": nameid,
        },
    )

    assert response.status_code == 200

    # Verify session is invalid after logout
    assert session_service.validate_session(session_id) is False

    # Verify session is marked as revoked
    session = session_service.get_session(session_id)
    assert session.revoked_at is not None

    # Verify new session can be created for same user
    new_session_data = session_service.create_session(
        user_id=user.id,
        email=user.email,
        roles=["user"],
        ttl_hours=24,
    )

    # Extract new session ID
    import jwt
    from app.core.config import get_settings

    settings = get_settings()
    claims = jwt.decode(
        new_session_data["access_token"],
        settings.auth_jwt_secret,
        algorithms=["HS256"],
    )
    new_session_id = claims["jti"]

    # Verify new session is different from old session
    assert new_session_id != session_id

    # Verify new session is valid
    assert session_service.validate_session(new_session_id) is True


# Test 17: SAMLService logout methods
def test_okta_saml_service_logout_methods(
    okta_provider: SAMLProvider,
) -> None:
    """
    Test SAMLService logout-related methods.

    Story 6.1 - Unit testing for SLO components
    """
    service = SAMLService()

    # Test initiate_logout
    logout_data = service.initiate_logout(
        provider=okta_provider,
        session_id="test-session",
        nameid="test@example.com",
    )

    assert "redirect_url" in logout_data
    assert "saml_request" in logout_data
    assert logout_data["redirect_url"].startswith(okta_provider.slo_url)

    # Verify SAMLRequest is properly formatted
    parsed_url = urlparse(logout_data["redirect_url"])
    query_params = parse_qs(parsed_url.query)
    assert "SAMLRequest" in query_params


# Test 18: Concurrent logout attempts
def test_okta_concurrent_logout_attempts(
    db_session: Session,
    okta_provider: SAMLProvider,
    authenticated_user: tuple[User, str, str],
) -> None:
    """
    Test handling of multiple logout attempts for same session.

    Story 6.1 - Edge case testing
    """
    user, session_id, nameid = authenticated_user

    # First logout attempt
    response1 = client.post(
        "/api/auth/saml/logout",
        json={
            "provider_id": okta_provider.id,
            "session_id": session_id,
            "nameid": nameid,
        },
    )

    assert response1.status_code == 200

    # Second logout attempt (session already revoked)
    response2 = client.post(
        "/api/auth/saml/logout",
        json={
            "provider_id": okta_provider.id,
            "session_id": session_id,
            "nameid": nameid,
        },
    )

    # Second attempt should fail (session already revoked)
    assert response2.status_code == 404
    assert "session" in response2.json()["detail"].lower()
