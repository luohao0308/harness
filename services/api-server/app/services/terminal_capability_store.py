from __future__ import annotations

import hashlib
import secrets
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from redis import Redis

from app.core.config import get_settings


class TerminalCapabilityStoreUnavailable(RuntimeError):
    """The shared capability store cannot be reached."""


class TerminalSessionLimitReached(RuntimeError):
    """The principal has reached the active terminal session limit."""


@dataclass(frozen=True)
class TerminalTokenRecord:
    token: str
    terminal_id: str
    user_id: str
    organization_id: str
    expires_at: float


@dataclass(frozen=True)
class TerminalSessionReservation:
    session_id: str
    terminal_id: str
    user_id: str
    organization_id: str


class TerminalCapabilityStore(Protocol):
    def issue_token(
        self,
        *,
        terminal_id: str,
        user_id: str,
        organization_id: str,
        now: float | None = None,
    ) -> TerminalTokenRecord: ...

    def consume_and_reserve(
        self,
        *,
        token: str | None,
        terminal_id: str,
        now: float | None = None,
    ) -> tuple[TerminalTokenRecord, TerminalSessionReservation] | None: ...

    def heartbeat(
        self,
        reservation: TerminalSessionReservation,
        *,
        now: float | None = None,
    ) -> bool: ...

    def release(self, reservation: TerminalSessionReservation) -> None: ...


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class InMemoryTerminalCapabilityStore:
    """Single-process fallback used only for local development and tests."""

    def __init__(self, *, token_ttl_seconds: int, max_sessions: int, lease_seconds: int) -> None:
        self.token_ttl_seconds = token_ttl_seconds
        self.max_sessions = max_sessions
        self.lease_seconds = lease_seconds
        self._tokens: dict[str, TerminalTokenRecord] = {}
        self._sessions: dict[str, dict[str, float]] = {}
        self._lock = threading.Lock()

    def issue_token(
        self,
        *,
        terminal_id: str,
        user_id: str,
        organization_id: str,
        now: float | None = None,
    ) -> TerminalTokenRecord:
        current = now if now is not None else time.time()
        with self._lock:
            self._prune(current)
            if self._active_count(user_id, organization_id) >= self.max_sessions:
                raise TerminalSessionLimitReached
            token = secrets.token_urlsafe(32)
            record = TerminalTokenRecord(
                token=token,
                terminal_id=terminal_id,
                user_id=user_id,
                organization_id=organization_id,
                expires_at=current + self.token_ttl_seconds,
            )
            self._tokens[_token_digest(token)] = record
            return record

    def consume_and_reserve(
        self,
        *,
        token: str | None,
        terminal_id: str,
        now: float | None = None,
    ) -> tuple[TerminalTokenRecord, TerminalSessionReservation] | None:
        if not token:
            return None
        current = now if now is not None else time.time()
        with self._lock:
            self._prune(current)
            record = self._tokens.get(_token_digest(token))
            if record is None or record.expires_at <= current or record.terminal_id != terminal_id:
                self._tokens.pop(_token_digest(token), None)
                return None
            if self._active_count(record.user_id, record.organization_id) >= self.max_sessions:
                raise TerminalSessionLimitReached
            self._tokens.pop(_token_digest(token), None)
            session_id = secrets.token_urlsafe(24)
            principal_key = self._principal_key(record.user_id, record.organization_id)
            self._sessions.setdefault(principal_key, {})[session_id] = current + self.lease_seconds
            return record, TerminalSessionReservation(
                session_id=session_id,
                terminal_id=record.terminal_id,
                user_id=record.user_id,
                organization_id=record.organization_id,
            )

    def heartbeat(
        self,
        reservation: TerminalSessionReservation,
        *,
        now: float | None = None,
    ) -> bool:
        current = now if now is not None else time.time()
        with self._lock:
            principal_sessions = self._sessions.get(
                self._principal_key(reservation.user_id, reservation.organization_id),
            )
            if principal_sessions is None or reservation.session_id not in principal_sessions:
                return False
            principal_sessions[reservation.session_id] = current + self.lease_seconds
            return True

    def release(self, reservation: TerminalSessionReservation) -> None:
        with self._lock:
            principal_key = self._principal_key(reservation.user_id, reservation.organization_id)
            principal_sessions = self._sessions.get(principal_key)
            if principal_sessions is None:
                return
            principal_sessions.pop(reservation.session_id, None)
            if not principal_sessions:
                self._sessions.pop(principal_key, None)

    def _prune(self, now: float) -> None:
        for principal_key, sessions in list(self._sessions.items()):
            for session_id, lease_expires_at in list(sessions.items()):
                if lease_expires_at <= now:
                    sessions.pop(session_id, None)
            if not sessions:
                self._sessions.pop(principal_key, None)
        for token_digest, record in list(self._tokens.items()):
            if record.expires_at <= now:
                self._tokens.pop(token_digest, None)

    def _active_count(self, user_id: str, organization_id: str) -> int:
        return len(self._sessions.get(self._principal_key(user_id, organization_id), {}))

    @staticmethod
    def _principal_key(user_id: str, organization_id: str) -> str:
        return f"{organization_id}:{user_id}"


