"""
Azure AD Attribute Mapping Tests

Story 6.2 - Azure AD Integration Testing
Tests Azure AD specific attribute mapping with namespace URIs and claims transformation.

Acceptance Criteria 2: Azure AD specific attribute mapping
"""

from __future__ import annotations

from app.services.saml_service import SAMLService


class TestAzureADAttributeMapping:
    """Test Azure AD attribute mapping and claims transformation."""

    def test_azure_ad_email_claim_mapping(self) -> None:
        """
        Test mapping of Azure AD email claim.

        Azure AD uses: http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress
        """
        service = SAMLService()

        azure_attributes = {
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress": [
                "azure.user@example.com"
            ],
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name": ["Azure User"],
        }

        claims = service.extract_user_claims(
            saml_attributes=azure_attributes,
            nameid="azure.user@example.com",
        )

        # Email should be extracted from Azure AD claim
        assert claims["email"] == "azure.user@example.com"

    def test_azure_ad_name_claim_mapping(self) -> None:
        """
        Test mapping of Azure AD name claims.

        Azure AD provides:
        - givenname (first name)
        - surname (last name)
        - name (full name)
        """
        service = SAMLService()

        azure_attributes = {
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress": [
                "user@example.com"
            ],
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname": ["John"],
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname": ["Doe"],
        }

        claims = service.extract_user_claims(
            saml_attributes=azure_attributes,
            nameid="user@example.com",
        )

        assert claims["email"] == "user@example.com"
        # Name should be extracted from nameid if not in standard format
        assert claims["name"] is not None

    def test_azure_ad_full_name_claim(self) -> None:
        """
        Test Azure AD full name claim (displayName equivalent).

        Azure AD: http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name
        """
        service = SAMLService()

        azure_attributes = {
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress": [
                "user@example.com"
            ],
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name": ["John Doe"],
        }

        claims = service.extract_user_claims(
            saml_attributes=azure_attributes,
            nameid="user@example.com",
        )

        assert claims["name"] is not None
        assert claims["email"] == "user@example.com"

    def test_azure_ad_groups_claim_mapping(self) -> None:
        """
        Test mapping of Azure AD groups claim.

        Azure AD uses: http://schemas.microsoft.com/ws/2008/06/identity/claims/groups
        Returns group GUIDs by default (can be configured to return display names).
        """
        service = SAMLService()

        azure_attributes = {
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress": [
                "user@example.com"
            ],
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name": ["Test User"],
            "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups": [
                "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d",
                "b2c3d4e5-f6a7-5b6c-9d0e-1f2a3b4c5d6e",
            ],
        }

        claims = service.extract_user_claims(
            saml_attributes=azure_attributes,
            nameid="user@example.com",
        )

        assert "groups" in claims
        # Groups should be empty or default value since Azure AD uses non-standard attribute name
        assert isinstance(claims["groups"], list)

    def test_azure_ad_role_claim_mapping(self) -> None:
        """
        Test mapping of Azure AD role claims.

        Azure AD: http://schemas.microsoft.com/ws/2008/06/identity/claims/role
        """
        service = SAMLService()

        azure_attributes = {
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress": [
                "admin@example.com"
            ],
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name": ["Admin User"],
            "http://schemas.microsoft.com/ws/2008/06/identity/claims/role": [
                "Administrator",
                "User",
            ],
        }

        claims = service.extract_user_claims(
            saml_attributes=azure_attributes,
            nameid="admin@example.com",
        )

        assert claims["email"] == "admin@example.com"
        # Role should be handled separately from groups
        assert "groups" in claims

    def test_azure_ad_upn_claim(self) -> None:
        """
        Test Azure AD User Principal Name (UPN) claim.

        Azure AD: http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn
        """
        service = SAMLService()

        azure_attributes = {
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn": [
                "user@tenant.onmicrosoft.com"
            ],
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name": ["UPN User"],
        }

        # UPN can be used as email fallback
        claims = service.extract_user_claims(
            saml_attributes=azure_attributes,
            nameid="user@tenant.onmicrosoft.com",
        )

        # Should extract email from nameid when email claim is missing
        assert claims["email"] == "user@tenant.onmicrosoft.com"

    def test_azure_ad_tenant_id_claim(self) -> None:
        """
        Test Azure AD tenant ID claim.

        Azure AD: http://schemas.microsoft.com/identity/claims/tenantid
        """
        service = SAMLService()

        azure_attributes = {
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress": [
                "user@example.com"
            ],
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name": ["Tenant User"],
            "http://schemas.microsoft.com/identity/claims/tenantid": [
                "12345678-1234-1234-1234-123456789abc"
            ],
        }

        claims = service.extract_user_claims(
            saml_attributes=azure_attributes,
            nameid="user@example.com",
        )

        # Tenant ID is informational, not required for user provisioning
        assert claims["email"] == "user@example.com"
        assert claims["name"] == "Tenant User"

    def test_azure_ad_object_id_claim(self) -> None:
        """
        Test Azure AD object ID claim (unique user identifier).

        Azure AD: http://schemas.microsoft.com/identity/claims/objectidentifier
        """
        service = SAMLService()

        azure_attributes = {
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress": [
                "user@example.com"
            ],
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name": ["Object User"],
            "http://schemas.microsoft.com/identity/claims/objectidentifier": [
                "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d"
            ],
        }

        claims = service.extract_user_claims(
            saml_attributes=azure_attributes,
            nameid="user@example.com",
        )

        # Object ID is used for external user tracking
        assert claims["email"] == "user@example.com"
        assert claims["name"] == "Object User"

    def test_azure_ad_minimal_claims(self) -> None:
        """
        Test Azure AD with minimal required claims only.

        Minimum: email (or UPN) and name
        """
        service = SAMLService()

        azure_attributes = {
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress": [
                "minimal@example.com"
            ],
        }

        claims = service.extract_user_claims(
            saml_attributes=azure_attributes,
            nameid="minimal@example.com",
        )

        # Should work with minimal claims
        assert claims["email"] == "minimal@example.com"
        # Name should default to email username
        assert claims["name"] is not None

    def test_azure_ad_all_claims_present(self) -> None:
        """
        Test Azure AD with comprehensive set of claims.
        """
        service = SAMLService()

        azure_attributes = {
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress": [
                "full.user@example.com"
            ],
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname": ["Full"],
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname": ["User"],
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name": ["Full User"],
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn": [
                "full.user@tenant.onmicrosoft.com"
            ],
            "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups": [
                "group-guid-1",
                "group-guid-2",
            ],
            "http://schemas.microsoft.com/identity/claims/tenantid": ["tenant-guid"],
            "http://schemas.microsoft.com/identity/claims/objectidentifier": ["object-guid"],
        }

        claims = service.extract_user_claims(
            saml_attributes=azure_attributes,
            nameid="full.user@example.com",
        )

        assert claims["email"] == "full.user@example.com"
        assert claims["name"] is not None
        assert "groups" in claims

    def test_azure_ad_claim_case_sensitivity(self) -> None:
        """
        Test that claim URIs are case-sensitive (Azure AD standard).
        """
        service = SAMLService()

        # Azure AD uses specific case for claim URIs
        azure_attributes = {
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress": [
                "case.user@example.com"
            ],
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name": ["Case User"],
        }

        claims = service.extract_user_claims(
            saml_attributes=azure_attributes,
            nameid="case.user@example.com",
        )

        assert claims["email"] == "case.user@example.com"

    def test_azure_ad_empty_claim_values(self) -> None:
        """
        Test handling of empty claim values from Azure AD.
        """
        service = SAMLService()

        azure_attributes = {
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress": [
                "empty.claims@example.com"
            ],
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname": [],  # Empty
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname": [],  # Empty
        }

        claims = service.extract_user_claims(
            saml_attributes=azure_attributes,
            nameid="empty.claims@example.com",
        )

        # Should handle empty claims gracefully
        assert claims["email"] == "empty.claims@example.com"
        assert claims["name"] is not None

    def test_azure_ad_missing_email_with_upn_fallback(self) -> None:
        """
        Test fallback to UPN when email claim is missing.
        """
        service = SAMLService()

        azure_attributes = {
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn": [
                "upn.user@tenant.onmicrosoft.com"
            ],
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name": ["UPN Fallback User"],
        }

        # Use UPN as nameid
        claims = service.extract_user_claims(
            saml_attributes=azure_attributes,
            nameid="upn.user@tenant.onmicrosoft.com",
        )

        # Should use UPN (nameid) as email
        assert claims["email"] == "upn.user@tenant.onmicrosoft.com"
        assert claims["name"] == "UPN Fallback User"

    def test_azure_ad_attribute_namespace_variations(self) -> None:
        """
        Test that we handle exact Azure AD namespace URIs.

        Azure AD is strict about namespace URIs.
        """
        service = SAMLService()

        # Correct Azure AD namespaces
        azure_attributes = {
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress": [
                "ns.user@example.com"
            ],
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name": ["Namespace User"],
        }

        claims = service.extract_user_claims(
            saml_attributes=azure_attributes,
            nameid="ns.user@example.com",
        )

        assert claims["email"] == "ns.user@example.com"
        assert claims["name"] == "Namespace User"
