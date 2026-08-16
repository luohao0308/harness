"""
SAML Service Provider Implementation

Handles SAML Service Provider metadata generation and SSO operations.
Uses python3-saml (OneLogin SAML Python Toolkit) for SAML protocol support.

Story 1.1 - SAML Service Provider Setup
Story 2.1 - SP-Initiated SSO Flow
Story 2.2 - SAML Assertion Validation
Story 2.3 - User Provisioning from SAML
Story 4.2 - Single Logout (SLO)
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from typing import Any

from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.settings import OneLogin_Saml2_Settings
from sqlalchemy.orm import Session

from app.config.saml_config import get_saml_config
from app.db.models import SAMLProvider, User
from app.services.session_service import SessionService
from app.services.user_provisioning_service import UserProvisioningService


class SAMLService:
    """
    SAML Service Provider operations.

    Generates and serves SAML SP metadata XML for IdP integration.
    """

    def __init__(self) -> None:
        """Initialize SAML service with configuration."""
        self._config = get_saml_config()
        self._settings: OneLogin_Saml2_Settings | None = None

    def _get_saml_settings(self, provider: SAMLProvider | None = None) -> OneLogin_Saml2_Settings:
        """
        Build OneLogin SAML settings from configuration.

        Args:
            provider: Optional SAML provider for IdP-specific settings.

        Returns:
            OneLogin_Saml2_Settings instance configured for this SP.
        """
        # Build settings dict compatible with python3-saml
        settings_dict: dict[str, Any] = {
            "strict": True,
            "debug": False,
            "sp": {
                "entityId": self._config["sp_entity_id"],
                "assertionConsumerService": {
                    "url": self._config["sp_acs_url"],
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
                },
                "singleLogoutService": {
                    "url": self._config["sp_sls_url"],
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
                },
                "x509cert": self._extract_cert_content(self._config["sp_x509_cert"]),
                "privateKey": self._extract_key_content(self._config["sp_private_key"]),
            },
            "idp": {
                "entityId": provider.entity_id if provider else "https://idp.example.com/metadata",
                "singleSignOnService": {
                    "url": provider.sso_url if provider else "https://idp.example.com/sso",
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
                },
                "singleLogoutService": {
                    "url": provider.slo_url
                    if provider and provider.slo_url
                    else "https://idp.example.com/slo",
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
                },
                "x509cert": self._extract_cert_content(provider.x509_cert) if provider else "",
            },
        }
        return OneLogin_Saml2_Settings(settings_dict)

    def _extract_cert_content(self, cert_with_headers: str) -> str:
        """
        Extract certificate content without BEGIN/END headers.

        python3-saml expects just the base64 content, not PEM headers.

        Args:
            cert_with_headers: Certificate with BEGIN CERTIFICATE / END CERTIFICATE headers.

        Returns:
            Base64-encoded certificate content without headers or newlines.
        """
        lines = cert_with_headers.strip().split("\n")
        content_lines = [
            line.strip()
            for line in lines
            if line.strip()
            and not line.startswith("-----BEGIN")
            and not line.startswith("-----END")
        ]
        return "".join(content_lines)

    def _extract_key_content(self, key_with_headers: str) -> str:
        """
        Extract private key content without BEGIN/END headers.

        Args:
            key_with_headers: Private key with BEGIN PRIVATE KEY / END PRIVATE KEY headers.

        Returns:
            Base64-encoded key content without headers or newlines.
        """
        lines = key_with_headers.strip().split("\n")
        content_lines = [
            line.strip()
            for line in lines
            if line.strip()
            and not line.startswith("-----BEGIN")
            and not line.startswith("-----END")
        ]
        return "".join(content_lines)

    def generate_sp_metadata(self) -> str:
        """
        Generate SAML Service Provider metadata XML.

        Returns SP metadata XML that can be shared with Identity Providers
        for SSO integration. Contains entity ID, ACS URL, SLS URL, and X.509 certificate.

        Returns:
            XML string containing complete SP metadata.

        Raises:
            Exception: If metadata generation fails (invalid config, missing cert, etc).
        """
        settings = self._get_saml_settings()
        metadata = settings.get_sp_metadata()

        # python3-saml versions differ on whether metadata is bytes or text.
        if not metadata:
            raise ValueError("Failed to generate SP metadata")

        return metadata.decode("utf-8") if isinstance(metadata, bytes) else metadata

    def generate_authn_request(self, provider: SAMLProvider) -> dict[str, str]:
        """
        Generate SAML AuthnRequest for SP-Initiated SSO flow.

        Creates a SAML AuthnRequest and returns the redirect URL with the encoded request.

        Args:
            provider: SAML Identity Provider configuration.

        Returns:
            Dictionary with 'redirect_url' and 'saml_request' keys.

        Raises:
            ValueError: If AuthnRequest generation fails.
        """
        # Build SAML settings with provider-specific IdP config
        settings = self._get_saml_settings(provider)

        # Create OneLogin SAML Auth object
        # Mock request dict (required by python3-saml but not used for AuthnRequest generation)
        request_data = {
            "https": "on",
            "http_host": "localhost",
            "script_name": "/api/auth/saml/acs",
            "get_data": {},
            "post_data": {},
        }

        auth = OneLogin_Saml2_Auth(request_data, settings)

        # Generate AuthnRequest and get redirect URL
        # The login() method returns the SSO URL with SAMLRequest parameter
        redirect_url = auth.login(return_to=None)

        # Extract SAMLRequest from URL for response
        # The redirect_url contains the full SSO URL with SAMLRequest parameter
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(redirect_url)
        params = parse_qs(parsed.query)
        saml_request = params.get("SAMLRequest", [""])[0]

        return {
            "redirect_url": redirect_url,
            "saml_request": saml_request,
        }

    def extract_issuer_from_response(
        self,
        saml_response: str,
    ) -> str:
        """
        Extract IdP entity ID (issuer) from SAML Response.

        Used for IdP-initiated SSO to identify which provider to use.

        Args:
            saml_response: Base64-encoded SAML Response.

        Returns:
            IdP entity ID (issuer) from the SAML Response.

        Raises:
            ValueError: If issuer cannot be extracted.
        """
        # Use a temporary settings object to parse the response
        settings = self._get_saml_settings()

        try:
            # Use OneLogin_Saml2_Response directly to parse the SAML response
            from onelogin.saml2.response import OneLogin_Saml2_Response

            response_obj = OneLogin_Saml2_Response(
                settings,
                saml_response,
            )

            issuer = response_obj.get_issuer()
            if not issuer:
                raise ValueError("Could not extract issuer from SAML Response")

            return issuer
        except Exception as exc:
            raise ValueError("Failed to extract issuer from SAML Response") from exc

    def process_saml_response(
        self,
        saml_response: str,
        provider: SAMLProvider,
        is_idp_initiated: bool = False,
    ) -> dict[str, Any]:
        """
        Process and validate SAML Response from IdP with comprehensive validation.

        Performs the following validation steps:
        1. Validates SAML signature using IdP certificate
        2. Checks assertion validity period (NotBefore, NotAfter)
        3. Verifies audience restriction matches SP entity ID
        4. Extracts user claims (email, name, groups)

        For IdP-initiated flow (is_idp_initiated=True):
        - Skips InResponseTo validation (no AuthnRequest was sent)
        - Still validates signature, audience, and timing

        Args:
            saml_response: Base64-encoded SAML Response.
            provider: SAML Identity Provider configuration.
            is_idp_initiated: True if this is IdP-initiated (unsolicited) SSO.

        Returns:
            Dictionary with user attributes and authentication status.

        Raises:
            ValueError: If SAML Response is invalid or validation fails.
        """
        # Build SAML settings with provider-specific IdP config
        settings = self._get_saml_settings(provider)

        # Create request data with SAML Response
        request_data = {
            "https": "on",
            "http_host": "localhost",
            "script_name": "/api/auth/saml/acs",
            "get_data": {},
            "post_data": {"SAMLResponse": saml_response},
        }

        auth = OneLogin_Saml2_Auth(request_data, settings)

        # Process the SAML Response (includes signature validation)
        # For IdP-initiated flow, we don't have a request ID to validate against
        try:
            auth.process_response(request_id=None if is_idp_initiated else None)
        except Exception as exc:
            raise ValueError("Invalid or malformed SAML response") from exc

        # Step 1: Check for signature validation errors
        errors = auth.get_errors()
        if errors:
            error_reason = auth.get_last_error_reason()
            raise ValueError(f"SAML authentication failed: {error_reason or ', '.join(errors)}")

        # Check if authenticated (signature must be valid)
        if not auth.is_authenticated():
            raise ValueError("SAML authentication failed: user not authenticated")

        # Extract user attributes
        attributes = auth.get_attributes()
        nameid = auth.get_nameid()

        return {
            "authenticated": True,
            "nameid": nameid,
            "attributes": attributes,
            "is_idp_initiated": is_idp_initiated,
        }

    def extract_user_attributes(
        self,
        saml_attributes: dict[str, list[str]],
        nameid: str,
    ) -> dict[str, str]:
        """
        Extract user attributes from SAML Response.

        Maps SAML attributes to user profile fields.
        This is a legacy method kept for backward compatibility.
        Use extract_user_claims() for new code.

        Args:
            saml_attributes: SAML attributes from IdP.
            nameid: SAML NameID (typically email).

        Returns:
            Dictionary with user email and name.

        Raises:
            ValueError: If required attributes are missing.
        """
        # Use extract_user_claims and return only email and name for compatibility
        claims = self.extract_user_claims(saml_attributes, nameid)
        return {
            "email": claims["email"],
            "name": claims["name"],
        }

    def create_or_update_session(
        self,
        db_session: Session,
        user_data: dict[str, str],
        organization_id: str,
        provider: SAMLProvider | None = None,
        saml_claims: dict[str, Any] | None = None,
        subject_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Create or update user session after successful SAML authentication.

        Creates a new user if they don't exist, or updates existing user's last login.
        Generates JWT session tokens using SessionService (Story 4.1).

        Story 2.3: Uses UserProvisioningService for JIT provisioning and
        external ID tracking when provider and saml_claims are provided.

        Args:
            db_session: Database session.
            user_data: User data from SAML (email, name).
            organization_id: Organization ID for the user.
            provider: Optional SAML provider for provisioning integration.
            saml_claims: Optional full SAML claims for provisioning.
            subject_id: Optional SAML subject ID (NameID).

        Returns:
            Dictionary with user_id, access_token, refresh_token, and expires_at.
        """
        # Use provisioning service if provider and claims are available (Story 2.3)
        if provider and saml_claims and subject_id:
            provisioning_service = UserProvisioningService(db_session)
            user = provisioning_service.provision_user_from_saml(
                saml_claims=saml_claims,
                idp_entity_id=provider.entity_id,
                subject_id=subject_id,
            )
        else:
            # Legacy path: direct user creation/update (Story 2.1/2.2 compatibility)
            email = user_data["email"]
            name = user_data["name"]

            # Find or create user
            user = db_session.query(User).filter(User.email == email).first()

            if user:
                # Update existing user
                user.name = name
                user.last_login_at = datetime.now(UTC)
            else:
                # Create new user
                user = User(
                    email=email,
                    name=name,
                    password_hash=self._generate_random_password_hash(),
                    email_verified=True,  # SAML users are pre-verified
                    status="active",
                    last_login_at=datetime.now(UTC),
                )
                db_session.add(user)

            db_session.commit()
            db_session.refresh(user)

        # Generate JWT session tokens using SessionService (Story 4.1)
        session_service = SessionService(db_session)
        roles = ["user"]
        if saml_claims:
            roles = [
                UserProvisioningService(db_session).assign_roles_from_groups(
                    saml_claims.get("groups", [])
                )
            ]

        session_data = session_service.create_session(
            user_id=user.id,
            email=user.email,
            roles=roles,
            ttl_hours=24,
        )

        return {
            "user_id": user.id,
            "session_token": session_data["access_token"],
            "refresh_token": session_data["refresh_token"],
            "expires_at": session_data["expires_at"],
        }

    def _generate_session_token(self) -> str:
        """Generate a secure random session token."""
        return secrets.token_urlsafe(32)

    def _generate_random_password_hash(self) -> str:
        """
        Generate a random password hash for SAML users.

        SAML users don't use password auth, but the field is required.
        """
        random_password = secrets.token_urlsafe(32)
        return hashlib.sha256(random_password.encode()).hexdigest()

    def validate_saml_signature(
        self,
        saml_response: str,
        provider: SAMLProvider,
    ) -> bool:
        """
        Validate SAML Response signature using IdP certificate.

        Verifies that the SAML Response was signed by the Identity Provider
        using the configured X.509 certificate.

        Args:
            saml_response: Base64-encoded SAML Response.
            provider: SAML Identity Provider configuration with x509_cert.

        Returns:
            True if signature is valid.

        Raises:
            ValueError: If signature validation fails.
        """
        # Build SAML settings with provider-specific IdP config
        settings = self._get_saml_settings(provider)

        # Create request data with SAML Response
        request_data = {
            "https": "on",
            "http_host": "localhost",
            "script_name": "/api/auth/saml/acs",
            "get_data": {},
            "post_data": {"SAMLResponse": saml_response},
        }

        auth = OneLogin_Saml2_Auth(request_data, settings)

        # Process the SAML Response (includes signature validation)
        auth.process_response()

        # Check for signature validation errors
        errors = auth.get_errors()
        if errors:
            error_reason = auth.get_last_error_reason()
            detail = error_reason or ", ".join(errors)
            raise ValueError(f"SAML signature validation failed: {detail}")

        # Check if authenticated (signature must be valid)
        if not auth.is_authenticated():
            raise ValueError("SAML signature validation failed: invalid signature")

        return True

    def check_assertion_validity(
        self,
        not_before: str,
        not_after: str,
    ) -> bool:
        """
        Check SAML assertion validity period.

        Validates that the current time is within the assertion's NotBefore
        and NotAfter time window.

        Args:
            not_before: ISO 8601 timestamp for NotBefore condition.
            not_after: ISO 8601 timestamp for NotAfter condition.

        Returns:
            True if assertion is currently valid.

        Raises:
            ValueError: If assertion is expired or not yet valid.
        """
        now = datetime.now(UTC)

        # Parse timestamps
        try:
            not_before_dt = datetime.fromisoformat(not_before.replace("Z", "+00:00"))
            not_after_dt = datetime.fromisoformat(not_after.replace("Z", "+00:00"))
        except (ValueError, AttributeError) as exc:
            raise ValueError(f"Invalid timestamp format in assertion: {exc}") from exc

        # Check if assertion is not yet valid
        if now < not_before_dt:
            raise ValueError(
                "Assertion not yet valid: current time "
                f"{now.isoformat()} is before NotBefore {not_before}"
            )

        # Check if assertion is expired
        if now > not_after_dt:
            raise ValueError(
                f"Assertion expired: current time {now.isoformat()} is after NotAfter {not_after}"
            )

        return True

    def verify_audience(
        self,
        audience: str,
    ) -> bool:
        """
        Verify SAML assertion audience restriction.

        Validates that the audience in the SAML assertion matches the
        Service Provider's entity ID.

        Args:
            audience: Audience value from SAML assertion.

        Returns:
            True if audience matches SP entity ID.

        Raises:
            ValueError: If audience does not match SP entity ID.
        """
        sp_entity_id = self._config["sp_entity_id"]

        if audience != sp_entity_id:
            raise ValueError(f"Audience mismatch: expected {sp_entity_id}, got {audience}")

        return True

    def extract_user_claims(
        self,
        saml_attributes: dict[str, list[str]],
        nameid: str,
    ) -> dict[str, Any]:
        """
        Extract user claims from SAML assertion attributes.

        Extracts standard SAML attributes including email, name, and groups.

        Args:
            saml_attributes: SAML attributes from IdP assertion.
            nameid: SAML NameID (typically email).

        Returns:
            Dictionary with email, name, and groups.

        Raises:
            ValueError: If required attributes are missing.
        """

        def first_value(*keys: str) -> str | None:
            for key in keys:
                values = saml_attributes.get(key)
                if values:
                    value = str(values[0]).strip()
                    if value:
                        return value
            return None

        # Support friendly names and common Azure AD claim URIs.
        email = first_value(
            "email",
            "emailaddress",
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
            "upn",
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn",
        ) or (nameid.strip() if nameid else None)

        if not email:
            raise ValueError("Email attribute is required but not provided in SAML assertion")

        name = first_value(
            "displayName",
            "display_name",
            "name",
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name",
            "cn",
        )
        if not name:
            first = (
                first_value(
                    "firstName",
                    "givenName",
                    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname",
                )
                or ""
            )
            last = (
                first_value(
                    "lastName",
                    "surname",
                    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname",
                )
                or ""
            )
            name = f"{first} {last}".strip() or email.split("@")[0]

        # Extract groups - optional attribute
        groups: list[str] = []
        for key in (
            "groups",
            "roles",
            "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups",
            "http://schemas.microsoft.com/ws/2008/06/identity/claims/role",
        ):
            for group in saml_attributes.get(key, []):
                value = str(group).strip()
                if value and value not in groups:
                    groups.append(value)

        return {
            "email": email,
            "name": name,
            "groups": groups,
        }

    def initiate_logout(
        self,
        provider: SAMLProvider,
        session_id: str,
        nameid: str,
    ) -> dict[str, str]:
        """
        Initiate SAML Single Logout (SLO) flow.

        Generates a SAML LogoutRequest and returns the redirect URL to IdP's SLO endpoint.
        The LogoutRequest includes the NameID from the original login session.

        Args:
            provider: SAML Identity Provider configuration.
            session_id: User session ID to be logged out.
            nameid: SAML NameID from original login (typically email).

        Returns:
            Dictionary with 'redirect_url' and 'saml_request' keys.

        Raises:
            ValueError: If LogoutRequest generation fails or provider has no SLO URL.
        """
        # Verify provider has SLO URL configured
        if not provider.slo_url:
            raise ValueError(f"Provider {provider.name} does not have SLO URL configured")

        # Build SAML settings with provider-specific IdP config
        settings = self._get_saml_settings(provider)

        # Create OneLogin SAML Auth object
        # Mock request dict (required by python3-saml)
        request_data = {
            "https": "on",
            "http_host": "localhost",
            "script_name": "/api/auth/saml/sls",
            "get_data": {},
            "post_data": {},
        }

        auth = OneLogin_Saml2_Auth(request_data, settings)

        # Generate LogoutRequest and get redirect URL
        # The logout() method returns the SLO URL with SAMLRequest parameter
        redirect_url = auth.logout(
            name_id=nameid,
            session_index=session_id,
            return_to=provider.id,
        )

        # Extract SAMLRequest from URL for response
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(redirect_url)
        params = parse_qs(parsed.query)
        saml_request = params.get("SAMLRequest", [""])[0]

        return {
            "redirect_url": redirect_url,
            "saml_request": saml_request,
        }

    def handle_logout_response(
        self,
        saml_response: str,
        provider: SAMLProvider,
    ) -> dict[str, bool]:
        """
        Process SAML LogoutResponse from Identity Provider.

        Validates the LogoutResponse to confirm the user was successfully
        logged out at the IdP.

        Args:
            saml_response: Base64-encoded SAML LogoutResponse.
            provider: SAML Identity Provider configuration.

        Returns:
            Dictionary with 'success' key indicating logout status.

        Raises:
            ValueError: If LogoutResponse validation fails.
        """
        # Build SAML settings with provider-specific IdP config
        settings = self._get_saml_settings(provider)

        # Create request data with SAML LogoutResponse
        request_data = {
            "https": "on",
            "http_host": "localhost",
            "script_name": "/api/auth/saml/sls",
            "get_data": {"SAMLResponse": saml_response},
            "post_data": {},
        }

        auth = OneLogin_Saml2_Auth(request_data, settings)

        # Process the SAML LogoutResponse
        auth.process_slo()

        # Check for errors
        errors = auth.get_errors()
        if errors:
            error_reason = auth.get_last_error_reason()
            raise ValueError(f"SAML logout failed: {error_reason or ', '.join(errors)}")

        return {
            "success": True,
        }
