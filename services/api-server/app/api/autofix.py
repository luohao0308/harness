"""
API endpoints for autofix operations - Story 3.1: Secret Generation (Auto-Fix)

Provides endpoints to automatically generate and configure missing security secrets.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.autofix_service import AutofixService

router = APIRouter(prefix="/onboarding/autofix", tags=["onboarding"])


class AutofixSecretsResponse(BaseModel):
    """Response for secret autofix operation."""

    success: bool = Field(description="Whether the operation succeeded")
    added_secrets: list[str] = Field(description="List of secrets that were added")
    jwt_secret_added: bool = Field(description="Whether JWT secret was generated and added")
    encryption_key_added: bool = Field(
        description="Whether encryption key was generated and added"
    )
    message: str = Field(description="Human-readable result message")
    timestamp: str = Field(description="ISO timestamp of the operation")


@router.post(
    "/secrets",
    response_model=AutofixSecretsResponse,
    summary="Auto-generate missing secrets (Story 3.1)",
)
def autofix_secrets() -> AutofixSecretsResponse:
    """
    Automatically generate and configure missing security secrets.

    Story 3.1: Secret Generation (Auto-Fix)

    This endpoint:
    1. Generates AUTH_JWT_SECRET if missing (64 bytes, base64 encoded)
    2. Generates HARNESS_SECRET_ENCRYPTION_KEY if missing (32 bytes, Fernet format)
    3. Updates .env file without overwriting existing secrets
    4. Returns audit trail of actions taken

    The operation is idempotent - it will not overwrite existing secrets.

    Returns:
        AutofixSecretsResponse with details of what was generated and added

    Raises:
        HTTPException: If .env file cannot be found or written
    """
    # Locate .env file (assume it's in the api-server directory)
    env_path = Path(__file__).parent.parent.parent / ".env"

    if not env_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f".env file not found at {env_path}. Please create it first."
        )

    try:
        # Run autofix service
        service = AutofixService()
        result = service.autofix_secrets(env_path=str(env_path))

        # Build response message
        if not result["added_secrets"]:
            message = "All required secrets already exist. No changes made."
        else:
            secrets_list = ", ".join(result["added_secrets"])
            message = f"Successfully generated and added: {secrets_list}"

        return AutofixSecretsResponse(
            success=True,
            added_secrets=result["added_secrets"],
            jwt_secret_added=result["jwt_secret_added"],
            encryption_key_added=result["encryption_key_added"],
            message=message,
            timestamp=result["timestamp"].isoformat(),
        )

    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied when writing to .env file: {e}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to autofix secrets: {e}"
        )
