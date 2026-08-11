"""
Tests for validation service - Story 2.1: System Requirements Checks

Tests cover:
1. Python version check (≥ 3.11)
2. Node.js version check (≥ 20)
3. Disk space check (≥ 10 GB free)
4. Memory check (≥ 4 GB available)
"""

from unittest.mock import MagicMock, patch

import pytest
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


# Test 1: Python version check - pass
@patch("subprocess.run")
def test_check_python_version_pass(
    mock_run: MagicMock,
    validation_service: ValidationService,
) -> None:
    """Test Python version check passes when version >= 3.11."""
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="Python 3.11.5",
        stderr="",
    )

    result = validation_service.check_python_version()

    assert result["check"] == "python_version"
    assert result["status"] == "pass"
    assert "3.11" in result["message"]
    assert result["details"] is not None
    assert result["details"]["version"] == "3.11.5"
    assert result["details"]["required"] == "3.11"


# Test 2: Python version check - fail (too old)
@patch("subprocess.run")
def test_check_python_version_fail_old(
    mock_run: MagicMock,
    validation_service: ValidationService,
) -> None:
    """Test Python version check fails when version < 3.11."""
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="Python 3.10.8",
        stderr="",
    )

    result = validation_service.check_python_version()

    assert result["check"] == "python_version"
    assert result["status"] == "fail"
    assert "3.10.8" in result["message"]
    assert "3.11" in result["message"]
    assert result["details"] is not None
    assert result["details"]["version"] == "3.10.8"
    assert result["details"]["required"] == "3.11"


# Test 3: Python version check - error (command failed)
@patch("subprocess.run")
def test_check_python_version_error(
    mock_run: MagicMock,
    validation_service: ValidationService,
) -> None:
    """Test Python version check fails when command errors."""
    mock_run.side_effect = FileNotFoundError("python not found")

    result = validation_service.check_python_version()

    assert result["check"] == "python_version"
    assert result["status"] == "fail"
    assert "not found" in result["message"].lower() or "error" in result["message"].lower()


# Test 4: Node.js version check - pass
@patch("subprocess.run")
def test_check_nodejs_version_pass(
    mock_run: MagicMock,
    validation_service: ValidationService,
) -> None:
    """Test Node.js version check passes when version >= 20."""
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="v20.10.0",
        stderr="",
    )

    result = validation_service.check_nodejs_version()

    assert result["check"] == "nodejs_version"
    assert result["status"] == "pass"
    assert "20" in result["message"]
    assert result["details"] is not None
    assert result["details"]["version"] == "20.10.0"
    assert result["details"]["required"] == "20"


# Test 5: Node.js version check - fail (too old)
@patch("subprocess.run")
def test_check_nodejs_version_fail_old(
    mock_run: MagicMock,
    validation_service: ValidationService,
) -> None:
    """Test Node.js version check fails when version < 20."""
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="v18.16.0",
        stderr="",
    )

    result = validation_service.check_nodejs_version()

    assert result["check"] == "nodejs_version"
    assert result["status"] == "fail"
    assert "18.16.0" in result["message"]
    assert "20" in result["message"]


# Test 6: Disk space check - pass
@patch("psutil.disk_usage")
def test_check_disk_space_pass(
    mock_disk_usage: MagicMock,
    validation_service: ValidationService,
) -> None:
    """Test disk space check passes when free space >= 10 GB."""
    # Mock 50 GB free
    mock_disk_usage.return_value = MagicMock(
        total=100 * 1024**3,
        used=50 * 1024**3,
        free=50 * 1024**3,
    )

    result = validation_service.check_disk_space()

    assert result["check"] == "disk_space"
    assert result["status"] == "pass"
    assert result["details"] is not None
    assert result["details"]["free_gb"] == 50
    assert result["details"]["required_gb"] == 10


