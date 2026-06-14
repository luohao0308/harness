"""
Tests for validation service - Story 2.2: Configuration Validation

Tests cover:
1. JWT_SECRET validation
2. ENCRYPTION_KEY validation
3. Database connectivity check
4. API_BASE_URL accessibility check
5. CORS configuration validation
6. Model provider API keys validation
"""
from unittest.mock import MagicMock, patch

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.services.validation_service import ValidationService


class MockSettings:
    """Mock settings object for testing."""

    def __init__(self, **kwargs):
        self.app_env = kwargs.get("app_env", "development")
        self.api_base_url = kwargs.get("api_base_url", "http://localhost:8000")
        self.console_base_url = kwargs.get("console_base_url", "http://localhost:5173")
        self.app_base_url = kwargs.get("app_base_url", "http://localhost:3000")
        self.database_url = kwargs.get(
            "database_url", "postgresql+psycopg://agent:agent@localhost:5432/agent_harness"
        )
        self.auth_jwt_secret = kwargs.get("auth_jwt_secret", "test-secret-32chars")
        self.harness_secret_encryption_key = kwargs.get(
            "harness_secret_encryption_key", "test-encryption-32chars"
        )
        self.deepseek_api_key = kwargs.get("deepseek_api_key", "")
        self.model_gateway_api_key = kwargs.get("model_gateway_api_key", "")


@pytest.fixture
def mock_settings() -> MockSettings:
    """Create mock settings for testing."""
    return MockSettings(
        app_env="development",
        api_base_url="http://localhost:8000",
        console_base_url="http://localhost:5173",
        app_base_url="http://localhost:3000",
        database_url="postgresql+psycopg://agent:agent@localhost:5432/agent_harness",
        auth_jwt_secret="test-secret-key-with-sufficient-length-32chars",
        harness_secret_encryption_key="test-encryption-key-with-sufficient-length",
        deepseek_api_key="sk-test-deepseek-key-1234567890",
        model_gateway_api_key="gateway-key-123",
    )


@pytest.fixture
def validation_service(db_session: Session, mock_settings: MockSettings) -> ValidationService:
    """Create validation service instance."""
    return ValidationService(db_session, settings=mock_settings)


def test_check_required_secrets_all_valid(
    validation_service: ValidationService,
) -> None:
    """Test that valid secrets pass validation."""
    results = validation_service.check_required_secrets()

    # Should have 2 results: jwt_secret and encryption_key
    assert len(results) == 2

    # Find JWT secret result
    jwt_result = next(r for r in results if r["check"] == "jwt_secret")
    assert jwt_result["status"] == "pass"
    assert "properly configured" in jwt_result["message"]

    # Find encryption key result
    enc_result = next(r for r in results if r["check"] == "encryption_key")
    assert enc_result["status"] == "pass"
    assert "properly configured" in enc_result["message"]


def test_check_required_secrets_jwt_missing(
    db_session: Session,
) -> None:
    """Test JWT_SECRET validation fails when missing."""
    settings = MockSettings(
        auth_jwt_secret="",
        harness_secret_encryption_key="test-encryption-key-with-sufficient-length",
    )
    service = ValidationService(db_session, settings=settings)

    results = service.check_required_secrets()

    jwt_result = next(r for r in results if r["check"] == "jwt_secret")
    assert jwt_result["status"] == "fail"
    assert "not set" in jwt_result["message"]
    assert jwt_result["details"] is not None
    assert "hint" in jwt_result["details"]


def test_check_required_secrets_jwt_placeholder(
    db_session: Session,
) -> None:
    """Test JWT_SECRET validation fails when using placeholder."""
    settings = MockSettings(
        auth_jwt_secret="replace-with-openssl-rand-hex-32",
        harness_secret_encryption_key="test-encryption-key-with-sufficient-length",
    )
    service = ValidationService(db_session, settings=settings)

    results = service.check_required_secrets()

    jwt_result = next(r for r in results if r["check"] == "jwt_secret")
    assert jwt_result["status"] == "fail"
    assert "placeholder" in jwt_result["message"]


