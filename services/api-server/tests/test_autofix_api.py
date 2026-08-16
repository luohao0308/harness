"""
Integration tests for autofix API endpoint - Story 3.1
"""
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_autofix_secrets_endpoint_success():
    """
    Test successful autofix operation via API endpoint.
    """
    # Create a temporary .env file
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".env") as f:
        f.write("APP_ENV=development\n")
        f.write("DATABASE_URL=postgresql://localhost/test\n")
        temp_path = f.name

    try:
        # Mock the env path resolution
        with patch("app.api.autofix.Path") as mock_path:
            mock_path_instance = mock_path.return_value
            mock_path_instance.parent.parent.parent.__truediv__.return_value = Path(temp_path)
            mock_path_instance.exists.return_value = True

            # Patch the actual Path used in autofix
            with patch("app.services.autofix_service.Path", return_value=Path(temp_path)):
                response = client.post("/api/onboarding/autofix/secrets")

        # Verify response
        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["jwt_secret_added"] is True
        assert data["encryption_key_added"] is True
        assert len(data["added_secrets"]) == 2
        assert "AUTH_JWT_SECRET" in data["added_secrets"]
        assert "HARNESS_SECRET_ENCRYPTION_KEY" in data["added_secrets"]
        assert "timestamp" in data

    finally:
        import os
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def test_autofix_secrets_endpoint_no_env_file():
    """
    Test error when .env file doesn't exist.
    """
    # Create a path that doesn't exist
    non_existent_path = Path("/tmp/nonexistent_test_file_12345.env")

    with patch("app.api.autofix.Path") as mock_path_class:
        # Mock the Path constructor call in the endpoint
        mock_env_path = mock_path_class.return_value.parent.parent.parent.__truediv__.return_value
        mock_env_path.exists.return_value = False
        mock_env_path.__str__.return_value = str(non_existent_path)

        response = client.post("/api/onboarding/autofix/secrets")

        assert response.status_code == 404
        assert ".env file not found" in response.json()["detail"]
