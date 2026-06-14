"""
Tests for User Provisioning Service

Story 2.3 - User Provisioning from SAML
Comprehensive tests for JIT provisioning, attribute mapping, and role assignment.
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.db.models import User
from app.services.user_provisioning_service import UserProvisioningService


@pytest.fixture
def provisioning_service(db_session: Session) -> UserProvisioningService:
    """Create UserProvisioningService instance."""
    return UserProvisioningService(db_session)


@pytest.fixture
def saml_claims_basic() -> dict:
    """Basic SAML user claims."""
    return {
        "email": "john.doe@example.com",
        "name": "John Doe",
        "groups": [],
    }


@pytest.fixture
def saml_claims_with_groups() -> dict:
    """SAML claims with groups."""
    return {
        "email": "admin.user@example.com",
        "name": "Admin User",
        "groups": ["admin", "developers", "users"],
    }


@pytest.fixture
def saml_identity() -> dict:
    """SAML identity information."""
    return {
        "idp_entity_id": "https://idp.example.com/metadata",
        "subject_id": "user123@idp.example.com",
    }


# Test 1: Just-In-Time (JIT) provisioning - create user on first SSO login
def test_provision_new_user_creates_user(
    provisioning_service: UserProvisioningService,
    db_session: Session,
    saml_claims_basic: dict,
    saml_identity: dict,
) -> None:
    """Test that a new user is created on first SAML login."""
    # Arrange
    assert db_session.query(User).filter(User.email == saml_claims_basic["email"]).first() is None

    # Act
    user = provisioning_service.provision_user_from_saml(
        saml_claims=saml_claims_basic,
        idp_entity_id=saml_identity["idp_entity_id"],
        subject_id=saml_identity["subject_id"],
    )

    # Assert
    assert user is not None
    assert user.email == saml_claims_basic["email"]
    assert user.name == saml_claims_basic["name"]
    assert user.email_verified is True  # SAML users are pre-verified
    assert user.status == "active"
    assert user.last_login_at is not None


# Test 2: User attribute mapping (SAML attributes → local user fields)
def test_map_saml_attributes(
    provisioning_service: UserProvisioningService,
    saml_claims_basic: dict,
) -> None:
    """Test mapping SAML attributes to user fields."""
    # Act
    mapped_attrs = provisioning_service.map_saml_attributes(saml_claims_basic)

    # Assert
    assert mapped_attrs["email"] == saml_claims_basic["email"]
    assert mapped_attrs["name"] == saml_claims_basic["name"]
    assert mapped_attrs["email_verified"] is True
    assert mapped_attrs["status"] == "active"


# Test 3: Role assignment logic based on SAML groups
def test_assign_roles_from_groups_default_user(
    provisioning_service: UserProvisioningService,
    saml_claims_basic: dict,
) -> None:
    """Test that default role is 'user' when no admin group present."""
    # Act
    role = provisioning_service.assign_roles_from_groups(saml_claims_basic["groups"])

    # Assert
    assert role == "user"


# Test 4: Role assignment - admin role if 'admin' group present
def test_assign_roles_from_groups_admin(
    provisioning_service: UserProvisioningService,
    saml_claims_with_groups: dict,
) -> None:
    """Test that role is 'admin' when admin group is present."""
    # Act
    role = provisioning_service.assign_roles_from_groups(saml_claims_with_groups["groups"])

    # Assert
    assert role == "admin"


# Test 5: Update existing users on subsequent logins
def test_provision_existing_user_updates_attributes(
    provisioning_service: UserProvisioningService,
    db_session: Session,
    saml_claims_basic: dict,
    saml_identity: dict,
) -> None:
    """Test that existing user attributes are updated on subsequent logins."""
    # Arrange - Create initial user
    first_user = provisioning_service.provision_user_from_saml(
        saml_claims=saml_claims_basic,
        idp_entity_id=saml_identity["idp_entity_id"],
        subject_id=saml_identity["subject_id"],
    )
    first_user_id = first_user.id
    first_login_at = first_user.last_login_at

    # Act - Update user with new name
    updated_claims = saml_claims_basic.copy()
    updated_claims["name"] = "John Updated Doe"

    updated_user = provisioning_service.provision_user_from_saml(
        saml_claims=updated_claims,
        idp_entity_id=saml_identity["idp_entity_id"],
        subject_id=saml_identity["subject_id"],
    )

    # Assert
    assert updated_user.id == first_user_id  # Same user
    assert updated_user.name == "John Updated Doe"  # Name updated
    assert updated_user.last_login_at > first_login_at  # Login time updated


# Test 6: Store external user ID in user_external_ids table
def test_provision_user_stores_external_id(
    provisioning_service: UserProvisioningService,
    db_session: Session,
    saml_claims_basic: dict,
    saml_identity: dict,
) -> None:
    """Test that external ID is stored in user_external_ids table."""
    # Act
    user = provisioning_service.provision_user_from_saml(
        saml_claims=saml_claims_basic,
        idp_entity_id=saml_identity["idp_entity_id"],
        subject_id=saml_identity["subject_id"],
    )

    # Assert
    # Query user_external_ids to verify entry
    from app.db.models import UserExternalId

    external_id = (
        db_session.query(UserExternalId)
        .filter(
            UserExternalId.user_id == user.id,
            UserExternalId.provider == "saml",
            UserExternalId.external_entity_id == saml_identity["idp_entity_id"],
        )
        .first()
    )

    assert external_id is not None
    assert external_id.external_user_id == saml_identity["subject_id"]


# Test 7: Update user attributes method
def test_update_user_attributes(
    provisioning_service: UserProvisioningService,
    db_session: Session,
    saml_claims_basic: dict,
    saml_identity: dict,
) -> None:
    """Test updating existing user attributes."""
    # Arrange - Create user first
    user = provisioning_service.provision_user_from_saml(
        saml_claims=saml_claims_basic,
        idp_entity_id=saml_identity["idp_entity_id"],
        subject_id=saml_identity["subject_id"],
    )

    # Act - Update attributes
    new_attrs = {
        "name": "John New Name",
    }
    updated_user = provisioning_service.update_user_attributes(user, new_attrs)

    # Assert
    assert updated_user.name == "John New Name"
    assert updated_user.email == saml_claims_basic["email"]  # Email unchanged


# Test 8: Handle missing email in SAML claims
def test_provision_user_missing_email_raises_error(
    provisioning_service: UserProvisioningService,
    saml_identity: dict,
) -> None:
    """Test that missing email raises ValueError."""
    # Arrange
    invalid_claims = {
        "name": "Test User",
        "groups": [],
    }

    # Act & Assert
    with pytest.raises(ValueError, match="Email is required"):
        provisioning_service.provision_user_from_saml(
            saml_claims=invalid_claims,
            idp_entity_id=saml_identity["idp_entity_id"],
            subject_id=saml_identity["subject_id"],
        )


# Test 9: Handle empty groups list
def test_assign_roles_empty_groups(
    provisioning_service: UserProvisioningService,
) -> None:
    """Test role assignment with empty groups list."""
    # Act
    role = provisioning_service.assign_roles_from_groups([])

    # Assert
    assert role == "user"


# Test 10: Case-insensitive admin group matching
def test_assign_roles_admin_case_insensitive(
    provisioning_service: UserProvisioningService,
) -> None:
    """Test that admin group matching is case-insensitive."""
    # Act
    role_upper = provisioning_service.assign_roles_from_groups(["ADMIN", "users"])
    role_mixed = provisioning_service.assign_roles_from_groups(["Admin", "developers"])
    role_lower = provisioning_service.assign_roles_from_groups(["admin"])

    # Assert
    assert role_upper == "admin"
    assert role_mixed == "admin"
    assert role_lower == "admin"


# Test 11: Idempotent provisioning - multiple calls don't create duplicates
def test_provision_user_idempotent(
    provisioning_service: UserProvisioningService,
    db_session: Session,
    saml_claims_basic: dict,
    saml_identity: dict,
) -> None:
    """Test that multiple provisioning calls are idempotent."""
    # Act - Provision same user multiple times
    user1 = provisioning_service.provision_user_from_saml(
        saml_claims=saml_claims_basic,
        idp_entity_id=saml_identity["idp_entity_id"],
        subject_id=saml_identity["subject_id"],
    )

    user2 = provisioning_service.provision_user_from_saml(
        saml_claims=saml_claims_basic,
        idp_entity_id=saml_identity["idp_entity_id"],
        subject_id=saml_identity["subject_id"],
    )

    # Assert - Same user returned
    assert user1.id == user2.id

    # Verify only one user exists
    user_count = db_session.query(User).filter(User.email == saml_claims_basic["email"]).count()
    assert user_count == 1


# Test 12: Generate random password hash for SAML users
def test_provision_user_generates_password_hash(
    provisioning_service: UserProvisioningService,
    db_session: Session,
    saml_claims_basic: dict,
    saml_identity: dict,
) -> None:
    """Test that SAML users get a random password hash."""
    # Act
    user = provisioning_service.provision_user_from_saml(
        saml_claims=saml_claims_basic,
        idp_entity_id=saml_identity["idp_entity_id"],
        subject_id=saml_identity["subject_id"],
    )

    # Assert
    assert user.password_hash is not None
    assert len(user.password_hash) > 0
    # SAML users shouldn't be able to use this password (it's random)