# Test 7: Disk space check - warn (low space)
@patch("psutil.disk_usage")
def test_check_disk_space_warn(
    mock_disk_usage: MagicMock,
    validation_service: ValidationService,
) -> None:
    """Test disk space check warns when free space is between 5-10 GB."""
    # Mock 7 GB free
    mock_disk_usage.return_value = MagicMock(
        total=100 * 1024**3,
        used=93 * 1024**3,
        free=7 * 1024**3,
    )

    result = validation_service.check_disk_space()

    assert result["check"] == "disk_space"
    assert result["status"] == "warn"
    assert result["details"] is not None
    assert result["details"]["free_gb"] == 7
    assert result["details"]["required_gb"] == 10


# Test 8: Disk space check - fail (insufficient space)
@patch("psutil.disk_usage")
def test_check_disk_space_fail(
    mock_disk_usage: MagicMock,
    validation_service: ValidationService,
) -> None:
    """Test disk space check fails when free space < 5 GB."""
    # Mock 3 GB free
    mock_disk_usage.return_value = MagicMock(
        total=100 * 1024**3,
        used=97 * 1024**3,
        free=3 * 1024**3,
    )

    result = validation_service.check_disk_space()

    assert result["check"] == "disk_space"
    assert result["status"] == "fail"
    assert result["details"] is not None
    assert result["details"]["free_gb"] == 3


# Test 9: Memory check - pass
@patch("psutil.virtual_memory")
def test_check_memory_pass(
    mock_memory: MagicMock,
    validation_service: ValidationService,
) -> None:
    """Test memory check passes when available memory >= 4 GB."""
    # Mock 8 GB available
    mock_memory.return_value = MagicMock(
        total=16 * 1024**3,
        available=8 * 1024**3,
    )

    result = validation_service.check_memory()

    assert result["check"] == "memory"
    assert result["status"] == "pass"
    assert result["details"] is not None
    assert result["details"]["available_gb"] == 8
    assert result["details"]["required_gb"] == 4


# Test 10: Memory check - warn (low memory)
@patch("psutil.virtual_memory")
def test_check_memory_warn(
    mock_memory: MagicMock,
    validation_service: ValidationService,
) -> None:
    """Test memory check warns when available memory is between 2-4 GB."""
    # Mock 3 GB available
    mock_memory.return_value = MagicMock(
        total=8 * 1024**3,
        available=3 * 1024**3,
    )

    result = validation_service.check_memory()

    assert result["check"] == "memory"
    assert result["status"] == "warn"
    assert result["details"] is not None
    assert result["details"]["available_gb"] == 3
    assert result["details"]["required_gb"] == 4


# Test 11: Memory check - fail (insufficient memory)
@patch("psutil.virtual_memory")
def test_check_memory_fail(
    mock_memory: MagicMock,
    validation_service: ValidationService,
) -> None:
    """Test memory check fails when available memory < 2 GB."""
    # Mock 1 GB available
    mock_memory.return_value = MagicMock(
        total=4 * 1024**3,
        available=1 * 1024**3,
    )

    result = validation_service.check_memory()

    assert result["check"] == "memory"
    assert result["status"] == "fail"
    assert result["details"] is not None
    assert result["details"]["available_gb"] == 1


# =======================
# Story 2.3: Database Migration Check Tests
# =======================


# Test 1: Migration check - all migrations applied (pass)
def test_check_migrations_status_pass(
    validation_service: ValidationService,
) -> None:
    """Test migration check passes when all migrations are applied."""
    with (
        patch("app.services.validation_service.Config") as mock_config_cls,
        patch("app.services.validation_service.ScriptDirectory") as mock_script_cls,
        patch("app.services.validation_service.MigrationContext") as mock_migration_ctx_cls,
    ):
        # Mock Alembic configuration
        mock_config = MagicMock()
        mock_config_cls.return_value = mock_config

        # Mock ScriptDirectory to return latest revision
        mock_script = MagicMock()
        mock_script.get_current_head.return_value = "20260610_0037"
        mock_script_cls.from_config.return_value = mock_script

        # Mock MigrationContext to return current database revision
        mock_migration_ctx = MagicMock()
        mock_migration_ctx.get_current_revision.return_value = "20260610_0037"
        mock_migration_ctx_cls.configure.return_value = mock_migration_ctx

        result = validation_service.check_migrations_status()

        assert result["check"] == "database_migrations"
        assert result["status"] == "pass"
        assert "up to date" in result["message"].lower()
        assert result["details"] is not None
        assert result["details"]["current_revision"] == "20260610_0037"
        assert result["details"]["latest_revision"] == "20260610_0037"
        assert result["details"]["pending_count"] == 0


