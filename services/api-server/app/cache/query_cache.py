from __future__ import annotations

import json
import time
from collections.abc import Callable
from functools import wraps
from threading import Lock
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar

from pydantic import BaseModel

if TYPE_CHECKING:
    from redis import Redis

from app.core.config import get_settings
from app.observability.metrics import query_cache_hit_total, query_cache_miss_total

P = ParamSpec("P")
R = TypeVar("R")


class QueryCache:
    def __init__(self) -> None:
        self._redis: Redis | None = None
        self._redis_failed = False
        self._memory: dict[str, tuple[float, str]] = {}
        self._lock = Lock()

    def clear_memory(self) -> None:
        with self._lock:
            self._memory.clear()

    def get(self, key: str) -> Any | None:
        payload: str | bytes | None = None
        client = self._client()
        if client is not None:
            try:
                payload = client.get(key)
            except Exception:
                self._redis_failed = True
                payload = None
        if payload is None:
            payload = self._get_memory(key)
        if payload is None:
            return None
        try:
            if isinstance(payload, bytes):
                payload = payload.decode("utf-8")
            return json.loads(payload)
        except json.JSONDecodeError:
            return None

    def get_with_metrics(self, key: str, *, entity: str) -> Any | None:
        value = self.get(key)
        if value is None:
            query_cache_miss_total.labels(entity=entity).inc()
        else:
            query_cache_hit_total.labels(entity=entity).inc()
        return value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        payload = json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True, default=str)
        client = self._client()
        if client is not None:
            try:
                client.setex(key, ttl_seconds, payload)
                return
            except Exception:
                self._redis_failed = True
        expires_at = time.time() + ttl_seconds
        with self._lock:
            self._memory[key] = (expires_at, payload)

    def delete_prefix(self, prefix: str) -> int:
        deleted = 0
        client = self._client()
        if client is not None:
            try:
                for key in client.scan_iter(f"{prefix}*"):
                    deleted += int(client.delete(key))
            except Exception:
                self._redis_failed = True
        with self._lock:
            for key in list(self._memory):
                if key.startswith(prefix):
                    del self._memory[key]
                    deleted += 1
        return deleted

    def _get_memory(self, key: str) -> str | None:
        with self._lock:
            record = self._memory.get(key)
            if record is None:
                return None
            expires_at, payload = record
            if expires_at < time.time():
                del self._memory[key]
                return None
            return payload

    def _client(self) -> Redis | None:
        if get_settings().runtime_profile == "local":
            return None
        if self._redis_failed:
            return None
        if self._redis is None:
            try:
                from redis import Redis

                self._redis = Redis.from_url(get_settings().redis_url, socket_connect_timeout=0.05)
            except Exception:
                self._redis_failed = True
                return None
        return self._redis


query_cache = QueryCache()


def cached(
    *,
    key_fn: Callable[P, str],
    ttl_seconds: int = 60,
    entity: str = "unknown",
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorator(function: Callable[P, R]) -> Callable[P, R]:
        @wraps(function)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            key = key_fn(*args, **kwargs)
            cached_value = query_cache.get(key)
            if cached_value is not None:
                query_cache_hit_total.labels(entity=entity).inc()
                return cached_value  # type: ignore[return-value]
            query_cache_miss_total.labels(entity=entity).inc()
            value = function(*args, **kwargs)
            query_cache.set(key, value, ttl_seconds)
            return value

        return wrapper

    return decorator


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value
