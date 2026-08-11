"""
SAML Configuration Module

Provides SAML Service Provider configuration for SSO authentication.
Loads X.509 certificates and configures SAML endpoints.

Story 1.1 - SAML Service Provider Setup
"""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from app.core.config import get_settings

_API_SERVER_ROOT = Path(__file__).resolve().parents[2]
_CERTIFICATE_DIR = _API_SERVER_ROOT / "certs"


class SAMLConfig(TypedDict):
    """SAML Service Provider configuration."""

    sp_entity_id: str
    sp_acs_url: str
    sp_sls_url: str
    sp_x509_cert: str
    sp_private_key: str


def get_saml_config() -> SAMLConfig:
    """
    Build SAML configuration from environment settings.

    Returns:
        SAMLConfig with SP entity ID, ACS URL, SLS URL, and certificates.

    Raises:
        FileNotFoundError: If certificate files are not found.
        ValueError: If certificate files are empty.
    """
    settings = get_settings()
    api_base = str(settings.api_base_url).rstrip("/")

    cert_path = _CERTIFICATE_DIR / "saml_sp.crt"
    key_path = _CERTIFICATE_DIR / "saml_sp.key"

    if not cert_path.exists():
        raise FileNotFoundError(f"SAML SP certificate not found: {cert_path}")
    if not key_path.exists():
        raise FileNotFoundError(f"SAML SP private key not found: {key_path}")

    cert_content = cert_path.read_text().strip()
    key_content = key_path.read_text().strip()

    if not cert_content:
        raise ValueError(f"SAML SP certificate is empty: {cert_path}")
    if not key_content:
        raise ValueError(f"SAML SP private key is empty: {key_path}")

    return SAMLConfig(
        sp_entity_id=f"{api_base}/api/auth/saml/metadata",
        sp_acs_url=f"{api_base}/api/auth/saml/acs",
        sp_sls_url=f"{api_base}/api/auth/saml/sls",
        sp_x509_cert=cert_content,
        sp_private_key=key_content,
    )
