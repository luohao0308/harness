"""
Integration Tests for Okta User Provisioning

Story 6.1 - Okta Integration Testing
Tests Just-In-Time (JIT) user provisioning and role assignment from Okta groups.

Test Scenarios:
6. User provisioned on first login
7. Admin role assigned from Okta group
8. User attributes updated on subsequent login
9. External ID tracking
10. Multiple group membership handling
"""
from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import SAMLProvider, User, UserExternalId
from app.main import app
from app.services.saml_provider_service import SAMLProviderService
from app.services.user_provisioning_service import UserProvisioningService

client = TestClient(app)


@pytest.fixture
def okta_provider(db_session: Session) -> SAMLProvider:
    """Create Okta SAML provider for provisioning tests."""
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
        organization_id="test-org-okta-provisioning",
        name="Okta Provisioning Test IdP",
        entity_id="http://www.okta.com/exkprov1234567890",
        sso_url="https://dev-12345678.okta.com/app/testapp/sso/saml",
        slo_url="https://dev-12345678.okta.com/app/testapp/slo/saml",
        x509_cert=okta_cert,
        is_active=True,
    )


# Test 6: User provisioned on first login
@patch("app.services.saml_service.OneLogin_Saml2_Auth")
def test_okta_user_provisioned_on_first_login(
    mock_saml_auth: MagicMock,
    db_session: Session,
    okta_provider: SAMLProvider,
) -> None:
    """
    Test Just-In-Time (JIT) user provisioning on first Okta login.

    Story 6.1 - Acceptance Criteria 3: User provisioning verification

    When a user logs in via Okta for the first time:
    1. User account is automatically created
    2. Email is marked as verified
    3. User status is set to active
    4. User attributes are populated from SAML
    5. External ID mapping is created
    """
    new_user_email = "newuser@example.com"

    # Verify user does not exist yet
    existing_user = db_session.query(User).filter(User.email == new_user_email).first()
    assert existing_user is None

    # Mock Okta SAML authentication
    mock_auth_instance = MagicMock()
    mock_auth_instance.is_authenticated.return_value = True
    mock_auth_instance.get_errors.return_value = []
    mock_auth_instance.get_attributes.return_value = {
        "email": [new_user_email],
        "firstName": ["New"],
        "lastName": ["User"],
        "displayName": ["New User"],
        "groups": ["Everyone"],
    }
    mock_auth_instance.get_nameid.return_value = new_user_email
    mock_saml_auth.return_value = mock_auth_instance

    # Simulate first login via Okta
    saml_response = base64.b64encode(b"<okta-new-user-response>").decode("utf-8")

    response = client.post(
        "/api/auth/saml/acs",
        data={
            "SAMLResponse": saml_response,
            "RelayState": okta_provider.id,
        },
    )

    assert response.status_code == 200
    data = response.json()

    # Verify session was created
    assert "user" in data
    assert "session_token" in data
    assert data["user"]["email"] == new_user_email

    # Verify user was provisioned in database
    provisioned_user = db_session.query(User).filter(User.email == new_user_email).first()
    assert provisioned_user is not None
    assert provisioned_user.name == "New User"
    assert provisioned_user.email_verified is True
    assert provisioned_user.status == "active"
    assert provisioned_user.last_login_at is not None

    # Verify external ID mapping was created
    external_id = (
        db_session.query(UserExternalId)
        .filter(
            UserExternalId.user_id == provisioned_user.id,
            UserExternalId.provider == "saml",
            UserExternalId.external_entity_id == okta_provider.entity_id,
        )
        .first()
    )
    assert external_id is not None
    assert external_id.external_user_id == new_user_email


