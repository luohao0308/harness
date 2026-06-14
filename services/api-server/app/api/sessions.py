"""
Session Management API Endpoints

Provides endpoints for session lifecycle operations: validation, refresh, and logout.

Story 4.1 - SSO Session Lifecycle Management
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.services.session_service import SessionService

router = APIRouter(prefix="/auth/sessions", tags=["auth"])

DbSession = Annotated[Session, Depends(get_db_session)]


# Pydantic models for request/response
class SessionValidateResponse(BaseModel):
    """Response model for session validation."""

    user_id: str = Field(..., description="User ID")
    email: str = Field(..., description="User email")
    roles: list[str] = Field(..., description="User roles")
    expires_at: int = Field(..., description="Token expiration timestamp")


class SessionRefreshRequest(BaseModel):
    """Request model for session refresh."""

    refresh_token: str = Field(..., description="Refresh token")


class SessionRefreshResponse(BaseModel):
    """Response model for session refresh."""

    access_token: str = Field(..., description="New access token")
    refresh_token: str = Field(..., description="New refresh token")
    expires_at: str = Field(..., description="Token expiration ISO timestamp")
    token_type: str = Field(default="Bearer", description="Token type")


class SessionRevokeResponse(BaseModel):
    """Response model for session revocation."""

    success: bool = Field(..., description="Whether revocation succeeded")
    message: str = Field(..., description="Status message")


def get_token_from_header(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """
    Extract JWT token from Authorization header.

    Args:
        authorization: Authorization header value.

    Returns:
        JWT token string.

    Raises:
        HTTPException: 401 if header is missing or malformed.
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header",
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Invalid Authorization header format. Expected: Bearer <token>",
        )

    return parts[1]


@router.get(
    "/current",
    response_model=SessionValidateResponse,
    summary="Validate Current Session",
    description=(
        "Validates the current session token and returns user information. "
        "Checks JWT signature, expiration, and database session status."
    ),
)
async def validate_current_session(
    token: Annotated[str, Depends(get_token_from_header)],
    db: DbSession,
) -> SessionValidateResponse:
    """
    Validate current session and return user info.

    Extracts JWT token from Authorization header, validates it,
    and returns user claims if valid.

    Args:
        token: JWT token from Authorization header.
        db: Database session.

    Returns:
        User information from validated token.

    Raises:
        HTTPException: 401 if token is invalid, expired, or revoked.
    """
    try:
        service = SessionService(db)
        claims = service.validate_token(token)

        return SessionValidateResponse(
            user_id=claims["user_id"],
            email=claims["email"],
            roles=claims.get("roles", ["user"]),
            expires_at=claims["exp"],
        )

    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=f"Token validation failed: {e}",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to validate session: {e}",
        ) from e


@router.post(
    "/refresh",
    response_model=SessionRefreshResponse,
    summary="Refresh Session",
    description=(
        "Refreshes an existing session by issuing new access and refresh tokens. "
        "Extends session lifetime by the configured TTL (default 24 hours)."
    ),
)
async def refresh_session(
    refresh_request: SessionRefreshRequest,
    db: DbSession,
) -> SessionRefreshResponse:
    """
    Refresh session and issue new tokens.

    Validates refresh token and generates new access and refresh tokens
    with extended expiration time.

    Args:
        refresh_request: Contains refresh_token.
        db: Database session.

    Returns:
        New access and refresh tokens with updated expiration.

    Raises:
        HTTPException: 401 if refresh token is invalid or expired.
    """
    try:
        service = SessionService(db)
        result = service.refresh_session(refresh_request.refresh_token)

        return SessionRefreshResponse(
            access_token=result["access_token"],
            refresh_token=result["refresh_token"],
            expires_at=result["expires_at"],
            token_type=result["token_type"],
        )

    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=f"Token refresh failed: {e}",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to refresh session: {e}",
        ) from e


@router.delete(
    "/current",
    response_model=SessionRevokeResponse,
    summary="Logout (Revoke Current Session)",
    description=(
        "Revokes the current session, effectively logging out the user. "
        "The session token will no longer be valid for authentication."
    ),
)
async def revoke_current_session(
    token: Annotated[str, Depends(get_token_from_header)],
    db: DbSession,
) -> SessionRevokeResponse:
    """
    Revoke current session (logout).

    Extracts session ID from JWT token and marks the session as revoked
    in the database. The token will fail validation after revocation.

    Args:
        token: JWT token from Authorization header.
        db: Database session.

    Returns:
        Success status and message.

    Raises:
        HTTPException: 401 if token is invalid, 404 if session not found.
    """
    try:
        # First validate token to extract session ID
        service = SessionService(db)
        claims = service.validate_token(token)
        session_id = claims["jti"]

        # Revoke the session
        success = service.revoke_session(session_id)

        if not success:
            raise HTTPException(
                status_code=404,
                detail="Session not found",
            )

        return SessionRevokeResponse(
            success=True,
            message="Session revoked successfully",
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=f"Token validation failed: {e}",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to revoke session: {e}",
        ) from e
