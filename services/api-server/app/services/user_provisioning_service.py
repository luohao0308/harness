"""
User Provisioning Service for SAML SSO

Story 2.3 - User Provisioning from SAML
Handles Just-In-Time (JIT) user provisioning, attribute mapping, and role assignment.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import User, UserExternalId


class UserProvisioningService:
    """
    Service for provisioning users from SAML authentication.

    Handles:
    - Just-In-Time (JIT) provisioning (create user on first SSO login)
    - User attribute mapping (SAML attributes → local user fields)
    - Role assignment based on SAML groups
    - Update existing users on subsequent logins
    - Store external user ID in user_external_ids table
    """

    def __init__(self, db_session: Session) -> None:
        """
        Initialize user provisioning service.

        Args:
            db_session: SQLAlchemy database session.
        """
        self.db = db_session

    def provision_user_from_saml(
        self,
        saml_claims: dict[str, Any],
        idp_entity_id: str,
        subject_id: str,
    ) -> User:
        """
        Provision or update user from SAML claims (JIT provisioning).

        Creates a new user on first login, or updates existing user on subsequent logins.
        Stores external identity mapping in user_external_ids table.

        Args:
            saml_claims: SAML user claims (email, name, groups).
            idp_entity_id: Identity Provider entity ID.
            subject_id: SAML subject identifier (NameID).

        Returns:
            User object (created or updated).

        Raises:
            ValueError: If required attributes are missing.
        """
        # Validate required attributes
        if "email" not in saml_claims or not saml_claims["email"]:
            raise ValueError("Email is required for user provisioning")

        email = saml_claims["email"]

        # Check if user already exists
        existing_user = self.db.query(User).filter(User.email == email).first()

        if existing_user:
            # Update existing user
            updated_user = self._update_existing_user(existing_user, saml_claims)
            self._update_or_create_external_id(updated_user, idp_entity_id, subject_id)
            return updated_user
        else:
            # Create new user (JIT provisioning)
            new_user = self._create_new_user(saml_claims)
            self._create_external_id(new_user, idp_entity_id, subject_id)
            return new_user

    def map_saml_attributes(self, saml_claims: dict[str, Any]) -> dict[str, Any]:
        """
        Map SAML attributes to local user fields.

        Maps SAML assertion attributes to the User model fields.

        Args:
            saml_claims: SAML user claims (email, name, groups).

        Returns:
            Dictionary with mapped user attributes.
        """
        return {
            "email": saml_claims["email"],
            "name": saml_claims["name"],
            "email_verified": True,  # SAML users are pre-verified
            "status": "active",
        }

    def assign_roles_from_groups(self, groups: list[str]) -> str:
        """
        Assign user role based on SAML groups.

        Role assignment logic:
        - 'admin' if 'admin' group is present (case-insensitive)
        - 'user' as default role

        Args:
            groups: List of SAML group names.

        Returns:
            Role name ('admin' or 'user').
        """
        # Normalize groups to lowercase for case-insensitive matching
        normalized_groups = [g.lower() for g in groups]

        # Check for admin group
        if "admin" in normalized_groups:
            return "admin"

        # Default role
        return "user"

    def update_user_attributes(
        self,
        user: User,
        attributes: dict[str, Any],
    ) -> User:
        """
        Update existing user attributes.

        Args:
            user: User object to update.
            attributes: Dictionary of attributes to update.

        Returns:
            Updated User object.
        """
        # Update allowed attributes
        if "name" in attributes:
            user.name = attributes["name"]
        if "email_verified" in attributes:
            user.email_verified = attributes["email_verified"]
        if "status" in attributes:
            user.status = attributes["status"]

        # Update last login timestamp
        user.last_login_at = datetime.now(UTC)
        user.updated_at = datetime.now(UTC)

        self.db.commit()
        self.db.refresh(user)

        return user

    def _create_new_user(self, saml_claims: dict[str, Any]) -> User:
        """
        Create a new user from SAML claims.

        Args:
            saml_claims: SAML user claims.

        Returns:
            Newly created User object.
        """
        # Map SAML attributes
        mapped_attrs = self.map_saml_attributes(saml_claims)

        # Determine role from groups
        groups = saml_claims.get("groups", [])
        role = self.assign_roles_from_groups(groups)

        # Create user
        user = User(
            email=mapped_attrs["email"],
            name=mapped_attrs["name"],
            password_hash=self._generate_random_password_hash(),
            email_verified=mapped_attrs["email_verified"],
            status=mapped_attrs["status"],
            last_login_at=datetime.now(UTC),
        )

        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

        return user

    def _update_existing_user(
        self,
        user: User,
        saml_claims: dict[str, Any],
    ) -> User:
        """
        Update existing user from SAML claims.

        Args:
            user: Existing user to update.
            saml_claims: SAML user claims.

        Returns:
            Updated User object.
        """
        # Map SAML attributes
        mapped_attrs = self.map_saml_attributes(saml_claims)

        # Update user attributes
        return self.update_user_attributes(user, mapped_attrs)

    def _create_external_id(
        self,
        user: User,
        idp_entity_id: str,
        subject_id: str,
    ) -> UserExternalId:
        """
        Create external identity mapping.

        Args:
            user: User object.
            idp_entity_id: Identity Provider entity ID.
            subject_id: SAML subject identifier.

        Returns:
            Created UserExternalId object.
        """
        external_id = UserExternalId(
            user_id=user.id,
            provider="saml",
            external_entity_id=idp_entity_id,
            external_user_id=subject_id,
        )

        self.db.add(external_id)
        self.db.commit()
        self.db.refresh(external_id)

        return external_id

    def _update_or_create_external_id(
        self,
        user: User,
        idp_entity_id: str,
        subject_id: str,
    ) -> UserExternalId:
        """
        Update or create external identity mapping.

        Args:
            user: User object.
            idp_entity_id: Identity Provider entity ID.
            subject_id: SAML subject identifier.

        Returns:
            UserExternalId object.
        """
        # Check if external ID already exists
        existing_external_id = (
            self.db.query(UserExternalId)
            .filter(
                UserExternalId.user_id == user.id,
                UserExternalId.provider == "saml",
                UserExternalId.external_entity_id == idp_entity_id,
            )
            .first()
        )

        if existing_external_id:
            # Update subject ID if changed
            existing_external_id.external_user_id = subject_id
            existing_external_id.updated_at = datetime.now(UTC)
            self.db.commit()
            self.db.refresh(existing_external_id)
            return existing_external_id
        else:
            # Create new external ID mapping
            return self._create_external_id(user, idp_entity_id, subject_id)

    def _generate_random_password_hash(self) -> str:
        """
        Generate a random password hash for SAML users.

        SAML users don't use password authentication, but the field is required.
        Generate a secure random hash that cannot be used for login.

        Returns:
            SHA256 hash of a random token.
        """
        random_password = secrets.token_urlsafe(32)
        return hashlib.sha256(random_password.encode()).hexdigest()
