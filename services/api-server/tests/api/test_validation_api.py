"""
Tests for validation API endpoints - Story 2.1

Tests the POST /api/onboarding/validate/system endpoint.
"""
from unittest.mock import patch

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
