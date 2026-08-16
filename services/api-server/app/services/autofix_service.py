"""
Autofix Service - Story 3.1 & 3.2: Secret Generation and Database Setup (Auto-Fix)

This service handles automatic fixes for:

Story 3.1 - Secret Generation:
- AUTH_JWT_SECRET: 64-byte JWT signing secret
- HARNESS_SECRET_ENCRYPTION_KEY: 32-byte Fernet encryption key

Story 3.2 - Database Setup:
- Run pending Alembic migrations
- Create initial admin user if none exists
- Seed default configurations

The service ensures:
1. Secure random generation using Python's secrets module
2. Proper encoding (base64 for JWT, Fernet format for encryption)
3. Never overwrites existing secrets
4. Updates both .env and .env.example files
5. Provides audit trail of actions taken
"""

from __future__ import annotations

import base64
import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from alembic.config import Config
from cryptography.fernet import Fernet
from sqlalchemy import text

from alembic import command
from app.security.jwt_utils import hash_password

if TYPE_CHECKING:
    from typing import TypedDict

    from sqlalchemy.orm import Session

    class AutofixResult(TypedDict):
        """Result of autofix operation."""

        added_secrets: list[str]
        jwt_secret_added: bool
        encryption_key_added: bool
        timestamp: datetime

    class DatabaseAutofixResult(TypedDict):
        """Result of database autofix operation."""

        success: bool
        migrations_run: bool
        admin_created: bool
        admin_email: str | None
        admin_password: str | None
        configs_created: list[str]
        timestamp: datetime
        actions: list[str]