# Test 7: Admin role assigned from Okta group
@patch("app.services.saml_service.OneLogin_Saml2_Auth")
def test_okta_admin_role_from_group(
    mock_saml_auth: MagicMock,
    db_session: Session,
    okta_provider: SAMLProvider,
) -> None:
    """
    Test admin role assignment based on Okta group membership.

    Story 6.1 - Acceptance Criteria 4: Role assignment from groups

    When Okta sends a user with "admin" group:
    - User should be assigned admin role in session
    - Role is included in JWT claims
    """
    admin_user_email = "admin@example.com"

    # Mock Okta SAML authentication with admin group
    mock_auth_instance = MagicMock()
    mock_auth_instance.is_authenticated.return_value = True
    mock_auth_instance.get_errors.return_value = []
    mock_auth_instance.get_attributes.return_value = {
        "email": [admin_user_email],
        "firstName": ["Admin"],
        "lastName": ["User"],
        "displayName": ["Admin User"],
        "groups": ["Everyone", "admin", "Engineering"],  # Contains "admin" group
    }
    mock_auth_instance.get_nameid.return_value = admin_user_email
    mock_saml_auth.return_value = mock_auth_instance

    saml_response = base64.b64encode(b"<okta-admin-user-response>").decode("utf-8")

    response = client.post(
        "/api/auth/saml/acs",
        data={
            "SAMLResponse": saml_response,
            "RelayState": okta_provider.id,
        },
    )

    assert response.status_code == 200
    data = response.json()

    # Verify session token was created
    assert "session_token" in data

    # Decode JWT to verify admin role
    import jwt

    from app.core.config import get_settings

    settings = get_settings()
    token_claims = jwt.decode(
        data["session_token"],
        settings.auth_jwt_secret,
        algorithms=["HS256"],
    )

    # Verify admin role is in token
    assert "roles" in token_claims
    assert "admin" in token_claims["roles"]


# Test 8: User role from non-admin Okta group
@patch("app.services.saml_service.OneLogin_Saml2_Auth")
def test_okta_user_role_from_group(
    mock_saml_auth: MagicMock,
    db_session: Session,
    okta_provider: SAMLProvider,
) -> None:
    """
    Test default user role when admin group is not present.

    Story 6.1 - Acceptance Criteria 4: Role assignment from groups

    When Okta sends a user without "admin" group:
    - User should be assigned default "user" role
    """
    regular_user_email = "regularuser@example.com"

    # Mock Okta SAML authentication without admin group
    mock_auth_instance = MagicMock()
    mock_auth_instance.is_authenticated.return_value = True
    mock_auth_instance.get_errors.return_value = []
    mock_auth_instance.get_attributes.return_value = {
        "email": [regular_user_email],
        "firstName": ["Regular"],
        "lastName": ["User"],
        "displayName": ["Regular User"],
        "groups": ["Everyone", "Engineering"],  # No admin group
    }
    mock_auth_instance.get_nameid.return_value = regular_user_email
    mock_saml_auth.return_value = mock_auth_instance

    saml_response = base64.b64encode(b"<okta-regular-user-response>").decode("utf-8")

    response = client.post(
        "/api/auth/saml/acs",
        data={
            "SAMLResponse": saml_response,
            "RelayState": okta_provider.id,
        },
    )

    assert response.status_code == 200
    data = response.json()

    # Decode JWT to verify user role
    import jwt

    from app.core.config import get_settings

    settings = get_settings()
    token_claims = jwt.decode(
        data["session_token"],
        settings.auth_jwt_secret,
        algorithms=["HS256"],
    )

    # Verify user role is in token (not admin)
    assert "roles" in token_claims
    assert "user" in token_claims["roles"]
    assert "admin" not in token_claims["roles"]


# Test 9: User attributes updated on subsequent login
@patch("app.services.saml_service.OneLogin_Saml2_Auth")
def test_okta_user_updated_on_subsequent_login(
    mock_saml_auth: MagicMock,
    db_session: Session,
    okta_provider: SAMLProvider,
) -> None:
    """
    Test user attributes are updated on subsequent Okta logins.

    Story 6.1 - Acceptance Criteria 3: User provisioning verification

    When an existing user logs in again:
    1. User attributes are updated from SAML
    2. Last login timestamp is updated
    3. User is not duplicated
    """
    existing_email = "existing@example.com"

    # Create existing user with old data
    existing_user = User(
        email=existing_email,
        name="Old Name",
        password_hash="dummy-hash",
        email_verified=True,
        status="active",
    )
    db_session.add(existing_user)
    db_session.commit()
    db_session.refresh(existing_user)

    original_user_id = existing_user.id
    original_last_login = existing_user.last_login_at

    # Mock Okta SAML authentication with updated name
    mock_auth_instance = MagicMock()
    mock_auth_instance.is_authenticated.return_value = True
    mock_auth_instance.get_errors.return_value = []
    mock_auth_instance.get_attributes.return_value = {
        "email": [existing_email],
        "displayName": ["Updated Name"],  # Name changed in Okta
        "groups": ["Everyone"],
    }
    mock_auth_instance.get_nameid.return_value = existing_email
    mock_saml_auth.return_value = mock_auth_instance

    saml_response = base64.b64encode(b"<okta-existing-user-response>").decode("utf-8")

    response = client.post(
        "/api/auth/saml/acs",
        data={
            "SAMLResponse": saml_response,
            "RelayState": okta_provider.id,
        },
    )

    assert response.status_code == 200
    data = response.json()

    # Verify user ID is the same (not duplicated)
    assert data["user"]["id"] == original_user_id

    # Verify user name was updated
    db_session.refresh(existing_user)
    assert existing_user.name == "Updated Name"

    # Verify last login was updated
    assert existing_user.last_login_at is not None
    if original_last_login:
        assert existing_user.last_login_at > original_last_login

    # Verify only one user with this email exists
    user_count = db_session.query(User).filter(User.email == existing_email).count()
    assert user_count == 1


