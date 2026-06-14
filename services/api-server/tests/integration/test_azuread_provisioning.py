"""
Azure AD User Provisioning Tests

Story 6.2 - Azure AD Integration Testing
Tests user provisioning with Azure AD specific attributes and role assignment.

Acceptance Criteria 3: User provisioning verification
Acceptance Criteria 4: Role assignment from Azure AD groups
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.db.models import User, UserExternalId
from app.services.user_provisioning_service import UserProvisioningService


class TestAzureADProvisioning:
    """Test Azure AD user provisioning integration."""

    def test_provision_new_user_from_azure_ad(self, db_session: Session) -> None:
        """
        Test JIT provisioning of new user from Azure AD.

        Acceptance Criteria 3: User provisioning verification
        """
        provisioning_service = UserProvisioningService(db_session)

        # Azure AD SAML claims
        azure_claims = {
            "email": "newuser@example.com",
            "name": "Azure New User",
            "groups": ["azure-ad-group-guid-1", "azure-ad-group-guid-2"],
        }

        # Provision user
        user = provisioning_service.provision_user_from_saml(
            saml_claims=azure_claims,
            idp_entity_id="https://sts.windows.net/12345678-1234-1234-1234-123456789abc/",
            subject_id="azure-object-id-12345",
        )

        assert user is not None
        assert user.email == "newuser@example.com"
        assert user.name == "Azure New User"
        assert user.email_verified is True
        assert user.status == "active"

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
        assert external_id.external_entity_id == "https://sts.windows.net/12345678-1234-1234-1234-123456789abc/"
        assert external_id.external_user_id == "azure-object-id-12345"

    def test_update_existing_user_from_azure_ad(self, db_session: Session) -> None:
        """
        Test updating existing user on subsequent Azure AD login.

        Acceptance Criteria 3: User provisioning verification
        """
        # Create existing user
        existing_user = User(
            email="existing@example.com",
            name="Old Name",
            password_hash="dummy-hash",
            email_verified=False,
            status="pending",
        )
        db_session.add(existing_user)
        db_session.commit()
        db_session.refresh(existing_user)

        provisioning_service = UserProvisioningService(db_session)

        # Azure AD claims with updated info
        azure_claims = {
            "email": "existing@example.com",
            "name": "Updated Azure Name",
            "groups": ["azure-group-1"],
        }

        # Update user via provisioning
        updated_user = provisioning_service.provision_user_from_saml(
            saml_claims=azure_claims,
            idp_entity_id="https://sts.windows.net/tenant-id/",
            subject_id="azure-object-id-existing",
        )

        assert updated_user.id == existing_user.id
        assert updated_user.name == "Updated Azure Name"
        assert updated_user.email_verified is True
        assert updated_user.status == "active"
        assert updated_user.last_login_at is not None

    def test_azure_ad_admin_role_assignment(self, db_session: Session) -> None:
        """
        Test admin role assignment from Azure AD groups.

        Acceptance Criteria 4: Role assignment from Azure AD groups
        """
        provisioning_service = UserProvisioningService(db_session)

        # Azure AD claims with admin group
        azure_claims = {
            "email": "admin@example.com",
            "name": "Azure Admin",
            "groups": ["admin", "users"],
        }

        user = provisioning_service.provision_user_from_saml(
            saml_claims=azure_claims,
            idp_entity_id="https://sts.windows.net/tenant-id/",
            subject_id="admin-object-id",
        )

        # Check role assignment
        role = provisioning_service.assign_roles_from_groups(azure_claims["groups"])
        assert role == "admin"

    def test_azure_ad_user_role_assignment(self, db_session: Session) -> None:
        """
        Test default user role assignment from Azure AD groups.

        Acceptance Criteria 4: Role assignment from Azure AD groups
        """
        provisioning_service = UserProvisioningService(db_session)

        # Azure AD claims without admin group
        azure_claims = {
            "email": "user@example.com",
            "name": "Azure User",
            "groups": ["developers", "engineering"],
        }

        user = provisioning_service.provision_user_from_saml(
            saml_claims=azure_claims,
            idp_entity_id="https://sts.windows.net/tenant-id/",
            subject_id="user-object-id",
        )

        # Check role assignment
        role = provisioning_service.assign_roles_from_groups(azure_claims["groups"])
        assert role == "user"

    def test_azure_ad_directory_role_admin(self, db_session: Session) -> None:
        """
        Test admin role assignment from Azure AD directory roles.

        Azure AD can send directory roles like 'Global Administrator'.
        Acceptance Criteria 4: Admin role from Azure AD directory role
        """
        provisioning_service = UserProvisioningService(db_session)

        # Azure AD claims with directory role
        azure_claims = {
            "email": "globaladmin@example.com",
            "name": "Global Admin",
            "groups": ["Global Administrator", "Company Administrator"],
        }

        user = provisioning_service.provision_user_from_saml(
            saml_claims=azure_claims,
            idp_entity_id="https://sts.windows.net/tenant-id/",
            subject_id="global-admin-object-id",
        )

        # Check role assignment - should recognize admin keywords
        role = provisioning_service.assign_roles_from_groups(azure_claims["groups"])
        assert role == "admin"  # Contains 'admin' in group name

    def test_azure_ad_no_groups_default_role(self, db_session: Session) -> None:
        """
        Test default role assignment when no groups are provided.
        """
        provisioning_service = UserProvisioningService(db_session)

        # Azure AD claims without groups
        azure_claims = {
            "email": "nogroups@example.com",
            "name": "No Groups User",
            "groups": [],
        }

        user = provisioning_service.provision_user_from_saml(
            saml_claims=azure_claims,
            idp_entity_id="https://sts.windows.net/tenant-id/",
            subject_id="no-groups-object-id",
        )

        # Check default role assignment
        role = provisioning_service.assign_roles_from_groups(azure_claims["groups"])
        assert role == "user"

    def test_azure_ad_external_id_tracking(self, db_session: Session) -> None:
        """
        Test external ID tracking for Azure AD users.

        Azure AD object ID should be stored as external user ID.
        """
        provisioning_service = UserProvisioningService(db_session)

        azure_claims = {
            "email": "tracked@example.com",
            "name": "Tracked User",
            "groups": [],
        }

        azure_entity_id = "https://sts.windows.net/12345678-1234-1234-1234-123456789abc/"
        azure_object_id = "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d"

        user = provisioning_service.provision_user_from_saml(
            saml_claims=azure_claims,
            idp_entity_id=azure_entity_id,
            subject_id=azure_object_id,
        )

        # Verify external ID mapping
        external_id = (
            db_session.query(UserExternalId)
            .filter(
                UserExternalId.user_id == user.id,
                UserExternalId.provider == "saml",
            )
            .first()
        )

        assert external_id is not None
        assert external_id.external_entity_id == azure_entity_id
        assert external_id.external_user_id == azure_object_id

    def test_azure_ad_update_external_id(self, db_session: Session) -> None:
        """
        Test updating external ID when user logs in again.
        """
        provisioning_service = UserProvisioningService(db_session)

        azure_claims = {
            "email": "update.external@example.com",
            "name": "External Update User",
            "groups": [],
        }

        azure_entity_id = "https://sts.windows.net/tenant-id/"
        azure_object_id_1 = "old-object-id"

        # First login
        user = provisioning_service.provision_user_from_saml(
            saml_claims=azure_claims,
            idp_entity_id=azure_entity_id,
            subject_id=azure_object_id_1,
        )

        # Second login with updated object ID (edge case)
        azure_object_id_2 = "new-object-id"
        updated_user = provisioning_service.provision_user_from_saml(
            saml_claims=azure_claims,
            idp_entity_id=azure_entity_id,
            subject_id=azure_object_id_2,
        )

        # Verify external ID was updated
        external_id = (
            db_session.query(UserExternalId)
            .filter(
                UserExternalId.user_id == updated_user.id,
                UserExternalId.provider == "saml",
            )
            .first()
        )

        assert external_id is not None
        assert external_id.external_user_id == azure_object_id_2

    def test_azure_ad_missing_email_error(self, db_session: Session) -> None:
        """
        Test error when email is missing from Azure AD claims.
        """
        provisioning_service = UserProvisioningService(db_session)

        # Azure AD claims without email
        azure_claims = {
            "name": "No Email User",
            "groups": [],
        }

        # Should raise ValueError
        with pytest.raises(ValueError, match="Email is required"):
            provisioning_service.provision_user_from_saml(
                saml_claims=azure_claims,
                idp_entity_id="https://sts.windows.net/tenant-id/",
                subject_id="no-email-object-id",
            )

    def test_azure_ad_multi_tenant_provisioning(self, db_session: Session) -> None:
        """
        Test provisioning users from multiple Azure AD tenants.

        Acceptance Criteria 4: Multi-tenant support test
        """
        provisioning_service = UserProvisioningService(db_session)

        # Tenant A user
        tenant_a_claims = {
            "email": "usera@tenant-a.com",
            "name": "Tenant A User",
            "groups": ["admin"],
        }

        user_a = provisioning_service.provision_user_from_saml(
            saml_claims=tenant_a_claims,
            idp_entity_id="https://sts.windows.net/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/",
            subject_id="object-id-a",
        )

        # Tenant B user
        tenant_b_claims = {
            "email": "userb@tenant-b.com",
            "name": "Tenant B User",
            "groups": ["users"],
        }

        user_b = provisioning_service.provision_user_from_saml(
            saml_claims=tenant_b_claims,
            idp_entity_id="https://sts.windows.net/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb/",
            subject_id="object-id-b",
        )

        # Verify both users exist with correct external IDs
        external_id_a = (
            db_session.query(UserExternalId)
            .filter(UserExternalId.user_id == user_a.id)
            .first()
        )
        external_id_b = (
            db_session.query(UserExternalId)
            .filter(UserExternalId.user_id == user_b.id)
            .first()
        )

        assert external_id_a.external_entity_id == "https://sts.windows.net/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/"
        assert external_id_b.external_entity_id == "https://sts.windows.net/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb/"

    def test_azure_ad_guest_user_provisioning(self, db_session: Session) -> None:
        """
        Test provisioning of Azure AD B2B guest users.
        """
        provisioning_service = UserProvisioningService(db_session)

        # Guest user from another tenant
        guest_claims = {
            "email": "guest@external-company.com",
            "name": "Guest User",
            "groups": [],
        }

        guest_user = provisioning_service.provision_user_from_saml(
            saml_claims=guest_claims,
            idp_entity_id="https://sts.windows.net/host-tenant-id/",
            subject_id="guest-object-id",
        )

        assert guest_user.email == "guest@external-company.com"
        assert guest_user.status == "active"

    def test_azure_ad_group_guid_format(self, db_session: Session) -> None:
        """
        Test handling of Azure AD group GUIDs.

        Azure AD returns group GUIDs by default, not display names.
        """
        provisioning_service = UserProvisioningService(db_session)

        azure_claims = {
            "email": "groupguid@example.com",
            "name": "Group GUID User",
            "groups": [
                "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d",  # GUID format
                "b2c3d4e5-f6a7-5b6c-9d0e-1f2a3b4c5d6e",  # GUID format
            ],
        }

        user = provisioning_service.provision_user_from_saml(
            saml_claims=azure_claims,
            idp_entity_id="https://sts.windows.net/tenant-id/",
            subject_id="group-guid-object-id",
        )

        # Should handle GUIDs without error
        assert user.email == "groupguid@example.com"

        # Role assignment should default to user (GUIDs don't match 'admin')
        role = provisioning_service.assign_roles_from_groups(azure_claims["groups"])
        assert role == "user"

    def test_azure_ad_last_login_update(self, db_session: Session) -> None:
        """
        Test that last_login_at is updated on each login.
        """
        provisioning_service = UserProvisioningService(db_session)

        azure_claims = {
            "email": "logintime@example.com",
            "name": "Login Time User",
            "groups": [],
        }

        # First login
        user = provisioning_service.provision_user_from_saml(
            saml_claims=azure_claims,
            idp_entity_id="https://sts.windows.net/tenant-id/",
            subject_id="login-time-object-id",
        )

        first_login = user.last_login_at
        assert first_login is not None

        # Second login
        import time
        time.sleep(0.1)  # Ensure timestamp difference

        updated_user = provisioning_service.provision_user_from_saml(
            saml_claims=azure_claims,
            idp_entity_id="https://sts.windows.net/tenant-id/",
            subject_id="login-time-object-id",
        )

        assert updated_user.last_login_at > first_login
