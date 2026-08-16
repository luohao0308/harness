"""
Tests for SAML Provider API endpoints.

Following TDD: These tests are written first, then API implementation follows.
Story 1.2 - IdP Configuration Management
Tests CRUD endpoints for SAML Identity Provider configuration.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture
def sample_provider_data() -> dict:
    """Sample SAML provider data for API requests."""
    return {
        "organization_id": "org-123",
        "name": "Okta SSO",
        "entity_id": "http://www.okta.com/exk123",
        "sso_url": "https://example.okta.com/app/example_saml/exk123/sso/saml",
        "slo_url": "https://example.okta.com/app/example_saml/exk123/slo/saml",
        "x509_cert": """-----BEGIN CERTIFICATE-----
MIIDXTCCAkWgAwIBAgIJAKL0UG+mRKSzMA0GCSqGSIb3DQEBCwUAMEUxCzAJBgNV
BAYTAkFVMRMwEQYDVQQIDApTb21lLVN0YXRlMSEwHwYDVQQKDBhJbnRlcm5ldCBX
-----END CERTIFICATE-----""",
    }


class TestSAMLProviderAPICreate:
    """Test POST /api/auth/saml/providers endpoint."""

    def test_create_provider_success(self, sample_provider_data: dict):
        """Test successful creation of SAML provider via API."""
        response = client.post("/api/auth/saml/providers", json=sample_provider_data)

        assert response.status_code == 201
        data = response.json()
        assert data["id"] is not None
        assert data["organization_id"] == sample_provider_data["organization_id"]
        assert data["name"] == sample_provider_data["name"]
        assert data["entity_id"] == sample_provider_data["entity_id"]
        assert data["sso_url"] == sample_provider_data["sso_url"]
        assert data["slo_url"] == sample_provider_data["slo_url"]
        assert data["is_active"] is True
        assert "created_at" in data
        assert "updated_at" in data

    def test_create_provider_without_slo_url(self, sample_provider_data: dict):
        """Test creating provider without optional SLO URL."""
        data = {**sample_provider_data}
        del data["slo_url"]

        response = client.post("/api/auth/saml/providers", json=data)

        assert response.status_code == 201
        result = response.json()
        assert result["slo_url"] is None

    def test_create_provider_missing_required_fields(self):
        """Test creating provider with missing required fields."""
        incomplete_data = {
            "organization_id": "org-123",
            "name": "Test Provider",
        }

        response = client.post("/api/auth/saml/providers", json=incomplete_data)

        assert response.status_code == 422  # Unprocessable Entity

    def test_create_provider_invalid_sso_url(self, sample_provider_data: dict):
        """Test creating provider with invalid SSO URL."""
        data = {**sample_provider_data, "sso_url": "not-a-url"}

        response = client.post("/api/auth/saml/providers", json=data)

        assert response.status_code == 400
        assert "sso_url" in response.json()["detail"].lower()

    def test_create_provider_invalid_certificate(self, sample_provider_data: dict):
        """Test creating provider with invalid X.509 certificate."""
        data = {**sample_provider_data, "x509_cert": "invalid cert"}

        response = client.post("/api/auth/saml/providers", json=data)

        assert response.status_code == 400
        assert "x509_cert" in response.json()["detail"].lower()


class TestSAMLProviderAPIList:
    """Test GET /api/auth/saml/providers endpoint."""

    def test_list_providers_empty(self):
        """Test listing providers when none exist."""
        response = client.get("/api/auth/saml/providers?organization_id=org-empty")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_list_providers_multiple(self, sample_provider_data: dict):
        """Test listing multiple providers for an organization."""
        # Create two providers
        client.post("/api/auth/saml/providers", json=sample_provider_data)
        client.post(
            "/api/auth/saml/providers",
            json={**sample_provider_data, "name": "Azure AD SSO"},
        )

        response = client.get("/api/auth/saml/providers?organization_id=org-123")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all("id" in item for item in data)
        assert all("name" in item for item in data)

    def test_list_providers_missing_organization_id(self):
        """Test listing providers without organization_id parameter."""
        response = client.get("/api/auth/saml/providers")

        assert response.status_code == 422  # Missing required parameter


class TestSAMLProviderAPIGet:
    """Test GET /api/auth/saml/providers/{id} endpoint."""

    def test_get_provider_by_id_success(self, sample_provider_data: dict):
        """Test retrieving a specific provider by ID."""
        # Create provider
        create_response = client.post("/api/auth/saml/providers", json=sample_provider_data)
        provider_id = create_response.json()["id"]

        # Retrieve provider
        response = client.get(f"/api/auth/saml/providers/{provider_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == provider_id
        assert data["name"] == sample_provider_data["name"]
        assert data["entity_id"] == sample_provider_data["entity_id"]

    def test_get_provider_not_found(self):
        """Test retrieving non-existent provider returns 404."""
        response = client.get("/api/auth/saml/providers/non-existent-id")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestSAMLProviderAPIUpdate:
    """Test PUT /api/auth/saml/providers/{id} endpoint."""

    def test_update_provider_success(self, sample_provider_data: dict):
        """Test successful update of SAML provider."""
        # Create provider
        create_response = client.post("/api/auth/saml/providers", json=sample_provider_data)
        provider_id = create_response.json()["id"]

        # Update provider
        updates = {
            "name": "Updated SSO Name",
            "sso_url": "https://updated.example.com/sso",
        }
        response = client.put(f"/api/auth/saml/providers/{provider_id}", json=updates)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == provider_id
        assert data["name"] == "Updated SSO Name"
        assert data["sso_url"] == "https://updated.example.com/sso"
        assert data["entity_id"] == sample_provider_data["entity_id"]  # Unchanged

    def test_update_provider_not_found(self):
        """Test updating non-existent provider returns 404."""
        updates = {"name": "New Name"}
        response = client.put("/api/auth/saml/providers/non-existent-id", json=updates)

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_update_provider_invalid_url(self, sample_provider_data: dict):
        """Test updating provider with invalid URL."""
        # Create provider
        create_response = client.post("/api/auth/saml/providers", json=sample_provider_data)
        provider_id = create_response.json()["id"]

        # Try to update with invalid URL
        updates = {"sso_url": "not-a-url"}
        response = client.put(f"/api/auth/saml/providers/{provider_id}", json=updates)

        assert response.status_code == 400
        assert "sso_url" in response.json()["detail"].lower()

    def test_update_provider_partial_update(self, sample_provider_data: dict):
        """Test partial update (only some fields)."""
        # Create provider
        create_response = client.post("/api/auth/saml/providers", json=sample_provider_data)
        provider_id = create_response.json()["id"]
        original_sso_url = create_response.json()["sso_url"]

        # Update only name
        updates = {"name": "Only Name Changed"}
        response = client.put(f"/api/auth/saml/providers/{provider_id}", json=updates)

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Only Name Changed"
        assert data["sso_url"] == original_sso_url  # Unchanged


class TestSAMLProviderAPIDelete:
    """Test DELETE /api/auth/saml/providers/{id} endpoint."""

    def test_delete_provider_success(self, sample_provider_data: dict):
        """Test successful deletion of SAML provider."""
        # Create provider
        create_response = client.post("/api/auth/saml/providers", json=sample_provider_data)
        provider_id = create_response.json()["id"]

        # Delete provider
        response = client.delete(f"/api/auth/saml/providers/{provider_id}")

        assert response.status_code == 204

        # Verify it's deleted
        get_response = client.get(f"/api/auth/saml/providers/{provider_id}")
        assert get_response.status_code == 404

    def test_delete_provider_not_found(self):
        """Test deleting non-existent provider returns 404."""
        response = client.delete("/api/auth/saml/providers/non-existent-id")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
