"""
Session Service for SSO Session Lifecycle Management

Handles JWT token generation, session CRUD operations, token validation,
refresh logic, and session expiration for authenticated users.

Story 4.1 - SSO Session Lifecycle Management
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import UserSession


class SessionService:
    """
    Service for managing user authentication sessions.

    Provides JWT token generation, validation, refresh, and revocation
    with database-backed session storage.
    """

    def __init__(self, db_session: Session) -> None:
        """
        Initialize session service.

        Args:
            db_session: Database session for persistence.
        """
        self.db = db_session
        self.settings = get_settings()

    def create_session(
        self,
        user_id: str,
        email: str,
        roles: list[str] | None = None,
        ttl_hours: int = 24,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Create new session with JWT tokens.

        Generates access and refresh JWT tokens with user claims and stores
        session metadata in the database.

        Args:
            user_id: User ID to create session for.
            email: User email address.
            roles: Optional list of user roles (default: ["user"]).
            ttl_hours: Token TTL in hours (default: 24).
            metadata: Optional metadata (IP, user agent, etc.).

        Returns:
            Dictionary with access_token, refresh_token, expires_at, token_type.
        """
        if roles is None:
            roles = ["user"]

        # Generate session ID
        session_id = self._generate_uuid()

        # Calculate expiration
        now = datetime.now(UTC)
        expires_at = now + timedelta(hours=ttl_hours)
        refresh_expires_at = now + timedelta(days=30)

        # Generate JWT tokens
        access_token = self._generate_access_token(
            session_id=session_id,
            user_id=user_id,
            email=email,
            roles=roles,
            expires_at=expires_at,
        )

        refresh_token = self._generate_refresh_token(
            session_id=session_id,
            user_id=user_id,
            expires_at=refresh_expires_at,
        )

        # Hash tokens for storage
        token_hash = self._hash_token(access_token)
        refresh_token_hash = self._hash_token(refresh_token)

        # Create session record
        session = UserSession(
            id=session_id,
            user_id=user_id,
            email=email,
            token_hash=token_hash,
            refresh_token_hash=refresh_token_hash,
            roles_json=roles,
            metadata_json=metadata or {},
            expires_at=expires_at,
            created_at=now,
        )

        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at.isoformat(),
            "token_type": "Bearer",
        }

    def validate_token(self, token: str) -> dict[str, Any]:
        """
        Validate JWT access token and check session status.

        Decodes JWT, verifies signature, checks expiration, and validates
        against database session (revocation, expiration).

        Args:
            token: JWT access token to validate.

        Returns:
            Token claims including user_id, email, roles.

        Raises:
            ValueError: If token is invalid, expired, or revoked.
        """
        try:
            # Decode and verify JWT signature
            claims = jwt.decode(
                token,
                self.settings.auth_jwt_secret,
                algorithms=["HS256"],
            )

            # Extract session ID from jti claim
            session_id = claims.get("jti")
            if not session_id:
                raise ValueError("Invalid token: missing session ID")

            # Check database session status
            session = self.get_session(session_id)
            if not session:
                raise ValueError("Session not found")

            # Check if session is revoked
            if session.revoked_at is not None:
                raise ValueError("Session has been revoked")

            # Check if session has expired (DB expiration)
            if self._as_utc(session.expires_at) < datetime.now(UTC):
                raise ValueError("Session has expired")

            # Update last used timestamp
            session.last_used_at = datetime.now(UTC)
            self.db.commit()

            return claims

        except jwt.ExpiredSignatureError as e:
            raise ValueError("Token has expired") from e
        except jwt.InvalidTokenError as e:
            raise ValueError("Invalid token") from e

    def refresh_session(self, refresh_token: str) -> dict[str, Any]:
        """
        Refresh session and issue new tokens.

        Validates refresh token and extends session lifetime by issuing
        new access and refresh tokens.

        Args:
            refresh_token: JWT refresh token.

        Returns:
            Dictionary with new access_token, refresh_token, expires_at.

        Raises:
            ValueError: If refresh token is invalid or session is revoked.
        """
        try:
            # Decode refresh token
            claims = jwt.decode(
                refresh_token,
                self.settings.auth_jwt_secret,
                algorithms=["HS256"],
            )

            # Verify token type
            if claims.get("token_type") != "refresh":
                raise ValueError("Invalid token type: expected refresh token")

            # Get session ID
            session_id = claims.get("jti")
            if not session_id:
                raise ValueError("Invalid token: missing session ID")

            # Check database session status
            session = self.get_session(session_id)
            if not session:
                raise ValueError("Session not found")

            # Check if session is revoked
            if session.revoked_at is not None:
                raise ValueError("Session has been revoked")

            # Extend session expiration
            now = datetime.now(UTC)
            new_expires_at = now + timedelta(hours=24)
            refresh_expires_at = now + timedelta(days=30)

            # Generate new tokens
            new_access_token = self._generate_access_token(
                session_id=session.id,
                user_id=session.user_id,
                email=session.email,
                roles=session.roles_json,
                expires_at=new_expires_at,
            )

            new_refresh_token = self._generate_refresh_token(
                session_id=session.id,
                user_id=session.user_id,
                expires_at=refresh_expires_at,
            )

            # Update session with new token hashes and expiration
            session.token_hash = self._hash_token(new_access_token)
            session.refresh_token_hash = self._hash_token(new_refresh_token)
            session.expires_at = new_expires_at
            session.last_used_at = now

            self.db.commit()

            return {
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
                "expires_at": new_expires_at.isoformat(),
                "token_type": "Bearer",
            }

        except jwt.ExpiredSignatureError as e:
            raise ValueError("Refresh token has expired") from e
        except jwt.InvalidTokenError as e:
            raise ValueError("Invalid refresh token") from e

    def revoke_session(self, session_id: str) -> bool:
        """
        Revoke session (logout).

        Marks session as revoked, preventing further token validation.

        Args:
            session_id: Session ID to revoke.

        Returns:
            True if session was revoked, False if not found.
        """
        session = self.get_session(session_id)
        if not session or session.revoked_at is not None:
            return False

        session.revoked_at = datetime.now(UTC)
        self.db.commit()

        return True

    def validate_session(self, session_id: str) -> bool:
        """Return whether a persisted session is active and unexpired."""
        session = self.get_session(session_id)
        if not session or session.revoked_at is not None:
            return False
        return self._as_utc(session.expires_at) > datetime.now(UTC)

    def get_session(self, session_id: str) -> UserSession | None:
        """
        Retrieve session by ID.

        Args:
            session_id: Session ID to retrieve.

        Returns:
            UserSession model or None if not found.
        """
        return self.db.query(UserSession).filter(UserSession.id == session_id).first()

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        """Normalize database datetimes because SQLite drops timezone metadata."""
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _generate_access_token(
        self,
        session_id: str,
        user_id: str,
        email: str,
        roles: list[str],
        expires_at: datetime,
    ) -> str:
        """
        Generate JWT access token with user claims.

        Args:
            session_id: Session ID (stored in jti claim).
            user_id: User ID.
            email: User email.
            roles: User roles.
            expires_at: Token expiration time.

        Returns:
            Encoded JWT access token.
        """
        now = datetime.now(UTC)
        payload = {
            "user_id": user_id,
            "email": email,
            "roles": roles,
            "token_type": "access",
            "exp": int(expires_at.timestamp()),
            "iat": int(now.timestamp()),
            "jti": session_id,
        }

        return jwt.encode(
            payload,
            self.settings.auth_jwt_secret,
            algorithm="HS256",
        )

    def _generate_refresh_token(
        self,
        session_id: str,
        user_id: str,
        expires_at: datetime,
    ) -> str:
        """
        Generate JWT refresh token.

        Args:
            session_id: Session ID (stored in jti claim).
            user_id: User ID.
            expires_at: Token expiration time.

        Returns:
            Encoded JWT refresh token.
        """
        now = datetime.now(UTC)
        payload = {
            "user_id": user_id,
            "token_type": "refresh",
            "exp": int(expires_at.timestamp()),
            "iat": int(now.timestamp()),
            "jti": session_id,
        }

        return jwt.encode(
            payload,
            self.settings.auth_jwt_secret,
            algorithm="HS256",
        )

    def _hash_token(self, token: str) -> str:
        """
        Hash token for secure storage.

        Args:
            token: JWT token to hash.

        Returns:
            SHA256 hash of token.
        """
        return hashlib.sha256(token.encode()).hexdigest()

    def _generate_uuid(self) -> str:
        """
        Generate UUID for session ID.

        Returns:
            UUID string.
        """
        import uuid

        return str(uuid.uuid4())
