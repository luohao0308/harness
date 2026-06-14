"""
SAML Authentication Endpoints

Provides SAML Service Provider endpoints for SSO authentication.
Serves SP metadata and handles SAML authentication flows.

Story 1.1 - SAML Service Provider Setup
Story 1.2 - IdP Configuration Management
Story 2.1 - SP-Initiated SSO Flow
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.services.saml_provider_service import SAMLProviderService
from app.services.saml_service import SAMLService

router = APIRouter(prefix="/auth/saml", tags=["auth"])

DbSession = Annotated[Session, Depends(get_db_session)]


# Pydantic models for request/response
class SAMLProviderCreate(BaseModel):
    """Request model for creating SAML provider."""

    organization_id: str = Field(..., description="Organization ID")
    name: str = Field(..., description="Provider name")
    entity_id: str = Field(..., description="IdP entity ID")
    sso_url: str = Field(..., description="SSO service URL")
    slo_url: str | None = Field(None, description="SLO service URL (optional)")
    x509_cert: str = Field(..., description="X.509 certificate in PEM format")
    is_active: bool = Field(True, description="Whether provider is active")


class SAMLProviderUpdate(BaseModel):
    """Request model for updating SAML provider."""

    name: str | None = Field(None, description="Provider name")
    entity_id: str | None = Field(None, description="IdP entity ID")
    sso_url: str | None = Field(None, description="SSO service URL")
    slo_url: str | None = Field(None, description="SLO service URL")
    x509_cert: str | None = Field(None, description="X.509 certificate")
    is_active: bool | None = Field(None, description="Whether provider is active")


class SAMLProviderResponse(BaseModel):
    """Response model for SAML provider."""

    id: str
    organization_id: str
    name: str
    entity_id: str
    sso_url: str
    slo_url: str | None
    x509_cert: str
    is_active: bool
    created_at: str
    updated_at: str

    model_config = ConfigDict(from_attributes=True)


class SAMLLoginRequest(BaseModel):
    """Request model for initiating SAML SSO."""

    provider_id: str = Field(..., description="SAML provider ID")


class SAMLLoginResponse(BaseModel):
    """Response model for SAML SSO initiation."""

    redirect_url: str = Field(..., description="IdP SSO URL with SAMLRequest")


class SAMLACSResponse(BaseModel):
    """Response model for SAML ACS (Assertion Consumer Service)."""

    user: dict[str, Any] = Field(..., description="User information")
    session_token: str = Field(..., description="Session token")
    expires_at: str = Field(..., description="Token expiration timestamp")


# SAML SSO Endpoints (Story 2.1)


@router.post(
    "/login",
    response_model=SAMLLoginResponse,
    summary="Initiate SAML SSO",
    description=(
        "Initiates SP-Initiated SAML SSO flow. "
        "Generates SAML AuthnRequest and returns IdP redirect URL. "
        "Client should redirect user to the returned URL."
    ),
)
async def saml_login(
    login_request: SAMLLoginRequest,
    db: DbSession,
) -> SAMLLoginResponse:
    """
    Initiate SAML SSO login flow.

    Generates a SAML AuthnRequest and returns the IdP SSO URL
    where the user should be redirected for authentication.

    Args:
        login_request: Contains provider_id.
        db: Database session.

    Returns:
        Redirect URL with encoded SAMLRequest parameter.

    Raises:
        HTTPException: 404 if provider not found, 400 if provider inactive.
    """
    try:
        # Get provider
        provider_service = SAMLProviderService(db)
        provider = provider_service.get_provider_by_id(login_request.provider_id)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=f"SAML provider with ID {login_request.provider_id} not found",
            )

        # Check if provider is active
        if not provider.is_active:
            raise HTTPException(
                status_code=400,
                detail="SAML provider is inactive",
            )

        # Generate AuthnRequest
        saml_service = SAMLService()
        authn_data = saml_service.generate_authn_request(provider)

        return SAMLLoginResponse(redirect_url=authn_data["redirect_url"])

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initiate SAML SSO: {e}",
        ) from e


@router.post(
    "/acs",
    response_model=SAMLACSResponse,
    summary="SAML Assertion Consumer Service",
    description=(
        "Handles SAML Response from IdP after user authentication. "
        "Validates the SAML assertion, extracts user attributes, "
        "provisions/updates the user, and creates a session."
    ),
)
async def saml_acs(
    saml_response: Annotated[str, Form(alias="SAMLResponse")],
    relay_state: Annotated[str | None, Form(alias="RelayState")] = None,
    db: DbSession = Depends(get_db_session),
) -> SAMLACSResponse:
    """
    Process SAML Response from Identity Provider.

    This endpoint receives the SAML Response after the user authenticates
    at the IdP. It validates the response, extracts user attributes,
    provisions/updates the user (Story 2.3), and creates a session.

    Args:
        saml_response: Base64-encoded SAML Response from IdP.
        relay_state: Optional relay state (used to pass provider_id).
        db: Database session.

    Returns:
        User information and session token.

    Raises:
        HTTPException: 400/401 if validation fails or authentication unsuccessful.
    """
    try:
        # Get provider from relay state
        if not relay_state:
            raise HTTPException(
                status_code=400,
                detail="RelayState parameter is required",
            )

        provider_service = SAMLProviderService(db)
        provider = provider_service.get_provider_by_id(relay_state)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=f"SAML provider with ID {relay_state} not found",
            )

        # Process SAML Response
        saml_service = SAMLService()
        auth_result = saml_service.process_saml_response(saml_response, provider)

        if not auth_result["authenticated"]:
            raise HTTPException(
                status_code=401,
                detail="SAML authentication failed",
            )

        # Extract user claims (Story 2.2)
        user_claims = saml_service.extract_user_claims(
            auth_result["attributes"],
            auth_result["nameid"],
        )

        # Create or update session with provisioning (Story 2.3)
        session_data = saml_service.create_or_update_session(
            db,
            user_data={"email": user_claims["email"], "name": user_claims["name"]},
            organization_id=provider.organization_id,
            provider=provider,
            saml_claims=user_claims,
            subject_id=auth_result["nameid"],
        )

        return SAMLACSResponse(
            user={
                "id": session_data["user_id"],
                "email": user_claims["email"],
                "name": user_claims["name"],
            },
            session_token=session_data["session_token"],
            expires_at=session_data["expires_at"],
        )

    except HTTPException:
        raise
    except ValueError as e:
        # SAML validation errors
        error_msg = str(e)
        if "authentication failed" in error_msg.lower():
            raise HTTPException(status_code=401, detail=error_msg) from e
        raise HTTPException(status_code=400, detail=error_msg) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process SAML Response: {e}",
        ) from e


# SAML Metadata Endpoint (Story 1.1)


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


# SAML Provider CRUD Endpoints (Story 1.2)


@router.post(
    "/providers",
    response_model=SAMLProviderResponse,
    status_code=201,
    summary="Create SAML Provider",
    description="Create a new SAML Identity Provider configuration for an organization.",
)
async def create_saml_provider(
    provider_data: SAMLProviderCreate,
    db: DbSession,
) -> Any:
    """
    Create a new SAML Identity Provider configuration.

    Validates IdP metadata including entity ID, SSO URL, and X.509 certificate.
    Organizations can configure multiple IdPs for SSO.

    Args:
        provider_data: SAML provider configuration.
        db: Database session.

    Returns:
        Created SAML provider with ID and timestamps.

    Raises:
        HTTPException: 400 if validation fails.
    """
    try:
        service = SAMLProviderService(db)
        provider = service.create_provider(
            organization_id=provider_data.organization_id,
            name=provider_data.name,
            entity_id=provider_data.entity_id,
            sso_url=provider_data.sso_url,
            slo_url=provider_data.slo_url,
            x509_cert=provider_data.x509_cert,
            is_active=provider_data.is_active,
        )

        return SAMLProviderResponse(
            id=provider.id,
            organization_id=provider.organization_id,
            name=provider.name,
            entity_id=provider.entity_id,
            sso_url=provider.sso_url,
            slo_url=provider.slo_url,
            x509_cert=provider.x509_cert,
            is_active=provider.is_active,
            created_at=provider.created_at.isoformat(),
            updated_at=provider.updated_at.isoformat(),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create SAML provider: {e}",
        ) from e


@router.get(
    "/providers",
    response_model=list[SAMLProviderResponse],
    summary="List SAML Providers",
    description="List all SAML providers for an organization.",
)
async def list_saml_providers(
    organization_id: str,
    db: DbSession,
    active_only: bool = False,
) -> list[SAMLProviderResponse]:
    """
    List all SAML providers for an organization.

    Args:
        organization_id: Organization ID to filter by.
        active_only: If True, only return active providers.
        db: Database session.

    Returns:
        List of SAML providers.
    """
    try:
        service = SAMLProviderService(db)
        providers = service.list_providers_by_organization(
            organization_id=organization_id,
            active_only=active_only,
        )

        return [
            SAMLProviderResponse(
                id=p.id,
                organization_id=p.organization_id,
                name=p.name,
                entity_id=p.entity_id,
                sso_url=p.sso_url,
                slo_url=p.slo_url,
                x509_cert=p.x509_cert,
                is_active=p.is_active,
                created_at=p.created_at.isoformat(),
                updated_at=p.updated_at.isoformat(),
            )
            for p in providers
        ]
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list SAML providers: {e}",
        ) from e


@router.get(
    "/providers/{provider_id}",
    response_model=SAMLProviderResponse,
    summary="Get SAML Provider",
    description="Get a specific SAML provider by ID.",
)
async def get_saml_provider(
    provider_id: str,
    db: DbSession,
) -> SAMLProviderResponse:
    """
    Retrieve a specific SAML provider by ID.

    Args:
        provider_id: Provider ID to retrieve.
        db: Database session.

    Returns:
        SAML provider details.

    Raises:
        HTTPException: 404 if provider not found.
    """
    try:
        service = SAMLProviderService(db)
        provider = service.get_provider_by_id(provider_id)

        if not provider:
            raise HTTPException(
                status_code=404,
                detail=f"SAML provider with ID {provider_id} not found",
            )

        return SAMLProviderResponse(
            id=provider.id,
            organization_id=provider.organization_id,
            name=provider.name,
            entity_id=provider.entity_id,
            sso_url=provider.sso_url,
            slo_url=provider.slo_url,
            x509_cert=provider.x509_cert,
            is_active=provider.is_active,
            created_at=provider.created_at.isoformat(),
            updated_at=provider.updated_at.isoformat(),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get SAML provider: {e}",
        ) from e


@router.put(
    "/providers/{provider_id}",
    response_model=SAMLProviderResponse,
    summary="Update SAML Provider",
    description="Update an existing SAML provider configuration.",
)
async def update_saml_provider(
    provider_id: str,
    provider_data: SAMLProviderUpdate,
    db: DbSession,
) -> SAMLProviderResponse:
    """
    Update an existing SAML provider.

    Args:
        provider_id: Provider ID to update.
        provider_data: Fields to update.
        db: Database session.

    Returns:
        Updated SAML provider.

    Raises:
        HTTPException: 404 if provider not found, 400 if validation fails.
    """
    try:
        service = SAMLProviderService(db)

        # Build updates dict from non-None fields
        updates = {}
        if provider_data.name is not None:
            updates["name"] = provider_data.name
        if provider_data.entity_id is not None:
            updates["entity_id"] = provider_data.entity_id
        if provider_data.sso_url is not None:
            updates["sso_url"] = provider_data.sso_url
        if provider_data.slo_url is not None:
            updates["slo_url"] = provider_data.slo_url
        if provider_data.x509_cert is not None:
            updates["x509_cert"] = provider_data.x509_cert
        if provider_data.is_active is not None:
            updates["is_active"] = provider_data.is_active

        provider = service.update_provider(provider_id, **updates)

        return SAMLProviderResponse(
            id=provider.id,
            organization_id=provider.organization_id,
            name=provider.name,
            entity_id=provider.entity_id,
            sso_url=provider.sso_url,
            slo_url=provider.slo_url,
            x509_cert=provider.x509_cert,
            is_active=provider.is_active,
            created_at=provider.created_at.isoformat(),
            updated_at=provider.updated_at.isoformat(),
        )
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail=error_msg) from e
        raise HTTPException(status_code=400, detail=error_msg) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update SAML provider: {e}",
        ) from e


@router.delete(
    "/providers/{provider_id}",
    status_code=204,
    summary="Delete SAML Provider",
    description="Delete a SAML provider configuration.",
)
async def delete_saml_provider(
    provider_id: str,
    db: DbSession,
) -> Response:
    """
    Delete a SAML provider.

    Args:
        provider_id: Provider ID to delete.
        db: Database session.

    Returns:
        Empty response with 204 status.

    Raises:
        HTTPException: 404 if provider not found.
    """
    try:
        service = SAMLProviderService(db)
        deleted = service.delete_provider(provider_id)

        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=f"SAML provider with ID {provider_id} not found",
            )

        return Response(status_code=204)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete SAML provider: {e}",
        ) from e
