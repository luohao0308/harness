"""
SAML Service Provider Implementation

Handles SAML Service Provider metadata generation and SSO operations.
Uses python3-saml (OneLogin SAML Python Toolkit) for SAML protocol support.

Story 1.1 - SAML Service Provider Setup
Story 2.1 - SP-Initiated SSO Flow
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.settings import OneLogin_Saml2_Settings
from sqlalchemy.orm import Session

from app.config.saml_config import get_saml_config
from app.db.models import SAMLProvider, User


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
                    "url": provider.slo_url if provider and provider.slo_url else "https://idp.example.com/slo",
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

        # get_sp_metadata() returns XML string
        if not metadata:
            raise ValueError("Failed to generate SP metadata")

        return metadata

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
            "server_port": "443",
            "get_data": {},
            "post_data": {},
        }

        auth = OneLogin_Saml2_Auth(request_data, settings.to_dict())

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

    def process_saml_response(
        self,
        saml_response: str,
        provider: SAMLProvider,
    ) -> dict[str, Any]:
        """
        Process and validate SAML Response from IdP.

        Args:
            saml_response: Base64-encoded SAML Response.
            provider: SAML Identity Provider configuration.

        Returns:
            Dictionary with user attributes and authentication status.

        Raises:
            ValueError: If SAML Response is invalid or authentication failed.
        """
        # Build SAML settings with provider-specific IdP config
        settings = self._get_saml_settings(provider)

        # Create request data with SAML Response
        request_data = {
            "https": "on",
            "http_host": "localhost",
            "script_name": "/api/auth/saml/acs",
            "server_port": "443",
            "get_data": {},
            "post_data": {"SAMLResponse": saml_response},
        }

        auth = OneLogin_Saml2_Auth(request_data, settings.to_dict())

        # Process the SAML Response
        auth.process_response()

        # Check for errors
        errors = auth.get_errors()
        if errors:
            error_reason = auth.get_last_error_reason()
            raise ValueError(f"SAML authentication failed: {error_reason or ', '.join(errors)}")

        # Check if authenticated
        if not auth.is_authenticated():
            raise ValueError("SAML authentication failed: user not authenticated")

        # Extract user attributes
        attributes = auth.get_attributes()
        nameid = auth.get_nameid()

        return {
            "authenticated": True,
            "nameid": nameid,
            "attributes": attributes,
        }

    def extract_user_attributes(
        self,
        saml_attributes: dict[str, list[str]],
        nameid: str,
    ) -> dict[str, str]:
        """
        Extract user attributes from SAML Response.

        Maps SAML attributes to user profile fields.

        Args:
            saml_attributes: SAML attributes from IdP.
            nameid: SAML NameID (typically email).

        Returns:
            Dictionary with user email and name.

        Raises:
            ValueError: If required attributes are missing.
        """
        # Extract email - prefer email attribute, fall back to nameid
        email = None
        if "email" in saml_attributes and saml_attributes["email"]:
            email = saml_attributes["email"][0]
        elif nameid:
            email = nameid

        if not email:
            raise ValueError("Email attribute is required but not provided in SAML Response")

        # Extract name - try different attribute combinations
        name = None

        # Option 1: displayName
        if "displayName" in saml_attributes and saml_attributes["displayName"]:
            name = saml_attributes["displayName"][0]
        # Option 2: firstName + lastName
        elif "firstName" in saml_attributes and "lastName" in saml_attributes:
            first = saml_attributes.get("firstName", [""])[0]
            last = saml_attributes.get("lastName", [""])[0]
            name = f"{first} {last}".strip()
        # Option 3: cn (common name)
        elif "cn" in saml_attributes and saml_attributes["cn"]:
            name = saml_attributes["cn"][0]
        # Option 4: Use email as name
        else:
            name = email.split("@")[0]

        return {
            "email": email,
            "name": name,
        }

    def create_or_update_session(
        self,
        db_session: Session,
        user_data: dict[str, str],
        organization_id: str,
    ) -> dict[str, Any]:
        """
        Create or update user session after successful SAML authentication.

        Creates a new user if they don't exist, or updates existing user's last login.
        Generates a session token for the user.

        Args:
            db_session: Database session.
            user_data: User data from SAML (email, name).
            organization_id: Organization ID for the user.

        Returns:
            Dictionary with user_id, session_token, and expires_at.
        """
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

        # Generate session token
        session_token = self._generate_session_token()
        expires_at = datetime.now(UTC) + timedelta(hours=24)

        return {
            "user_id": user.id,
            "session_token": session_token,
            "expires_at": expires_at.isoformat(),
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

