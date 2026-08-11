from __future__ import annotations

import hashlib
import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass
class WebBootstrapGrant:
    token_hash: str
    user_id: str
    organization_id: str
    intended_origin: str
    expires_at: datetime
    consumed_at: datetime | None = None


class WebBootstrapStore:
    """Process-local, hashed, single-use browser bootstrap grants."""

    def __init__(self) -> None:
        self._grants: dict[str, WebBootstrapGrant] = {}
        self._lock = threading.Lock()

    def issue(
        self,
        *,
        user_id: str,
        organization_id: str,
        intended_origin: str,
        ttl_seconds: int,
        now: datetime | None = None,
    ) -> tuple[str, datetime]:
        issued_at = now or datetime.now(UTC)
        token = secrets.token_urlsafe(32)
        token_hash = self._hash(token)
        grant = WebBootstrapGrant(
            token_hash=token_hash,
            user_id=user_id,
            organization_id=organization_id,
            intended_origin=intended_origin,
            expires_at=issued_at + timedelta(seconds=ttl_seconds),
        )
        with self._lock:
            self._prune(issued_at)
            self._grants[token_hash] = grant
        return token, grant.expires_at

    def consume(
        self,
        token: str,
        *,
        origin: str,
        now: datetime | None = None,
    ) -> WebBootstrapGrant | None:
        consumed_at = now or datetime.now(UTC)
        token_hash = self._hash(token)
        with self._lock:
            grant = self._grants.get(token_hash)
            if (
                grant is None
                or grant.consumed_at is not None
                or grant.expires_at <= consumed_at
                or grant.intended_origin != origin
            ):
                return None
            grant.consumed_at = consumed_at
            return grant

    def clear(self) -> None:
        with self._lock:
            self._grants.clear()

    def _prune(self, now: datetime) -> None:
        expired = [key for key, grant in self._grants.items() if grant.expires_at <= now]
        for key in expired:
            self._grants.pop(key, None)

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()


WEB_BOOTSTRAP_STORE = WebBootstrapStore()
