from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class WorkspaceAuthorizationGrant:
    user_id: str
    organization_id: str
    profile_id: str
    root_path: Path
    label: str
    expires_at: datetime


class WorkspaceAuthorizationStore:
    def __init__(self) -> None:
        self._grants: dict[str, WorkspaceAuthorizationGrant] = {}
        self._lock = threading.Lock()

    def issue(
        self,
        *,
        signing_secret: str,
        user_id: str,
        organization_id: str,
        profile_id: str,
        root_path: Path,
        label: str,
        ttl_seconds: int,
    ) -> tuple[str, datetime]:
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=ttl_seconds)
        grant = WorkspaceAuthorizationGrant(
            user_id=user_id,
            organization_id=organization_id,
            profile_id=profile_id,
            root_path=root_path,
            label=label,
            expires_at=expires_at,
        )
        nonce = secrets.token_urlsafe(32)
        signature = self._signature(nonce=nonce, grant=grant, signing_secret=signing_secret)
        with self._lock:
            self._prune_locked(now)
            self._grants[nonce] = grant
        return f"hwa1_{nonce}.{signature}", expires_at

    def verify(
        self,
        token: str,
        *,
        signing_secret: str,
        user_id: str,
        organization_id: str,
    ) -> WorkspaceAuthorizationGrant | None:
        if not token.startswith("hwa1_") or "." not in token:
            return None
        nonce, supplied_signature = token[5:].split(".", 1)
        now = datetime.now(UTC)
        with self._lock:
            self._prune_locked(now)
            grant = self._grants.get(nonce)
        if grant is None:
            return None
        expected_signature = self._signature(
            nonce=nonce,
            grant=grant,
            signing_secret=signing_secret,
        )
        if not hmac.compare_digest(supplied_signature, expected_signature):
            return None
        if grant.user_id != user_id or grant.organization_id != organization_id:
            return None
        return grant

    def clear(self) -> None:
        with self._lock:
            self._grants.clear()

    def _prune_locked(self, now: datetime) -> None:
        expired = [nonce for nonce, grant in self._grants.items() if grant.expires_at <= now]
        for nonce in expired:
            self._grants.pop(nonce, None)

    @staticmethod
    def _signature(
        *,
        nonce: str,
        grant: WorkspaceAuthorizationGrant,
        signing_secret: str,
    ) -> str:
        message = "\x00".join(
            (
                nonce,
                grant.user_id,
                grant.organization_id,
                grant.profile_id,
                str(grant.root_path),
                grant.label,
                grant.expires_at.isoformat(),
            )
        ).encode("utf-8")
        return hmac.new(signing_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


WORKSPACE_AUTHORIZATION_STORE = WorkspaceAuthorizationStore()