# Test 10: External ID tracking for Okta users
def test_okta_external_id_tracking(
    db_session: Session,
    okta_provider: SAMLProvider,
) -> None:
    """
    Test external ID mapping is created and maintained.

    Story 6.1 - Acceptance Criteria 3: User provisioning verification

    External IDs enable:
    - Tracking which users came from which IdP
    - Account linking across multiple IdPs
    - SAML subject ID persistence
    """
    provisioning_service = UserProvisioningService(db_session)

    # Simulate Okta SAML claims
    okta_claims = {
        "email": "tracked@example.com",
        "name": "Tracked User",
        "groups": ["Everyone"],
    }

    okta_subject_id = "00u123456789abcdefg"  # Okta user ID format

    # Provision user
    user = provisioning_service.provision_user_from_saml(
        saml_claims=okta_claims,
        idp_entity_id=okta_provider.entity_id,
        subject_id=okta_subject_id,
    )

    # Verify external ID was created
    external_id = (
        db_session.query(UserExternalId)
        .filter(
            UserExternalId.user_id == user.id,
            UserExternalId.provider == "saml",
        )
        .first()
    )

    assert external_id is not None
    assert external_id.external_entity_id == okta_provider.entity_id
    assert external_id.external_user_id == okta_subject_id

    # Provision same user again (simulating re-login)
    updated_user = provisioning_service.provision_user_from_saml(
        saml_claims=okta_claims,
        idp_entity_id=okta_provider.entity_id,
        subject_id=okta_subject_id,
    )

    # Verify user is the same
    assert updated_user.id == user.id

    # Verify external ID was not duplicated
    external_id_count = (
        db_session.query(UserExternalId)
        .filter(
            UserExternalId.user_id == user.id,
            UserExternalId.provider == "saml",
        )
        .count()
    )
    assert external_id_count == 1


# Test 11: Multiple Okta groups handling
def test_okta_multiple_groups_handling(db_session: Session) -> None:
    """
    Test handling of multiple Okta group memberships.

    Story 6.1 - Acceptance Criteria 4: Role assignment from groups

    Okta users can be members of multiple groups:
    - Everyone (default)
    - Engineering, Marketing, Sales (department groups)
    - admin (role group)
    """
    provisioning_service = UserProvisioningService(db_session)

    # Test case 1: User with multiple non-admin groups
    groups_user = ["Everyone", "Engineering", "Platform-Team", "EMEA"]
    role = provisioning_service.assign_roles_from_groups(groups_user)
    assert role == "user"

    # Test case 2: User with admin group among multiple groups
    groups_admin = ["Everyone", "Engineering", "admin", "Platform-Team"]
    role = provisioning_service.assign_roles_from_groups(groups_admin)
    assert role == "admin"

    # Test case 3: Case-insensitive admin group detection
    groups_admin_case = ["Everyone", "ADMIN", "Engineering"]
    role = provisioning_service.assign_roles_from_groups(groups_admin_case)
    assert role == "admin"


