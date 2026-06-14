"""
API endpoints for autofix operations - Story 3.1 & 3.2: Secret Generation and Database Setup (Auto-Fix)

Provides endpoints to automatically generate and configure:
- Missing security secrets (Story 3.1)
- Database setup (migrations, admin user, configs) (Story 3.2)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db_session
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


class AutofixDatabaseResponse(BaseModel):
    """Response for database autofix operation - Story 3.2."""

    success: bool = Field(description="Whether the operation succeeded")
    migrations_run: bool = Field(description="Whether migrations were executed")
    admin_created: bool = Field(description="Whether admin user was created")
    admin_email: str | None = Field(
        description="Email of created admin user (if created)", default=None
    )
    admin_password: str | None = Field(
        description="Generated admin password (if created, save this!)", default=None
    )
    configs_created: list[str] = Field(
        description="List of configuration keys that were created"
    )
    message: str = Field(description="Human-readable result message")
    timestamp: str = Field(description="ISO timestamp of the operation")
    actions: list[str] = Field(description="List of actions taken (audit trail)")


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


@router.post(
    "/database",
    response_model=AutofixDatabaseResponse,
    summary="Auto-fix database setup (Story 3.2)",
)
def autofix_database(db: Session = Depends(get_db_session)) -> AutofixDatabaseResponse:
    """
    Automatically fix database setup issues.

    Story 3.2: Database Setup Auto-Fix

    This endpoint performs the following actions:
    1. Runs pending Alembic migrations to bring the database schema up to date
    2. Creates an initial admin user (admin@example.com) if no users exist
    3. Seeds default configuration values
    4. Returns an audit trail of all actions taken

    The operation is safe to run multiple times:
    - Migrations are only run if pending
    - Admin user is only created if no active users exist
    - Default configs are only created if they don't exist

    **IMPORTANT**: If an admin user is created, save the generated password!
    It will only be displayed once in this response.

    Returns:
        AutofixDatabaseResponse with details of actions taken

    Raises:
        HTTPException: If database operations fail
    """
    try:
        # Run database autofix service
        service = AutofixService()
        result = service.autofix_database(session=db)

        # Build response message
        if result["success"]:
            if result["admin_created"]:
                message = (
                    f"Database setup completed. Admin user created with email: {result['admin_email']}. "
                    f"SAVE THIS PASSWORD: {result['admin_password']}"
                )
            else:
                message = "Database setup completed successfully."
        else:
            message = "Database setup encountered issues. See actions for details."

        return AutofixDatabaseResponse(
            success=result["success"],
            migrations_run=result["migrations_run"],
            admin_created=result["admin_created"],
            admin_email=result["admin_email"],
            admin_password=result["admin_password"],
            configs_created=result["configs_created"],
            message=message,
            timestamp=result["timestamp"].isoformat(),
            actions=result["actions"],
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to autofix database setup: {e}"
        )