def test_check_required_secrets_jwt_too_short(
    db_session: Session,
) -> None:
    """Test JWT_SECRET validation fails when too short."""
    settings = MockSettings(
        auth_jwt_secret="short",
        harness_secret_encryption_key="test-encryption-key-with-sufficient-length",
    )
    service = ValidationService(db_session, settings=settings)

    results = service.check_required_secrets()

    jwt_result = next(r for r in results if r["check"] == "jwt_secret")
    assert jwt_result["status"] == "fail"
    assert "too short" in jwt_result["message"]
    assert jwt_result["details"] is not None
    assert jwt_result["details"]["current_length"] == 5
    assert jwt_result["details"]["minimum_length"] == 32


def test_check_required_secrets_encryption_key_missing_dev(
    db_session: Session,
) -> None:
    """Test ENCRYPTION_KEY validation warns in development when missing."""
    settings = MockSettings(
        app_env="development",
        auth_jwt_secret="test-secret-key-with-sufficient-length-32chars",
        harness_secret_encryption_key="",
    )
    service = ValidationService(db_session, settings=settings)

    results = service.check_required_secrets()

    enc_result = next(r for r in results if r["check"] == "encryption_key")
    assert enc_result["status"] == "warn"
    assert "not set" in enc_result["message"]
    assert "production" in enc_result["message"]


def test_check_required_secrets_encryption_key_missing_production(
    db_session: Session,
) -> None:
    """Test ENCRYPTION_KEY validation fails in production when missing."""
    settings = MockSettings(
        app_env="production",
        auth_jwt_secret="test-secret-key-with-sufficient-length-32chars",
        harness_secret_encryption_key="",
    )
    service = ValidationService(db_session, settings=settings)

    results = service.check_required_secrets()

    enc_result = next(r for r in results if r["check"] == "encryption_key")
    assert enc_result["status"] == "fail"
    assert "not set" in enc_result["message"]


def test_check_required_secrets_encryption_key_placeholder(
    db_session: Session,
) -> None:
    """Test ENCRYPTION_KEY validation fails when using placeholder."""
    settings = MockSettings(
        app_env="production",
        auth_jwt_secret="test-secret-key-with-sufficient-length-32chars",
        harness_secret_encryption_key="replace-with-generated-fernet-key",
    )
    service = ValidationService(db_session, settings=settings)

    results = service.check_required_secrets()

    enc_result = next(r for r in results if r["check"] == "encryption_key")
    assert enc_result["status"] == "fail"
    assert "placeholder" in enc_result["message"]


def test_validate_database_connectivity_success(
    validation_service: ValidationService,
) -> None:
    """Test database connectivity check passes when database is accessible."""
    result = validation_service.validate_database_connectivity()

    assert result["check"] == "database_connectivity"
    assert result["status"] == "pass"
    assert "healthy" in result["message"]
    assert result["details"] is not None
    assert "database_url" in result["details"]
    # Should mask credentials
    assert "***:***@" in result["details"]["database_url"]


def test_validate_database_connectivity_failure(
    db_session: Session,
    mock_settings: MockSettings,
) -> None:
    """Test database connectivity check fails when database is not accessible."""
    # Mock session to raise an exception
    db_session.execute = MagicMock(side_effect=OperationalError("Connection failed", None, None))

    service = ValidationService(db_session, settings=mock_settings)
    result = service.validate_database_connectivity()

    assert result["check"] == "database_connectivity"
    assert result["status"] == "fail"
    assert "failed" in result["message"]
    assert result["details"] is not None
    assert "error" in result["details"]


@patch("httpx.Client")
def test_check_api_base_url_accessibility_success(
    mock_client_class: MagicMock,
    validation_service: ValidationService,
) -> None:
    """Test API_BASE_URL check passes when API is accessible."""
    # Mock successful HTTP response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_client = MagicMock()
    mock_client.get.return_value = mock_response
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None
    mock_client_class.return_value = mock_client

    result = validation_service.check_api_base_url_accessibility()

    assert result["check"] == "api_base_url"
    assert result["status"] == "pass"
    assert "accessible" in result["message"]
    assert result["details"] is not None
    assert result["details"]["status_code"] == 200


