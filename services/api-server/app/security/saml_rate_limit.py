from __future__ import annotations

import hashlib
import math
import threading
import time
from dataclasses import dataclass
from typing import Protocol

from fastapi import HTTPException, Request, status
from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings


class SAMLRateLimitStoreUnavailable(RuntimeError):
    """The shared SAML rate-limit store cannot be reached."""


class SAMLRateLimiter(Protocol):
    def consume(self, key: str, *, now: float | None = None) -> int | None: ...

    def reset(self) -> None: ...


@dataclass
class _Window:
    started_at: float
    count: int


class InMemorySAMLRateLimiter:
    """Single-process limiter used for local development and tests."""

    def __init__(self, *, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._windows: dict[str, _Window] = {}
        self._lock = threading.Lock()

    def consume(self, key: str, *, now: float | None = None) -> int | None:
        current = now if now is not None else time.monotonic()
        with self._lock:
            window = self._windows.get(key)
            if window is None or current - window.started_at >= self.window_seconds:
                self._windows[key] = _Window(started_at=current, count=1)
                return None
            if window.count >= self.max_requests:
                remaining = self.window_seconds - (current - window.started_at)
                return max(1, math.ceil(remaining))
            window.count += 1
            return None

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()


class RedisSAMLRateLimiter:
    """Atomic fixed-window limiter shared by production API replicas."""

    _consume_script = """
    local count = redis.call('INCR', KEYS[1])
    if count == 1 then
        redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
    end
    local ttl = redis.call('TTL', KEYS[1])
    if count > tonumber(ARGV[2]) then
        return math.max(ttl, 1)
    end
    return 0
    """

    def __init__(self, client: Redis, *, max_requests: int, window_seconds: int) -> None:
        self.client = client
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._consume = client.register_script(self._consume_script)

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        max_requests: int,
        window_seconds: int,
    ) -> RedisSAMLRateLimiter:
        client = Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=1.0,
            socket_timeout=1.0,
        )
        return cls(client, max_requests=max_requests, window_seconds=window_seconds)

    def consume(self, key: str, *, now: float | None = None) -> int | None:
        del now
        redis_key = f"harness:saml-rate:{{{hashlib.sha256(key.encode()).hexdigest()}}}"
        try:
            retry_after = int(
                self._consume(
                    keys=[redis_key],
                    args=[self.window_seconds, self.max_requests],
                )
            )
        except (RedisError, OSError, ValueError) as exc:
            raise SAMLRateLimitStoreUnavailable from exc
        return retry_after or None

    def reset(self) -> None:
        return


_limiter: SAMLRateLimiter | None = None


def get_saml_rate_limiter() -> SAMLRateLimiter:
    global _limiter
    if _limiter is None:
        settings = get_settings()
        options = {
            "max_requests": settings.saml_rate_limit_max_requests,
            "window_seconds": settings.saml_rate_limit_window_seconds,
        }
        if settings.app_env.strip().lower() in {"development", "test"}:
            _limiter = InMemorySAMLRateLimiter(**options)
        else:
            _limiter = RedisSAMLRateLimiter.from_url(str(settings.redis_url), **options)
    return _limiter


def reset_saml_rate_limiter() -> None:
    global _limiter
    if _limiter is not None:
        _limiter.reset()
    _limiter = None


def enforce_saml_rate_limit(request: Request) -> None:
    settings = get_settings()
    client_host = request.client.host if request.client else "unknown"
    if settings.app_env.strip().lower() == "test":
        forwarded_for = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        client_host = forwarded_for or client_host
    try:
        retry_after = get_saml_rate_limiter().consume(client_host)
    except SAMLRateLimitStoreUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SAML authentication protection is temporarily unavailable",
        ) from exc
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="SAML authentication rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )
