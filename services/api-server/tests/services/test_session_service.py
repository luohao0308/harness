"""
Tests for SessionService (Story 4.1 - SSO Session Lifecycle Management)

Tests JWT token generation, session CRUD, token validation, refresh, and expiration.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import jwt
import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.session_service import SessionService


@pytest.fixture
def db_session() -> MagicMock:
    """Mock database session."""
    return MagicMock(spec=Session)


@pytest.fixture
def session_service(db_session: MagicMock) -> SessionService:
    """Create SessionService instance with mocked DB."""
    return SessionService(db_session)


class TestCreateSession:
    """Test session creation with JWT token generation."""

    def test_create_session_generates_jwt_token(
        self,
        session_service: SessionService,
        db_session: MagicMock,
    ) -> None:
        """Should create session with valid JWT token."""
        user_id = "user-123"
        email = "test@example.com"
        roles = ["user", "admin"]

        result = session_service.create_session(
            user_id=user_id,
            email=email,
            roles=roles,
        )

        # Verify session was added to database
        assert db_session.add.called
        assert db_session.commit.called

        # Verify JWT token structure
        assert "access_token" in result
        assert "refresh_token" in result
        assert "expires_at" in result
        assert "token_type" in result
        assert result["token_type"] == "Bearer"

        # Decode and verify JWT claims
        settings = get_settings()
        decoded = jwt.decode(
            result["access_token"],
            settings.auth_jwt_secret,
            algorithms=["HS256"],
        )
        assert decoded["user_id"] == user_id
        assert decoded["email"] == email
        assert decoded["roles"] == roles
        assert "exp" in decoded
        assert "iat" in decoded
        assert "jti" in decoded

    def test_create_session_with_custom_ttl(
        self,
        session_service: SessionService,
        db_session: MagicMock,
    ) -> None:
        """Should create session with custom TTL."""
        user_id = "user-123"
        email = "test@example.com"
        ttl_hours = 2

        result = session_service.create_session(
            user_id=user_id,
            email=email,
            ttl_hours=ttl_hours,
        )

        # Verify expiration time
        settings = get_settings()
        decoded = jwt.decode(
            result["access_token"],
            settings.auth_jwt_secret,
            algorithms=["HS256"],
        )
        exp_time = datetime.fromtimestamp(decoded["exp"], tz=UTC)
        iat_time = datetime.fromtimestamp(decoded["iat"], tz=UTC)
        actual_ttl = exp_time - iat_time

        # Allow 1 second tolerance for test execution time
        assert abs(actual_ttl.total_seconds() - (ttl_hours * 3600)) < 1

    def test_create_session_stores_metadata(
        self,
        session_service: SessionService,
        db_session: MagicMock,
    ) -> None:
        """Should store session metadata in database."""
        user_id = "user-123"
        email = "test@example.com"
        metadata = {"ip_address": "192.168.1.1", "user_agent": "Mozilla/5.0"}

        session_service.create_session(
            user_id=user_id,
            email=email,
            metadata=metadata,
        )

        # Verify session model was created with metadata
        call_args = db_session.add.call_args
        session_model = call_args[0][0]
        assert session_model.user_id == user_id
        assert session_model.metadata_json == metadata


class TestValidateToken:
    """Test JWT token validation."""

    def test_validate_token_success(
        self,
        session_service: SessionService,
        db_session: MagicMock,
    ) -> None:
        """Should validate valid JWT token."""
        # Create a session first
        user_id = "user-123"
        email = "test@example.com"
        result = session_service.create_session(user_id=user_id, email=email)
        token = result["access_token"]

        # Mock session lookup
        mock_session = MagicMock()
        mock_session.user_id = user_id
        mock_session.revoked_at = None
        mock_session.expires_at = datetime.now(UTC) + timedelta(hours=1)
        db_session.query.return_value.filter.return_value.first.return_value = mock_session

        # Validate token
        claims = session_service.validate_token(token)

        assert claims["user_id"] == user_id
        assert claims["email"] == email

    def test_validate_token_expired(
        self,
        session_service: SessionService,
        db_session: MagicMock,
    ) -> None:
        """Should reject expired JWT token."""
        # Create an expired token
        settings = get_settings()
        expired_time = datetime.now(UTC) - timedelta(hours=1)
        token_data = {
            "user_id": "user-123",
            "email": "test@example.com",
            "exp": expired_time.timestamp(),
            "iat": (expired_time - timedelta(hours=24)).timestamp(),
            "jti": "token-id",
        }
        expired_token = jwt.encode(
            token_data,
            settings.auth_jwt_secret,
            algorithm="HS256",
        )

        with pytest.raises(ValueError, match="Token has expired"):
            session_service.validate_token(expired_token)

    def test_validate_token_revoked(
        self,
        session_service: SessionService,
        db_session: MagicMock,
    ) -> None:
        """Should reject revoked session token."""
        # Create a valid token
        result = session_service.create_session(
            user_id="user-123",
            email="test@example.com",
        )
        token = result["access_token"]

        # Mock revoked session
        mock_session = MagicMock()
        mock_session.revoked_at = datetime.now(UTC)
        db_session.query.return_value.filter.return_value.first.return_value = mock_session

        with pytest.raises(ValueError, match="Session has been revoked"):
            session_service.validate_token(token)

    def test_validate_token_invalid_signature(
        self,
        session_service: SessionService,
    ) -> None:
        """Should reject token with invalid signature."""
        # Create token with wrong secret
        token_data = {
            "user_id": "user-123",
            "email": "test@example.com",
            "exp": (datetime.now(UTC) + timedelta(hours=1)).timestamp(),
            "iat": datetime.now(UTC).timestamp(),
            "jti": "token-id",
        }
        invalid_token = jwt.encode(
            token_data,
            "wrong-secret",
            algorithm="HS256",
        )

        with pytest.raises(ValueError, match="Invalid token"):
            session_service.validate_token(invalid_token)


class TestRefreshSession:
    """Test session refresh functionality."""

    def test_refresh_session_extends_expiration(
        self,
        session_service: SessionService,
        db_session: MagicMock,
    ) -> None:
        """Should extend session expiration on refresh."""
        # Create initial session
        initial_result = session_service.create_session(
            user_id="user-123",
            email="test@example.com",
        )
        refresh_token = initial_result["refresh_token"]

        # Mock session lookup
        mock_session = MagicMock()
        mock_session.id = "session-123"
        mock_session.user_id = "user-123"
        mock_session.email = "test@example.com"
        mock_session.roles_json = ["user"]
        mock_session.revoked_at = None
        mock_session.expires_at = datetime.now(UTC) + timedelta(hours=1)
        db_session.query.return_value.filter.return_value.first.return_value = mock_session

        # Refresh session
        result = session_service.refresh_session(refresh_token)

        # Verify new tokens were issued
        assert "access_token" in result
        assert "refresh_token" in result
        assert result["access_token"] != initial_result["access_token"]

        # Verify expiration was updated
        assert db_session.commit.called

    def test_refresh_session_with_revoked_token(
        self,
        session_service: SessionService,
        db_session: MagicMock,
    ) -> None:
        """Should reject refresh of revoked session."""
        settings = get_settings()
        refresh_token = jwt.encode(
            {
                "user_id": "user-123",
                "token_type": "refresh",
                "exp": (datetime.now(UTC) + timedelta(days=30)).timestamp(),
                "iat": datetime.now(UTC).timestamp(),
                "jti": "session-123",
            },
            settings.auth_jwt_secret,
            algorithm="HS256",
        )

        # Mock revoked session
        mock_session = MagicMock()
        mock_session.revoked_at = datetime.now(UTC)
        db_session.query.return_value.filter.return_value.first.return_value = mock_session

        with pytest.raises(ValueError, match="Session has been revoked"):
            session_service.refresh_session(refresh_token)


class TestRevokeSession:
    """Test session revocation (logout)."""

    def test_revoke_session_marks_as_revoked(
        self,
        session_service: SessionService,
        db_session: MagicMock,
    ) -> None:
        """Should mark session as revoked."""
        session_id = "session-123"

        # Mock session lookup
        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.revoked_at = None
        db_session.query.return_value.filter.return_value.first.return_value = mock_session

        result = session_service.revoke_session(session_id)

        assert result is True
        assert mock_session.revoked_at is not None
        assert db_session.commit.called

    def test_revoke_nonexistent_session(
        self,
        session_service: SessionService,
        db_session: MagicMock,
    ) -> None:
        """Should return False for nonexistent session."""
        db_session.query.return_value.filter.return_value.first.return_value = None

        result = session_service.revoke_session("nonexistent-session")

        assert result is False


class TestGetSession:
    """Test session retrieval."""

    def test_get_session_by_id(
        self,
        session_service: SessionService,
        db_session: MagicMock,
    ) -> None:
        """Should retrieve session by ID."""
        session_id = "session-123"

        # Mock session
        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = "user-123"
        mock_session.email = "test@example.com"
        mock_session.revoked_at = None
        db_session.query.return_value.filter.return_value.first.return_value = mock_session

        session = session_service.get_session(session_id)

        assert session is not None
        assert session.id == session_id

    def test_get_nonexistent_session(
        self,
        session_service: SessionService,
        db_session: MagicMock,
    ) -> None:
        """Should return None for nonexistent session."""
        db_session.query.return_value.filter.return_value.first.return_value = None

        session = session_service.get_session("nonexistent-session")

        assert session is None


class TestSessionExpiration:
    """Test session expiration handling."""

    def test_expired_session_validation_fails(
        self,
        session_service: SessionService,
        db_session: MagicMock,
    ) -> None:
        """Should reject validation of expired session."""
        # Create session
        result = session_service.create_session(
            user_id="user-123",
            email="test@example.com",
        )
        token = result["access_token"]

        # Mock expired session in DB
        mock_session = MagicMock()
        mock_session.expires_at = datetime.now(UTC) - timedelta(hours=1)
        mock_session.revoked_at = None
        db_session.query.return_value.filter.return_value.first.return_value = mock_session

        with pytest.raises(ValueError, match="Session has expired"):
            session_service.validate_token(token)
