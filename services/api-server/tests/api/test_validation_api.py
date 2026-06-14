"""
Tests for validation API endpoints - Story 2.1, 2.2 & 2.3

Tests the validation endpoints:
- POST /api/onboarding/validate/system
- POST /api/onboarding/validate/config
- POST /api/onboarding/validate/deployment
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@patch("app.services.validation_service.subprocess.run")
@patch("app.services.validation_service.psutil.disk_usage")
@patch("app.services.validation_service.psutil.virtual_memory")
def test_validate_system_all_pass(
    mock_memory,
    mock_disk,
    mock_subprocess,
) -> None:
    """Test system validation endpoint returns all passing checks."""
    # Mock all checks to pass
    mock_subprocess.side_effect = [
        # Python check
        type("obj", (), {"returncode": 0, "stdout": "Python 3.11.5", "stderr": ""})(),
        # Node check
        type("obj", (), {"returncode": 0, "stdout": "v20.10.0", "stderr": ""})(),
    ]
    mock_disk.return_value = type("obj", (), {"free": 50 * 1024**3})()
    mock_memory.return_value = type("obj", (), {"available": 8 * 1024**3})()

    response = client.post("/api/onboarding/validate/system")

    assert response.status_code == 200
    data = response.json()

    assert "checks" in data
    assert "summary" in data

    # Should have 4 checks: python, nodejs, disk, memory
    assert len(data["checks"]) == 4

    # All checks should pass
    assert data["summary"]["pass"] == 4
    assert data["summary"]["warn"] == 0
    assert data["summary"]["fail"] == 0
    assert data["summary"]["status"] == "pass"


@patch("app.services.validation_service.subprocess.run")
@patch("app.services.validation_service.psutil.disk_usage")
@patch("app.services.validation_service.psutil.virtual_memory")
def test_validate_system_with_warnings(
    mock_memory,
    mock_disk,
    mock_subprocess,
) -> None:
    """Test system validation endpoint returns warnings for low resources."""
    # Mock checks with warnings
    mock_subprocess.side_effect = [
        # Python check - pass
        type("obj", (), {"returncode": 0, "stdout": "Python 3.11.5", "stderr": ""})(),
        # Node check - pass
        type("obj", (), {"returncode": 0, "stdout": "v20.10.0", "stderr": ""})(),
    ]
    # Disk space low (7 GB)
    mock_disk.return_value = type("obj", (), {"free": 7 * 1024**3})()
    # Memory low (3 GB)
    mock_memory.return_value = type("obj", (), {"available": 3 * 1024**3})()

    response = client.post("/api/onboarding/validate/system")

    assert response.status_code == 200
    data = response.json()

    # Should have 2 pass, 2 warn
    assert data["summary"]["pass"] == 2
    assert data["summary"]["warn"] == 2
    assert data["summary"]["fail"] == 0
    assert data["summary"]["status"] == "warn"


@patch("app.services.validation_service.subprocess.run")
@patch("app.services.validation_service.psutil.disk_usage")
@patch("app.services.validation_service.psutil.virtual_memory")
def test_validate_system_with_failures(
    mock_memory,
    mock_disk,
    mock_subprocess,
) -> None:
    """Test system validation endpoint returns failures for insufficient resources."""
    # Mock checks with failures
    mock_subprocess.side_effect = [
        # Python check - fail (old version)
        type("obj", (), {"returncode": 0, "stdout": "Python 3.10.0", "stderr": ""})(),
        # Node check - fail (old version)
        type("obj", (), {"returncode": 0, "stdout": "v18.0.0", "stderr": ""})(),
    ]
    # Disk space critical (3 GB)
    mock_disk.return_value = type("obj", (), {"free": 3 * 1024**3})()
    # Memory critical (1 GB)
    mock_memory.return_value = type("obj", (), {"available": 1 * 1024**3})()

    response = client.post("/api/onboarding/validate/system")

    assert response.status_code == 200
    data = response.json()

    # All checks should fail
    assert data["summary"]["pass"] == 0
    assert data["summary"]["warn"] == 0
    assert data["summary"]["fail"] == 4
    assert data["summary"]["status"] == "fail"

    # Check that all checks have proper structure
    for check in data["checks"]:
        assert "check" in check
        assert "status" in check
        assert "message" in check
        assert check["status"] == "fail"


def test_validate_system_response_structure() -> None:
    """Test that the validation response has correct structure."""
    response = client.post("/api/onboarding/validate/system")

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "checks" in data
    assert "summary" in data
    assert isinstance(data["checks"], list)
    assert isinstance(data["summary"], dict)

    # Verify summary structure
    summary = data["summary"]
    assert "total" in summary
    assert "pass" in summary
    assert "warn" in summary
    assert "fail" in summary
    assert "status" in summary

    # Verify each check has required fields
    for check in data["checks"]:
        assert "check" in check
        assert "status" in check
        assert "message" in check
        assert check["status"] in ["pass", "warn", "fail"]


# =======================
# Story 2.3: Deployment Validation API Tests
# =======================


@patch("app.services.validation_service.Config")
@patch("app.services.validation_service.ScriptDirectory")
@patch("app.services.validation_service.MigrationContext")
def test_validate_deployment_all_pass(
    mock_migration_ctx_cls,
    mock_script_cls,
    mock_config_cls,
) -> None:
    """Test deployment validation endpoint returns passing checks."""
    # Mock Alembic configuration
    mock_config = MagicMock()
    mock_config_cls.return_value = mock_config

    # Mock ScriptDirectory - migrations up to date
    mock_script = MagicMock()
    mock_script.get_current_head.return_value = "20260610_0037"
    mock_script.get_heads.return_value = ["20260610_0037"]
    mock_script.versions = "/fake/path/versions"
    mock_script_cls.from_config.return_value = mock_script

    # Mock MigrationContext - database at latest revision
    mock_migration_ctx = MagicMock()
    mock_migration_ctx.get_current_revision.return_value = "20260610_0037"
    mock_migration_ctx_cls.configure.return_value = mock_migration_ctx

    with patch("os.path.exists", return_value=True), \
         patch("os.listdir", return_value=["20260610_0037_test.py"]):

        response = client.post("/api/onboarding/validate/deployment")

        assert response.status_code == 200
        data = response.json()

        assert "checks" in data
        assert "summary" in data

        # Should have 2 checks: migration status, migration integrity
        assert len(data["checks"]) == 2

        # All checks should pass
        assert data["summary"]["pass"] == 2
        assert data["summary"]["warn"] == 0
        assert data["summary"]["fail"] == 0
        assert data["summary"]["status"] == "pass"


@patch("app.services.validation_service.Config")
@patch("app.services.validation_service.ScriptDirectory")
@patch("app.services.validation_service.MigrationContext")
def test_validate_deployment_with_pending_migrations(
    mock_migration_ctx_cls,
    mock_script_cls,
    mock_config_cls,
) -> None:
    """Test deployment validation endpoint warns about pending migrations."""
    # Mock Alembic configuration
    mock_config = MagicMock()
    mock_config_cls.return_value = mock_config

    # Mock ScriptDirectory - has newer migrations
    mock_script = MagicMock()
    mock_script.get_current_head.return_value = "20260610_0037"
    mock_script.get_heads.return_value = ["20260610_0037"]
    mock_script.versions = "/fake/path/versions"

    # Mock pending migrations
    mock_rev1 = MagicMock()
    mock_rev1.revision = "20260609_0036"
    mock_rev1.doc = "add user avatar"
    mock_rev2 = MagicMock()
    mock_rev2.revision = "20260610_0037"
    mock_rev2.doc = "remove deprecated model pricing sources"

    mock_script.iterate_revisions.return_value = [mock_rev2, mock_rev1]
    mock_script_cls.from_config.return_value = mock_script

    # Mock MigrationContext - database at older revision
    mock_migration_ctx = MagicMock()
    mock_migration_ctx.get_current_revision.return_value = "20260608_0035"
    mock_migration_ctx_cls.configure.return_value = mock_migration_ctx

    with patch("os.path.exists", return_value=True), \
         patch("os.listdir", return_value=["20260610_0037_test.py"]):

        response = client.post("/api/onboarding/validate/deployment")

        assert response.status_code == 200
        data = response.json()

        # Should have 1 pass (integrity), 1 warn (pending migrations)
        assert data["summary"]["pass"] == 1
        assert data["summary"]["warn"] == 1
        assert data["summary"]["fail"] == 0
        assert data["summary"]["status"] == "warn"

        # Check migration status has pending migrations
        migration_check = next(c for c in data["checks"] if c["check"] == "database_migrations")
        assert migration_check["status"] == "warn"
        assert migration_check["details"]["pending_count"] == 2


@patch("app.services.validation_service.Config")
@patch("app.services.validation_service.ScriptDirectory")
@patch("app.services.validation_service.MigrationContext")
def test_validate_deployment_database_not_initialized(
    mock_migration_ctx_cls,
    mock_script_cls,
    mock_config_cls,
) -> None:
    """Test deployment validation endpoint fails when database not initialized."""
    # Mock Alembic configuration
    mock_config = MagicMock()
    mock_config_cls.return_value = mock_config

    # Mock ScriptDirectory
    mock_script = MagicMock()
    mock_script.get_current_head.return_value = "20260610_0037"
    mock_script.get_heads.return_value = ["20260610_0037"]
    mock_script.versions = "/fake/path/versions"
    mock_script_cls.from_config.return_value = mock_script

    # Mock MigrationContext - no revision in database
    mock_migration_ctx = MagicMock()
    mock_migration_ctx.get_current_revision.return_value = None
    mock_migration_ctx_cls.configure.return_value = mock_migration_ctx

    with patch("os.path.exists", return_value=True), \
         patch("os.listdir", return_value=["20260610_0037_test.py"]):

        response = client.post("/api/onboarding/validate/deployment")

        assert response.status_code == 200
        data = response.json()

        # Should have 1 fail (migration status), 1 pass (integrity)
        assert data["summary"]["pass"] == 1
        assert data["summary"]["warn"] == 0
        assert data["summary"]["fail"] == 1
        assert data["summary"]["status"] == "fail"

        # Check migration status fails
        migration_check = next(c for c in data["checks"] if c["check"] == "database_migrations")
        assert migration_check["status"] == "fail"
        assert "not initialized" in migration_check["message"].lower()


def test_validate_deployment_response_structure() -> None:
    """Test that the deployment validation response has correct structure."""
    response = client.post("/api/onboarding/validate/deployment")

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "checks" in data
    assert "summary" in data
    assert isinstance(data["checks"], list)
    assert isinstance(data["summary"], dict)

    # Verify summary structure
    summary = data["summary"]
    assert "total" in summary
    assert "pass" in summary
    assert "warn" in summary
    assert "fail" in summary
    assert "status" in summary

    # Verify each check has required fields
    for check in data["checks"]:
        assert "check" in check
        assert "status" in check
        assert "message" in check
        assert check["status"] in ["pass", "warn", "fail"]