@patch("httpx.Client")
def test_check_api_base_url_accessibility_non_200(
    mock_client_class: MagicMock,
    validation_service: ValidationService,
) -> None:
    """Test API_BASE_URL check warns when API returns non-200 status."""
    # Mock HTTP response with non-200 status
    mock_response = MagicMock()
    mock_response.status_code = 503
    mock_client = MagicMock()
    mock_client.get.return_value = mock_response
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None
    mock_client_class.return_value = mock_client

    result = validation_service.check_api_base_url_accessibility()

    assert result["check"] == "api_base_url"
    assert result["status"] == "warn"
    assert "non-200" in result["message"]
    assert result["details"] is not None
    assert result["details"]["status_code"] == 503


@patch("httpx.Client")
def test_check_api_base_url_accessibility_connection_error(
    mock_client_class: MagicMock,
    validation_service: ValidationService,
) -> None:
    """Test API_BASE_URL check warns when connection fails."""
    # Mock connection error
    mock_client = MagicMock()
    mock_client.get.side_effect = httpx.ConnectError("Connection refused")
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None
    mock_client_class.return_value = mock_client

    result = validation_service.check_api_base_url_accessibility()

    assert result["check"] == "api_base_url"
    assert result["status"] == "warn"
    assert "Cannot connect" in result["message"]
    assert result["details"] is not None
    assert "error" in result["details"]


def test_validate_cors_configuration_development(
    validation_service: ValidationService,
) -> None:
    """Test CORS validation passes in development environment."""
    result = validation_service.validate_cors_configuration()

    assert result["check"] == "cors_configuration"
    assert result["status"] == "pass"
    assert "development" in result["message"]
    assert result["details"] is not None
    assert result["details"]["environment"] == "development"
    assert result["details"]["mode"] == "permissive"


def test_validate_cors_configuration_production_valid(
    db_session: Session,
) -> None:
    """Test CORS validation passes in production with proper URLs."""
    settings = MockSettings(
        app_env="production",
        api_base_url="https://api.example.com",
        console_base_url="https://console.example.com",
        app_base_url="https://app.example.com",
        auth_jwt_secret="test-secret-key-with-sufficient-length-32chars",
    )
    service = ValidationService(db_session, settings=settings)

    result = service.validate_cors_configuration()

    assert result["check"] == "cors_configuration"
    assert result["status"] == "pass"
    assert "production" in result["message"]
    assert result["details"] is not None
    assert result["details"]["mode"] == "restrictive"


def test_validate_cors_configuration_production_localhost_console(
    db_session: Session,
) -> None:
    """Test CORS validation warns when console uses localhost in production."""
    settings = MockSettings(
        app_env="production",
        api_base_url="https://api.example.com",
        console_base_url="http://localhost:5173",
        app_base_url="https://app.example.com",
        auth_jwt_secret="test-secret-key-with-sufficient-length-32chars",
    )
    service = ValidationService(db_session, settings=settings)

    result = service.validate_cors_configuration()

    assert result["check"] == "cors_configuration"
    assert result["status"] == "warn"
    assert "CONSOLE_BASE_URL" in result["message"]
    assert "localhost" in result["message"]


def test_validate_cors_configuration_production_localhost_app(
    db_session: Session,
) -> None:
    """Test CORS validation warns when app uses localhost in production."""
    settings = MockSettings(
        app_env="production",
        api_base_url="https://api.example.com",
        console_base_url="https://console.example.com",
        app_base_url="http://localhost:3000",
        auth_jwt_secret="test-secret-key-with-sufficient-length-32chars",
    )
    service = ValidationService(db_session, settings=settings)

    result = service.validate_cors_configuration()

    assert result["check"] == "cors_configuration"
    assert result["status"] == "warn"
    assert "APP_BASE_URL" in result["message"]
    assert "localhost" in result["message"]


def test_test_model_provider_api_keys_all_configured(
    validation_service: ValidationService,
) -> None:
    """Test model provider API keys validation when all keys are configured."""
    results = validation_service.test_model_provider_api_keys()

    # Should have 2 results: deepseek and model_gateway
    assert len(results) == 2

    # Find DeepSeek result
    deepseek_result = next(r for r in results if r["check"] == "deepseek_api_key")
    assert deepseek_result["status"] == "pass"
    assert "configured" in deepseek_result["message"]

    # Find Model Gateway result
    gateway_result = next(r for r in results if r["check"] == "model_gateway_api_key")
    assert gateway_result["status"] == "pass"
    assert "configured" in gateway_result["message"]