# Test 12: Okta attribute mapping edge cases
def test_okta_attribute_mapping_edge_cases(db_session: Session) -> None:
    """
    Test attribute mapping for various Okta attribute formats.

    Story 6.1 - Acceptance Criteria 3: User provisioning verification

    Okta can send attributes in different formats:
    - displayName (preferred)
    - firstName + lastName (fallback)
    - email as name (last resort)
    """
    provisioning_service = UserProvisioningService(db_session)

    # Test case 1: Only email (no name attributes)
    claims_email_only = {
        "email": "emailonly@example.com",
        "groups": [],
    }
    mapped = provisioning_service.map_saml_attributes(claims_email_only)
    # Name should default to email prefix
    assert mapped["email"] == "emailonly@example.com"

    # Test case 2: Standard Okta attributes
    claims_standard = {
        "email": "standard@example.com",
        "name": "Standard User",
        "groups": ["Everyone"],
    }
    mapped = provisioning_service.map_saml_attributes(claims_standard)
    assert mapped["email"] == "standard@example.com"
    assert mapped["name"] == "Standard User"
    assert mapped["email_verified"] is True
    assert mapped["status"] == "active"


# Test 13: Provisioning with missing required attributes
def test_okta_provisioning_missing_email(db_session: Session, okta_provider: SAMLProvider) -> None:
    """
    Test provisioning fails gracefully when email is missing.

    Story 6.1 - Error scenario testing

    Email is a required attribute for user provisioning.
    """
    provisioning_service = UserProvisioningService(db_session)

    # Missing email attribute
    claims_no_email = {
        "name": "No Email User",
        "groups": ["Everyone"],
    }

    with pytest.raises(ValueError) as exc_info:
        provisioning_service.provision_user_from_saml(
            saml_claims=claims_no_email,
            idp_entity_id=okta_provider.entity_id,
            subject_id="test-subject-id",
        )

    assert "email" in str(exc_info.value).lower()
    assert "required" in str(exc_info.value).lower()


# Test 14: Complete provisioning flow integration
@patch("app.services.saml_service.OneLogin_Saml2_Auth")
def test_okta_complete_provisioning_flow(
    mock_saml_auth: MagicMock,
    db_session: Session,
    okta_provider: SAMLProvider,
) -> None:
    """
    Test complete end-to-end provisioning flow.

    Story 6.1 - Comprehensive provisioning test

    Full flow:
    1. New user authenticates via Okta
    2. User is provisioned with all attributes
    3. External ID is created
    4. Session is created with correct roles
    5. Subsequent login updates user
    """
    user_email = "complete@example.com"
    okta_subject_id = "00uabc123"

    # First login - user provisioning
    mock_auth_instance = MagicMock()
    mock_auth_instance.is_authenticated.return_value = True
    mock_auth_instance.get_errors.return_value = []
    mock_auth_instance.get_attributes.return_value = {
        "email": [user_email],
        "displayName": ["Complete User"],
        "groups": ["Everyone", "Engineering"],
    }
    mock_auth_instance.get_nameid.return_value = okta_subject_id
    mock_saml_auth.return_value = mock_auth_instance

    saml_response = base64.b64encode(b"<okta-complete-flow>").decode("utf-8")

    # First login
    response = client.post(
        "/api/auth/saml/acs",
        data={
            "SAMLResponse": saml_response,
            "RelayState": okta_provider.id,
        },
    )

    assert response.status_code == 200
    first_login_data = response.json()
    first_user_id = first_login_data["user"]["id"]

    # Verify user was provisioned
    user = db_session.query(User).filter(User.email == user_email).first()
    assert user is not None
    assert user.name == "Complete User"

    # Verify external ID
    external_id = (
        db_session.query(UserExternalId)
        .filter(UserExternalId.user_id == user.id)
        .first()
    )
    assert external_id is not None
    assert external_id.external_user_id == okta_subject_id

    # Second login - user update
    mock_auth_instance.get_attributes.return_value = {
        "email": [user_email],
        "displayName": ["Complete User Updated"],  # Name changed
        "groups": ["Everyone", "Engineering", "admin"],  # Added admin group
    }

    response = client.post(
        "/api/auth/saml/acs",
        data={
            "SAMLResponse": saml_response,
            "RelayState": okta_provider.id,
        },
    )

    assert response.status_code == 200
    second_login_data = response.json()

    # Verify same user (not duplicated)
    assert second_login_data["user"]["id"] == first_user_id

    # Verify name was updated
    db_session.refresh(user)
    assert user.name == "Complete User Updated"

    # Verify admin role in second session
    import jwt

    from app.core.config import get_settings

    settings = get_settings()
    token_claims = jwt.decode(
        second_login_data["session_token"],
        settings.auth_jwt_secret,
        algorithms=["HS256"],
    )
    assert "admin" in token_claims["roles"]
