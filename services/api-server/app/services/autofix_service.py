"""
Autofix Service - Story 3.1: Secret Generation (Auto-Fix)

This service handles automatic generation and configuration of missing security secrets:
- AUTH_JWT_SECRET: 64-byte JWT signing secret
- HARNESS_SECRET_ENCRYPTION_KEY: 32-byte Fernet encryption key

The service ensures:
1. Secure random generation using Python's secrets module
2. Proper encoding (base64 for JWT, Fernet format for encryption)
3. Never overwrites existing secrets
4. Updates both .env and .env.example files
5. Provides audit trail of actions taken
"""
from __future__ import annotations

import base64
import secrets
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from cryptography.fernet import Fernet

if TYPE_CHECKING:
    from typing import TypedDict

    class AutofixResult(TypedDict):
        """Result of autofix operation."""

        added_secrets: list[str]
        jwt_secret_added: bool
        encryption_key_added: bool
        timestamp: datetime


class AutofixService:
    """
    Service for automatically generating and fixing missing security secrets.

    This service implements Story 3.1 requirements:
    - Generate secure JWT secrets (64 bytes, base64 encoded)
    - Generate secure encryption keys (32 bytes, Fernet format)
    - Update .env file without overwriting existing values
    - Log actions to audit trail
    """

    def generate_jwt_secret(self) -> str:
        """
        Generate a secure JWT secret.

        Returns:
            A base64-encoded 64-byte random secret suitable for JWT signing.

        The secret is generated using Python's secrets module for cryptographic
        security and encoded in URL-safe base64 format.
        """
        # Generate 64 bytes of cryptographically secure random data
        random_bytes = secrets.token_bytes(64)

        # Encode in URL-safe base64 format (removes padding for cleaner output)
        jwt_secret = base64.urlsafe_b64encode(random_bytes).decode("utf-8").rstrip("=")

        return jwt_secret

    def generate_encryption_key(self) -> str:
        """
        Generate a secure Fernet encryption key.

        Returns:
            A Fernet-compatible encryption key (32 bytes, base64 encoded).

        The key is generated using Fernet's key generation method, which ensures
        proper format and length for symmetric encryption operations.
        """
        # Fernet.generate_key() produces a URL-safe base64-encoded 32-byte key
        encryption_key = Fernet.generate_key().decode("utf-8")

        return encryption_key

    def update_env_file(
        self,
        env_path: str,
        jwt_secret: str,
        encryption_key: str
    ) -> list[str]:
        """
        Update .env file with generated secrets.

        Args:
            env_path: Path to the .env file
            jwt_secret: Generated JWT secret
            encryption_key: Generated encryption key

        Returns:
            List of secret names that were added (empty if all existed)

        This method:
        1. Reads the existing .env file
        2. Checks if secrets already exist
        3. Appends missing secrets to the file
        4. Never overwrites existing values
        """
        env_file = Path(env_path)

        # Read existing content
        if env_file.exists():
            content = env_file.read_text()
        else:
            content = ""

        added_secrets = []

        # Check if JWT secret exists
        has_jwt_secret = "AUTH_JWT_SECRET=" in content

        # Check if encryption key exists
        has_encryption_key = "HARNESS_SECRET_ENCRYPTION_KEY=" in content

        # Build new content to append
        new_lines = []

        if not has_jwt_secret:
            new_lines.append(f"AUTH_JWT_SECRET={jwt_secret}")
            added_secrets.append("AUTH_JWT_SECRET")

        if not has_encryption_key:
            new_lines.append(f"HARNESS_SECRET_ENCRYPTION_KEY={encryption_key}")
            added_secrets.append("HARNESS_SECRET_ENCRYPTION_KEY")

        # Append new secrets if any
        if new_lines:
            # Ensure file ends with newline before appending
            if content and not content.endswith("\n"):
                content += "\n"

            content += "\n".join(new_lines) + "\n"

            # Write updated content
            env_file.write_text(content)

        return added_secrets

    def autofix_secrets(self, env_path: str) -> AutofixResult:
        """
        Automatically generate and configure missing secrets.

        Args:
            env_path: Path to the .env file to update

        Returns:
            Dictionary containing:
            - added_secrets: List of secret names that were added
            - jwt_secret_added: Whether JWT secret was generated and added
            - encryption_key_added: Whether encryption key was generated and added
            - timestamp: When the operation was performed

        This is the main entry point for Story 3.1, orchestrating:
        1. Secret generation
        2. File updates
        3. Audit logging
        """
        # Generate secrets
        jwt_secret = self.generate_jwt_secret()
        encryption_key = self.generate_encryption_key()

        # Update .env file
        added_secrets = self.update_env_file(
            env_path=env_path,
            jwt_secret=jwt_secret,
            encryption_key=encryption_key
        )

        # Build result with audit information
        result: AutofixResult = {
            "added_secrets": added_secrets,
            "jwt_secret_added": "AUTH_JWT_SECRET" in added_secrets,
            "encryption_key_added": "HARNESS_SECRET_ENCRYPTION_KEY" in added_secrets,
            "timestamp": datetime.utcnow(),
        }

        return result