def test_test_model_provider_api_keys_missing(
    db_session: Session,
) -> None:
    """Test model provider API keys validation when keys are missing."""
    settings = MockSettings(
        auth_jwt_secret="test-secret-key-with-sufficient-length-32chars",
        deepseek_api_key="",
        model_gateway_api_key="",
    )
    service = ValidationService(db_session, settings=settings)

    results = service.test_model_provider_api_keys()

    # Find DeepSeek result
    deepseek_result = next(r for r in results if r["check"] == "deepseek_api_key")
    assert deepseek_result["status"] == "warn"
    assert "not configured" in deepseek_result["message"]
    assert deepseek_result["details"] is not None
    assert deepseek_result["details"]["required"] is False

    # Find Model Gateway result
    gateway_result = next(r for r in results if r["check"] == "model_gateway_api_key")
    assert gateway_result["status"] == "warn"
    assert "not configured" in gateway_result["message"]


def test_test_model_provider_api_keys_deepseek_too_short(
    db_session: Session,
) -> None:
    """Test model provider API keys validation warns when DeepSeek key is too short."""
    settings = MockSettings(
        auth_jwt_secret="test-secret-key-with-sufficient-length-32chars",
        deepseek_api_key="short",
        model_gateway_api_key="gateway-key-123",
    )
    service = ValidationService(db_session, settings=settings)

    results = service.test_model_provider_api_keys()

    deepseek_result = next(r for r in results if r["check"] == "deepseek_api_key")
    assert deepseek_result["status"] == "warn"
    assert "too short" in deepseek_result["message"]


def test_test_model_provider_api_keys_gateway_placeholder(
    db_session: Session,
) -> None:
    """Test model provider API keys validation warns when gateway key uses placeholder."""
    settings = MockSettings(
        auth_jwt_secret="test-secret-key-with-sufficient-length-32chars",
        deepseek_api_key="sk-test-deepseek-key-1234567890",
        model_gateway_api_key="replace-me",
    )
    service = ValidationService(db_session, settings=settings)

    results = service.test_model_provider_api_keys()

    gateway_result = next(r for r in results if r["check"] == "model_gateway_api_key")
    assert gateway_result["status"] == "warn"
    assert "placeholder" in gateway_result["message"]


def test_validate_all_config(
    validation_service: ValidationService,
) -> None:
    """Test validate_all_config aggregates all configuration checks."""
    with patch.object(validation_service, "check_api_base_url_accessibility") as mock_api_check:
        mock_api_check.return_value = {
            "check": "api_base_url",
            "status": "pass",
            "message": "API accessible",
            "details": None,
        }

        results = validation_service.validate_all_config()

        # Should have results from:
        # - check_required_secrets (2: jwt_secret, encryption_key)
        # - validate_database_connectivity (1)
        # - check_api_base_url_accessibility (1)
        # - validate_cors_configuration (1)
        # - test_model_provider_api_keys (2: deepseek, model_gateway)
        assert len(results) >= 7

        # Verify all check types are present
        check_names = {r["check"] for r in results}
        assert "jwt_secret" in check_names
        assert "encryption_key" in check_names
        assert "database_connectivity" in check_names
        assert "api_base_url" in check_names
        assert "cors_configuration" in check_names
        assert "deepseek_api_key" in check_names
        assert "model_gateway_api_key" in check_names


def test_mask_db_credentials(
    validation_service: ValidationService,
) -> None:
    """Test database credential masking."""
    # Test with credentials
    masked = validation_service._mask_db_credentials(
        "postgresql+psycopg://user:password@localhost:5432/db"
    )
    assert "***:***@" in masked
    assert "user" not in masked
    assert "password" not in masked
    assert "localhost:5432/db" in masked

    # Test without credentials
    masked_no_creds = validation_service._mask_db_credentials("sqlite:///data.db")
    assert masked_no_creds == "sqlite:///data.db"