# Test 2: Migration check - pending migrations (warn)
def test_check_migrations_status_pending(
    validation_service: ValidationService,
) -> None:
    """Test migration check warns when there are pending migrations."""
    with (
        patch("app.services.validation_service.Config") as mock_config_cls,
        patch("app.services.validation_service.ScriptDirectory") as mock_script_cls,
        patch("app.services.validation_service.MigrationContext") as mock_migration_ctx_cls,
    ):
        # Mock Alembic configuration
        mock_config = MagicMock()
        mock_config_cls.return_value = mock_config

        # Mock ScriptDirectory
        mock_script = MagicMock()
        mock_script.get_current_head.return_value = "20260610_0037"

        # Mock pending migrations (2 pending)
        mock_rev1 = MagicMock()
        mock_rev1.revision = "20260609_0036"
        mock_rev1.doc = "add user avatar"
        mock_rev2 = MagicMock()
        mock_rev2.revision = "20260610_0037"
        mock_rev2.doc = "remove deprecated model pricing sources"

        mock_script.iterate_revisions.return_value = [mock_rev2, mock_rev1]
        mock_script_cls.from_config.return_value = mock_script

        # Mock MigrationContext - database is at older revision
        mock_migration_ctx = MagicMock()
        mock_migration_ctx.get_current_revision.return_value = "20260608_0035"
        mock_migration_ctx_cls.configure.return_value = mock_migration_ctx

        result = validation_service.check_migrations_status()

        assert result["check"] == "database_migrations"
        assert result["status"] == "warn"
        assert "pending" in result["message"].lower()
        assert result["details"] is not None
        assert result["details"]["current_revision"] == "20260608_0035"
        assert result["details"]["latest_revision"] == "20260610_0037"
        assert result["details"]["pending_count"] == 2


# Test 3: Migration check - no database revision (fail)
def test_check_migrations_status_no_revision(
    validation_service: ValidationService,
) -> None:
    """Test migration check fails when database has no migration applied."""
    with (
        patch("app.services.validation_service.Config") as mock_config_cls,
        patch("app.services.validation_service.ScriptDirectory") as mock_script_cls,
        patch("app.services.validation_service.MigrationContext") as mock_migration_ctx_cls,
    ):
        # Mock Alembic configuration
        mock_config = MagicMock()
        mock_config_cls.return_value = mock_config

        # Mock ScriptDirectory
        mock_script = MagicMock()
        mock_script.get_current_head.return_value = "20260610_0037"
        mock_script_cls.from_config.return_value = mock_script

        # Mock MigrationContext - no revision in database
        mock_migration_ctx = MagicMock()
        mock_migration_ctx.get_current_revision.return_value = None
        mock_migration_ctx_cls.configure.return_value = mock_migration_ctx

        result = validation_service.check_migrations_status()

        assert result["check"] == "database_migrations"
        assert result["status"] == "fail"
        assert (
            "not initialized" in result["message"].lower()
            or "no migration" in result["message"].lower()
        )
        assert result["details"] is not None
        assert result["details"]["current_revision"] is None


# Test 4: Migration check - error handling
def test_check_migrations_status_error(
    validation_service: ValidationService,
) -> None:
    """Test migration check handles errors gracefully."""
    with patch("app.services.validation_service.Config") as mock_config_cls:
        # Mock Config to raise an exception
        mock_config_cls.side_effect = Exception("Cannot read alembic.ini")

        result = validation_service.check_migrations_status()

        assert result["check"] == "database_migrations"
        assert result["status"] == "fail"
        assert "error" in result["message"].lower()
        assert result["details"] is not None
        assert "error" in result["details"]