class RedisTerminalCapabilityStore:
    _issue_script = """
    local now = tonumber(ARGV[1])
    local max_sessions = tonumber(ARGV[2])
    redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
    if tonumber(redis.call('ZCARD', KEYS[1])) >= max_sessions then
        return 0
    end
    redis.call('HSET', KEYS[2],
        'terminal_id', ARGV[3],
        'user_id', ARGV[4],
        'organization_id', ARGV[5],
        'expires_at', ARGV[6])
    redis.call('EXPIRE', KEYS[2], tonumber(ARGV[7]))
    return 1
    """

    _consume_script = """
    if redis.call('EXISTS', KEYS[2]) == 0 then
        return {0}
    end
    local stored_terminal_id = redis.call('HGET', KEYS[2], 'terminal_id')
    if stored_terminal_id ~= ARGV[3] then
        redis.call('DEL', KEYS[2])
        return {0}
    end
    local now = tonumber(ARGV[1])
    local expires_at = tonumber(redis.call('HGET', KEYS[2], 'expires_at'))
    if expires_at <= now then
        redis.call('DEL', KEYS[2])
        return {0}
    end
    local max_sessions = tonumber(ARGV[2])
    redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
    if tonumber(redis.call('ZCARD', KEYS[1])) >= max_sessions then
        return {-1}
    end
    local user_id = redis.call('HGET', KEYS[2], 'user_id')
    local organization_id = redis.call('HGET', KEYS[2], 'organization_id')
    redis.call('DEL', KEYS[2])
    redis.call('ZADD', KEYS[1], tonumber(ARGV[5]), ARGV[4])
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[6]))
    return {1, user_id, organization_id, tostring(expires_at)}
    """

    _heartbeat_script = """
    if redis.call('ZSCORE', KEYS[1], ARGV[1]) == false then
        return 0
    end
    redis.call('ZADD', KEYS[1], tonumber(ARGV[2]), ARGV[1])
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
    return 1
    """

    def __init__(
        self,
        client: Redis,
        *,
        token_ttl_seconds: int,
        max_sessions: int,
        lease_seconds: int,
    ) -> None:
        self.client = client
        self.token_ttl_seconds = token_ttl_seconds
        self.max_sessions = max_sessions
        self.lease_seconds = lease_seconds
        self._issue = client.register_script(self._issue_script)
        self._consume = client.register_script(self._consume_script)
        self._heartbeat = client.register_script(self._heartbeat_script)

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        token_ttl_seconds: int,
        max_sessions: int,
        lease_seconds: int,
    ) -> RedisTerminalCapabilityStore:
        from redis import Redis

        return cls(
            Redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=0.25,
                socket_timeout=1.0,
            ),
            token_ttl_seconds=token_ttl_seconds,
            max_sessions=max_sessions,
            lease_seconds=lease_seconds,
        )

    def issue_token(
        self,
        *,
        terminal_id: str,
        user_id: str,
        organization_id: str,
        now: float | None = None,
    ) -> TerminalTokenRecord:
        current = now if now is not None else time.time()
        principal_digest = self._principal_digest(user_id, organization_id)
        token = f"{principal_digest}.{secrets.token_urlsafe(32)}"
        expires_at = current + self.token_ttl_seconds
        try:
            allowed = self._issue(
                keys=[
                    self._sessions_key(principal_digest),
                    self._token_key(token, principal_digest),
                ],
                args=[
                    current,
                    self.max_sessions,
                    terminal_id,
                    user_id,
                    organization_id,
                    expires_at,
                    self.token_ttl_seconds,
                ],
            )
        except Exception as exc:
            from redis.exceptions import RedisError

            if not isinstance(exc, RedisError):
                raise
            raise TerminalCapabilityStoreUnavailable from exc
        if not int(allowed):
            raise TerminalSessionLimitReached
        return TerminalTokenRecord(token, terminal_id, user_id, organization_id, expires_at)

    def consume_and_reserve(
        self,
        *,
        token: str | None,
        terminal_id: str,
        now: float | None = None,
    ) -> tuple[TerminalTokenRecord, TerminalSessionReservation] | None:
        if not token:
            return None
        current = now if now is not None else time.time()
        principal_digest = self._token_principal_digest(token)
        if principal_digest is None:
            return None
        token_key = self._token_key(token, principal_digest)
        try:
            session_id = secrets.token_urlsafe(24)
            result = self._consume(
                keys=[self._sessions_key(principal_digest), token_key],
                args=[
                    current,
                    self.max_sessions,
                    terminal_id,
                    session_id,
                    current + self.lease_seconds,
                    self.lease_seconds * 2,
                ],
            )
        except Exception as exc:
            from redis.exceptions import RedisError

            if not isinstance(exc, RedisError):
                raise
            raise TerminalCapabilityStoreUnavailable from exc
        result = list(result or [])
        if not result or int(result[0]) == 0:
            return None
        if int(result[0]) < 0:
            raise TerminalSessionLimitReached
        record = TerminalTokenRecord(
            token=token,
            terminal_id=terminal_id,
            user_id=str(result[1]),
            organization_id=str(result[2]),
            expires_at=float(result[3]),
        )
        return record, TerminalSessionReservation(
            session_id=session_id,
            terminal_id=terminal_id,
            user_id=record.user_id,
            organization_id=record.organization_id,
        )

    def heartbeat(
        self,
        reservation: TerminalSessionReservation,
        *,
        now: float | None = None,
    ) -> bool:
        current = now if now is not None else time.time()
        try:
            result = self._heartbeat(
                keys=[
                    self._sessions_key(
                        self._principal_digest(reservation.user_id, reservation.organization_id)
                    )
                ],
                args=[reservation.session_id, current + self.lease_seconds, self.lease_seconds * 2],
            )
        except Exception as exc:
            from redis.exceptions import RedisError

            if not isinstance(exc, RedisError):
                raise
            raise TerminalCapabilityStoreUnavailable from exc
        return bool(int(result or 0))

    def release(self, reservation: TerminalSessionReservation) -> None:
        try:
            self.client.zrem(
                self._sessions_key(
                    self._principal_digest(reservation.user_id, reservation.organization_id)
                ),
                reservation.session_id,
            )
        except Exception as exc:
            from redis.exceptions import RedisError

            if not isinstance(exc, RedisError):
                raise
            raise TerminalCapabilityStoreUnavailable from exc

    @staticmethod
    def _token_key(token: str, principal_digest: str) -> str:
        return f"harness:terminal:{{{principal_digest}}}:token:{_token_digest(token)}"

    @staticmethod
    def _sessions_key(principal_digest: str) -> str:
        return f"harness:terminal:{{{principal_digest}}}:sessions"

    @staticmethod
    def _principal_digest(user_id: str, organization_id: str) -> str:
        return hashlib.sha256(f"{organization_id}:{user_id}".encode()).hexdigest()

    @staticmethod
    def _token_principal_digest(token: str) -> str | None:
        principal_digest, separator, _secret = token.partition(".")
        if separator != "." or len(principal_digest) != 64:
            return None
        if any(character not in "0123456789abcdef" for character in principal_digest):
            return None
        return principal_digest