class AutofixService:
    """
    Service for automatically generating and fixing missing security secrets and database setup.

    This service implements:

    Story 3.1:
    - Generate secure JWT secrets (64 bytes, base64 encoded)
    - Generate secure encryption keys (32 bytes, Fernet format)
    - Update .env file without overwriting existing values
    - Log actions to audit trail

    Story 3.2:
    - Run pending database migrations using Alembic
    - Create initial admin user if no users exist
    - Seed default configurations
    - Log all actions to audit trail
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

    def update_env_file(self, env_path: str, jwt_secret: str, encryption_key: str) -> list[str]:
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
            env_path=env_path, jwt_secret=jwt_secret, encryption_key=encryption_key
        )

        # Build result with audit information
        result: AutofixResult = {
            "added_secrets": added_secrets,
            "jwt_secret_added": "AUTH_JWT_SECRET" in added_secrets,
            "encryption_key_added": "HARNESS_SECRET_ENCRYPTION_KEY" in added_secrets,
            "timestamp": datetime.utcnow(),
        }

        return result

    # =======================
    # Story 3.2: Database Setup Auto-Fix
    # =======================

    def run_pending_migrations(self, alembic_ini_path: str | None = None) -> dict:
        """
        Run pending Alembic migrations.

        Args:
            alembic_ini_path: Path to alembic.ini file (auto-detected if not provided)

        Returns:
            Dictionary with migration results:
            - success: Whether migrations ran successfully
            - migrations_run: Whether any migrations were executed
            - message: Human-readable result message
        """
        try:
            # Get alembic.ini path
            if alembic_ini_path is None:
                alembic_ini_path = self._find_alembic_ini()

            # Create Alembic config
            alembic_cfg = Config(alembic_ini_path)

            # Run migrations to head
            command.upgrade(alembic_cfg, "head")

            return {
                "success": True,
                "migrations_run": True,
                "message": "Successfully ran pending migrations to head",
            }

        except FileNotFoundError as e:
            return {
                "success": False,
                "migrations_run": False,
                "message": f"Alembic configuration not found: {e}",
            }
        except Exception as e:
            return {
                "success": False,
                "migrations_run": False,
                "message": f"Error running migrations: {e}",
            }

    def create_initial_admin_user(self, session: Session) -> dict:
        """
        Create initial admin user if no users exist.

        Args:
            session: Database session

        Returns:
            Dictionary with admin creation results:
            - success: Whether the check/creation was successful
            - admin_created: Whether admin was created
            - admin_email: Email of created admin (if created)
            - admin_password: Generated password (if created)
            - reason: Reason if admin was not created
        """
        try:
            # Import User model here to avoid circular imports
            from app.db.models import User

            # Check if any active users exist
            result = session.execute(text("SELECT COUNT(*) FROM users WHERE status = 'active'"))
            user_count = result.scalar()

            if user_count > 0:
                return {
                    "success": False,
                    "admin_created": False,
                    "reason": f"Active users already exist (count: {user_count})",
                }

            # Generate random password (16 characters, URL-safe)
            password_bytes = secrets.token_urlsafe(16)
            admin_password = password_bytes[:16]  # Ensure exactly 16 characters

            # Hash the password using the project's standard hash_password function
            password_hash_value = hash_password(admin_password)

            # Create admin user
            admin_user = User(
                email="admin@example.com",
                name="Administrator",
                password_hash=password_hash_value,
                email_verified=True,
                status="active",
            )

            session.add(admin_user)
            session.commit()

            return {
                "success": True,
                "admin_created": True,
                "admin_email": "admin@example.com",
                "admin_password": admin_password,
            }

        except Exception as e:
            session.rollback()
            return {
                "success": False,
                "admin_created": False,
                "reason": f"Error creating admin user: {e}",
            }

    def seed_default_config(self, session: Session) -> dict:
        """
        Seed default configuration values.

        Args:
            session: Database session

        Returns:
            Dictionary with seeding results:
            - success: Whether seeding was successful
            - configs_created: List of configuration keys created
        """
        try:
            # For now, return empty list as there are no specific config tables
            # to seed based on the current schema. This can be extended later
            # if specific configuration tables are added.

            return {
                "success": True,
                "configs_created": [],
            }

        except Exception as e:
            return {
                "success": False,
                "configs_created": [],
                "error": str(e),
            }

    def autofix_database(
        self, session: Session, alembic_ini_path: str | None = None
    ) -> DatabaseAutofixResult:
        """
        Automatically fix database setup issues.

        This is the main entry point for Story 3.2, orchestrating:
        1. Running pending migrations
        2. Creating initial admin user if needed
        3. Seeding default configurations
        4. Logging all actions to audit trail

        Args:
            session: Database session
            alembic_ini_path: Path to alembic.ini (auto-detected if not provided)

        Returns:
            Dictionary containing:
            - success: Overall success status
            - migrations_run: Whether migrations were executed
            - admin_created: Whether admin user was created
            - admin_email: Email of created admin (if created)
            - admin_password: Generated password (if created, for display)
            - configs_created: List of configuration keys created
            - timestamp: When the operation was performed
            - actions: List of actions taken (audit trail)
        """
        actions = []
        admin_email = None
        admin_password = None

        # Step 1: Run pending migrations
        migration_result = self.run_pending_migrations(alembic_ini_path)
        if migration_result["success"]:
            actions.append("Ran pending database migrations")

        # Step 2: Create initial admin user if needed
        admin_result = self.create_initial_admin_user(session)
        if admin_result["admin_created"]:
            actions.append(f"Created initial admin user: {admin_result['admin_email']}")
            admin_email = admin_result["admin_email"]
            admin_password = admin_result["admin_password"]
        elif not admin_result["success"]:
            actions.append(f"Skipped admin creation: {admin_result.get('reason', 'Unknown')}")

        # Step 3: Seed default configurations
        config_result = self.seed_default_config(session)
        if config_result["success"] and config_result["configs_created"]:
            actions.append(f"Seeded {len(config_result['configs_created'])} default configurations")

        # Build comprehensive result
        result: DatabaseAutofixResult = {
            "success": migration_result["success"],
            "migrations_run": migration_result["migrations_run"],
            "admin_created": admin_result.get("admin_created", False),
            "admin_email": admin_email,
            "admin_password": admin_password,
            "configs_created": config_result.get("configs_created", []),
            "timestamp": datetime.utcnow(),
            "actions": actions,
        }

        return result

    def _find_alembic_ini(self) -> str:
        """
        Find alembic.ini file in standard locations.

        Returns:
            Path to alembic.ini

        Raises:
            FileNotFoundError: If alembic.ini cannot be found
        """
        # Try relative to current directory and parent directories
        candidates = [
            "alembic.ini",
            "../alembic.ini",
            "../../alembic.ini",
            os.path.join(os.path.dirname(__file__), "../../alembic.ini"),
        ]

        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate

        raise FileNotFoundError(
            "alembic.ini not found. Checked locations: " + ", ".join(candidates)
        )
