"""
SAML Service Provider Implementation

Handles SAML Service Provider metadata generation and SSO operations.
Uses python3-saml (OneLogin SAML Python Toolkit) for SAML protocol support.

Story 1.1 - SAML Service Provider Setup
"""
from __future__ import annotations

from typing import Any

from onelogin.saml2.settings import OneLogin_Saml2_Settings

from app.config.saml_config import get_saml_config


class SAMLService:
    """
    SAML Service Provider operations.

    Generates and serves SAML SP metadata XML for IdP integration.
    """

    def __init__(self) -> None:
        """Initialize SAML service with configuration."""
        self._config = get_saml_config()
        self._settings: OneLogin_Saml2_Settings | None = None

    def _get_saml_settings(self) -> OneLogin_Saml2_Settings:
        """
        Build OneLogin SAML settings from configuration.

        Returns:
            OneLogin_Saml2_Settings instance configured for this SP.
        """
        if self._settings is None:
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
                # IdP settings will be loaded dynamically per provider
                "idp": {
                    "entityId": "https://idp.example.com/metadata",
                    "singleSignOnService": {
                        "url": "https://idp.example.com/sso",
                        "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
                    },
                    "singleLogoutService": {
                        "url": "https://idp.example.com/slo",
                        "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
                    },
                    "x509cert": "",
                },
            }
            self._settings = OneLogin_Saml2_Settings(settings_dict)
        return self._settings

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
