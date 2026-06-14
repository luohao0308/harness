"""
SAML Authentication Endpoints

Provides SAML Service Provider endpoints for SSO authentication.
Serves SP metadata and handles SAML authentication flows.

Story 1.1 - SAML Service Provider Setup
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import PlainTextResponse

from app.services.saml_service import SAMLService

router = APIRouter(prefix="/auth/saml", tags=["auth"])


@router.get(
    "/metadata",
    response_class=PlainTextResponse,
    summary="Get SAML SP Metadata",
    description=(
        "Returns SAML Service Provider metadata XML. "
        "Identity Providers use this metadata to configure SSO integration. "
        "Contains entity ID, ACS URL, SLS URL, and X.509 certificate."
    ),
)
async def get_saml_metadata() -> str:
    """
    Serve SAML Service Provider metadata XML.

    This endpoint provides the SP metadata that Identity Providers need
    to configure SAML SSO integration. The metadata includes:
    - Entity ID (unique identifier for this SP)
    - Assertion Consumer Service (ACS) URL (where SAML responses are posted)
    - Single Logout Service (SLS) URL (for logout operations)
    - X.509 certificate (for signature verification)

    Returns:
        XML string containing complete SAML SP metadata.

    Raises:
        HTTPException: 500 if metadata generation fails.
    """
    try:
        service = SAMLService()
        metadata_xml = service.generate_sp_metadata()
        return metadata_xml
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=500,
            detail=f"SAML configuration error: {e}",
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=500,
            detail=f"SAML metadata generation error: {e}",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate SAML metadata: {e}",
        ) from e
