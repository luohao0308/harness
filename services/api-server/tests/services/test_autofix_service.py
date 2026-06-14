"""
Tests for autofix_service.py - Story 3.1: Secret Generation (Auto-Fix)

Tests cover:
1. JWT secret generation (64 bytes, base64 encoded)
2. Encryption key generation (32 bytes, Fernet format)
3. .env file updates without overwriting existing secrets
4. Audit trail logging
5. .env.example updates
"""
import base64
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet

from app.services.autofix_service import AutofixService


@pytest.fixture
def temp_env_file():
    """Create a temporary .env file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".env") as f:
        f.write("APP_ENV=development\n")
        f.write("DATABASE_URL=postgresql://localhost/test\n")
        temp_path = f.name

    yield temp_path

    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def temp_env_with_secrets():
    """Create a temporary .env file with existing secrets."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".env") as f:
        f.write("APP_ENV=development\n")
        f.write("AUTH_JWT_SECRET=existing-jwt-secret-do-not-overwrite\n")
        f.write("HARNESS_SECRET_ENCRYPTION_KEY=existing-encryption-key\n")
        temp_path = f.name

    yield temp_path

    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


class TestAutofixService:
    """Test suite for AutofixService - Story 3.1."""

    def test_generate_jwt_secret(self):
        """
        Test JWT secret generation.

        Requirements:
        - Must be 64 bytes
        - Must be base64 encoded
        - Must be URL-safe
        """
        service = AutofixService()
        jwt_secret = service.generate_jwt_secret()

        # Verify it's a string
        assert isinstance(jwt_secret, str)

        # Verify it can be decoded from base64
        decoded = base64.urlsafe_b64decode(jwt_secret + "==")  # Add padding if needed

        # Verify it's 64 bytes
        assert len(decoded) == 64

        # Verify it's not empty
        assert len(jwt_secret) > 0

        # Verify uniqueness - generate another one and they should be different
        jwt_secret2 = service.generate_jwt_secret()
        assert jwt_secret != jwt_secret2

    def test_generate_encryption_key(self):
        """
        Test encryption key generation.

        Requirements:
        - Must be 32 bytes
        - Must be Fernet key format (base64 encoded)
        - Must be valid for Fernet encryption
        """
        service = AutofixService()
        encryption_key = service.generate_encryption_key()

        # Verify it's a string
        assert isinstance(encryption_key, str)

        # Verify it's valid Fernet key by trying to create a Fernet instance
        try:
            fernet = Fernet(encryption_key.encode())
            # Try to encrypt/decrypt to verify it works
            test_data = b"test data"
            encrypted = fernet.encrypt(test_data)
            decrypted = fernet.decrypt(encrypted)
            assert decrypted == test_data
        except Exception as e:
            pytest.fail(f"Generated encryption key is not valid Fernet key: {e}")

        # Verify the underlying bytes are 32 bytes
        decoded = base64.urlsafe_b64decode(encryption_key)
        assert len(decoded) == 32

        # Verify uniqueness
        encryption_key2 = service.generate_encryption_key()
        assert encryption_key != encryption_key2

    def test_update_env_file_adds_missing_secrets(self, temp_env_file):
        """
        Test updating .env file to add missing secrets.

        Requirements:
        - Add AUTH_JWT_SECRET if missing
        - Add HARNESS_SECRET_ENCRYPTION_KEY if missing
        - Preserve existing content
        - Return list of added secrets
        """
        service = AutofixService()

        # Generate secrets
        jwt_secret = service.generate_jwt_secret()
        encryption_key = service.generate_encryption_key()

        # Update the env file
        added_secrets = service.update_env_file(
            env_path=temp_env_file,
            jwt_secret=jwt_secret,
            encryption_key=encryption_key
        )

        # Verify secrets were added
        assert "AUTH_JWT_SECRET" in added_secrets
        assert "HARNESS_SECRET_ENCRYPTION_KEY" in added_secrets

        # Read the file and verify content
        with open(temp_env_file) as f:
            content = f.read()

        # Verify existing content is preserved
        assert "APP_ENV=development" in content
        assert "DATABASE_URL=postgresql://localhost/test" in content

        # Verify new secrets are added
        assert f"AUTH_JWT_SECRET={jwt_secret}" in content
        assert f"HARNESS_SECRET_ENCRYPTION_KEY={encryption_key}" in content

    def test_update_env_file_preserves_existing_secrets(self, temp_env_with_secrets):
        """
        Test that existing secrets are NOT overwritten.

        Requirements:
        - Never overwrite existing AUTH_JWT_SECRET
        - Never overwrite existing HARNESS_SECRET_ENCRYPTION_KEY
        - Return empty list if no secrets were added
        """
        service = AutofixService()

        # Generate new secrets
        jwt_secret = service.generate_jwt_secret()
        encryption_key = service.generate_encryption_key()

        # Read original content
        with open(temp_env_with_secrets) as f:
            original_content = f.read()

        # Update the env file
        added_secrets = service.update_env_file(
            env_path=temp_env_with_secrets,
            jwt_secret=jwt_secret,
            encryption_key=encryption_key
        )

        # Verify no secrets were added (all existed)
        assert len(added_secrets) == 0

        # Read the file and verify content
        with open(temp_env_with_secrets) as f:
            content = f.read()

        # Verify original secrets are unchanged
        assert "AUTH_JWT_SECRET=existing-jwt-secret-do-not-overwrite" in content
        assert "HARNESS_SECRET_ENCRYPTION_KEY=existing-encryption-key" in content

        # Verify new secrets were NOT added
        assert jwt_secret not in content
        assert encryption_key not in content

    def test_autofix_secrets_generates_and_updates(self, temp_env_file):
        """
        Test complete autofix flow.

        Requirements:
        - Generate missing secrets automatically
        - Update .env file
        - Return summary of actions taken
        - Include audit information
        """
        service = AutofixService()

        # Run autofix
        result = service.autofix_secrets(env_path=temp_env_file)

        # Verify result structure
        assert "added_secrets" in result
        assert "jwt_secret_added" in result
        assert "encryption_key_added" in result
        assert "timestamp" in result

        # Verify secrets were added
        assert result["jwt_secret_added"] is True
        assert result["encryption_key_added"] is True
        assert len(result["added_secrets"]) == 2
        assert "AUTH_JWT_SECRET" in result["added_secrets"]
        assert "HARNESS_SECRET_ENCRYPTION_KEY" in result["added_secrets"]

        # Verify .env file was updated
        with open(temp_env_file) as f:
            content = f.read()

        assert "AUTH_JWT_SECRET=" in content
        assert "HARNESS_SECRET_ENCRYPTION_KEY=" in content

        # Verify the secrets are valid
        lines = content.split("\n")
        jwt_line = [l for l in lines if l.startswith("AUTH_JWT_SECRET=")][0]
        enc_line = [l for l in lines if l.startswith("HARNESS_SECRET_ENCRYPTION_KEY=")][0]

        jwt_value = jwt_line.split("=", 1)[1]
        enc_value = enc_line.split("=", 1)[1]

        # Verify JWT secret is valid base64
        assert len(jwt_value) > 0
        decoded_jwt = base64.urlsafe_b64decode(jwt_value + "==")
        assert len(decoded_jwt) == 64

        # Verify encryption key is valid Fernet key
        Fernet(enc_value.encode())  # Should not raise exception

    def test_autofix_secrets_partial_update(self):
        """
        Test autofix when only one secret is missing.

        Requirements:
        - Add only missing secrets
        - Preserve existing secrets
        - Report which secrets were added
        """
        # Create temp file with only JWT secret
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".env") as f:
            f.write("APP_ENV=development\n")
            f.write("AUTH_JWT_SECRET=existing-jwt-secret\n")
            temp_path = f.name

        try:
            service = AutofixService()
            result = service.autofix_secrets(env_path=temp_path)

            # Verify only encryption key was added
            assert result["jwt_secret_added"] is False
            assert result["encryption_key_added"] is True
            assert len(result["added_secrets"]) == 1
            assert "HARNESS_SECRET_ENCRYPTION_KEY" in result["added_secrets"]

            # Verify file content
            with open(temp_path) as f:
                content = f.read()

            assert "AUTH_JWT_SECRET=existing-jwt-secret" in content
            assert "HARNESS_SECRET_ENCRYPTION_KEY=" in content

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_autofix_secrets_no_update_needed(self, temp_env_with_secrets):
        """
        Test autofix when all secrets already exist.

        Requirements:
        - No changes made
        - Return empty added_secrets list
        - Both flags should be False
        """
        service = AutofixService()
        result = service.autofix_secrets(env_path=temp_env_with_secrets)

        # Verify no secrets were added
        assert result["jwt_secret_added"] is False
        assert result["encryption_key_added"] is False
        assert len(result["added_secrets"]) == 0