_store: InMemoryTerminalCapabilityStore | RedisTerminalCapabilityStore | None = None


def get_terminal_capability_store(
    *,
    token_ttl_seconds: int,
    max_sessions: int,
    lease_seconds: int,
) -> TerminalCapabilityStore:
    global _store
    settings = get_settings()
    if settings.runtime_profile == "local":
        if not isinstance(_store, InMemoryTerminalCapabilityStore):
            _store = InMemoryTerminalCapabilityStore(
                token_ttl_seconds=token_ttl_seconds,
                max_sessions=max_sessions,
                lease_seconds=lease_seconds,
            )
        return _store
    if _store is not None:
        return _store
    if settings.app_env.strip().lower() == "test":
        _store = InMemoryTerminalCapabilityStore(
            token_ttl_seconds=token_ttl_seconds,
            max_sessions=max_sessions,
            lease_seconds=lease_seconds,
        )
        return _store
    redis_store = RedisTerminalCapabilityStore.from_url(
        settings.redis_url,
        token_ttl_seconds=token_ttl_seconds,
        max_sessions=max_sessions,
        lease_seconds=lease_seconds,
    )
    if settings.app_env.strip().lower() in {"development", "test"}:
        try:
            redis_store.client.ping()
        except Exception as exc:
            from redis.exceptions import RedisError

            if not isinstance(exc, RedisError):
                raise
            _store = InMemoryTerminalCapabilityStore(
                token_ttl_seconds=token_ttl_seconds,
                max_sessions=max_sessions,
                lease_seconds=lease_seconds,
            )
            return _store
    _store = redis_store
    return _store


def set_terminal_capability_store_for_tests(store: TerminalCapabilityStore) -> None:
    global _store
    _store = store


def reset_terminal_capability_store_for_tests() -> None:
    global _store
    _store = None
