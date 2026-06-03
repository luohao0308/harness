from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Iterator
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from urllib import error, request
from urllib.parse import urljoin

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    ContextAssemblyManifest,
    ModelCall,
    PromptAssemblyManifest,
    SystemSetting,
    Task,
    utc_now,
)
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.observability.metrics import (
    model_call_duration_seconds,
    model_call_errors_total,
    model_calls_total,
    model_fallback_total,
    model_tokens_input_total,
    model_tokens_output_total,
)
from app.observability.tracing import traced_operation
from app.security.secrets import (
    SECRET_PURPOSE_MODEL_PROVIDER,
    SECRET_SCOPE_ORG,
    SECRET_SOURCE_ORG,
    env_candidates_for_provider,
    resolve_secret,
    upsert_secret,
)


class ModelMessage(BaseModel):
    role: str
    content: str


class ModelRequest(BaseModel):
    model_provider: str
    model_name: str
    messages: list[ModelMessage]
    response_format: str = "json"


class ModelResponse(BaseModel):
    content: str
    model_provider: str
    model_name: str
    usage: dict = Field(default_factory=dict)
    raw_response: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Streaming chunk contract (v4 streaming uplift — bugfix: true token-by-token
# streaming via upstream SSE APIs instead of single-block `complete`).
#
# Gateways expose an iterator of `ModelStreamChunk`:
#   - `text`  — incremental delta to append to the assistant content.
#   - `usage` — final token accounting (only set on the last chunk).
#   - `done`  — terminal marker; guarantees no further text/usage chunks.
#
# Chunks are additive: downstream consumers accumulate `text` as it arrives
# and commit the `usage` + `raw_response` once `done === True`.
# ---------------------------------------------------------------------------
@dataclass
class ModelStreamChunk:
    text: str = ""
    usage: dict | None = None
    raw_response: dict | None = None
    done: bool = False


class ModelGatewayError(RuntimeError):
    pass


MODEL_SETTINGS_KEY = "settings.models"
LEGACY_BUILTIN_PROVIDER_NAMES = {"minimax", "deepseek"}
LEGACY_BUILTIN_MODEL_NAMES = {
    "deepseek-chat",
    "deepseek-reasoner",
    "MiniMax-M2.7-highspeed",
}
DEEPSEEK_CONTEXT_WINDOW_TOKENS = 1_000_000
DEEPSEEK_MAX_OUTPUT_TOKENS = 384_000
DEEPSEEK_API_KEY_ENV = "DEEPSEEK_API_KEY"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

DEEPSEEK_FLASH_PROVIDER = {
    "name": "deepseek-flash",
    "label": "DeepSeek Flash",
    "status": "healthy",
    "api_format": "openai",
    "model": "deepseek-v4-flash",
    "base_url": DEEPSEEK_BASE_URL,
    "api_key": "replace-me",
    "api_key_env": DEEPSEEK_API_KEY_ENV,
    "model_context_window_tokens": DEEPSEEK_CONTEXT_WINDOW_TOKENS,
    "max_output_tokens": DEEPSEEK_MAX_OUTPUT_TOKENS,
    "rate_limit_rpm": 300,
    "rate_limit_tpm": DEEPSEEK_CONTEXT_WINDOW_TOKENS,
    "timeout_seconds": 60,
    "health_timeout_seconds": 20,
    "circuit_breaker": {
        "failure_threshold": 3,
        "cooldown_seconds": 60,
    },
}

DEEPSEEK_PRO_PROVIDER = {
    **deepcopy(DEEPSEEK_FLASH_PROVIDER),
    "name": "deepseek-pro",
    "label": "DeepSeek Pro",
    "model": "deepseek-v4-pro",
}


DEFAULT_MODEL_SETTINGS = {
    "default_provider": "deepseek-flash",
    "default_model": "deepseek-v4-flash",
    "providers": [
        DEEPSEEK_FLASH_PROVIDER,
        DEEPSEEK_PRO_PROVIDER,
        {
            "name": "openai-compatible",
            "label": "OpenAI GPT-5.5",
            "model": "gpt-5.5",
            "api_format": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_key": "",
            "api_key_env": "OPENAI_API_KEY",
            "model_context_window_tokens": 272000,
            "max_output_tokens": 128000,
            "status": "healthy",
            "rate_limit_rpm": 600,
            "rate_limit_tpm": 120000,
            "timeout_seconds": 30,
            "health_timeout_seconds": 5,
            "circuit_breaker": {
                "failure_threshold": 3,
                "cooldown_seconds": 60,
            },
        },
    ],
    "rate_limits": {"rpm": 600, "tpm": 120000},
    "health": {
        "status": "healthy",
        "updated_at": None,
        "mode": "mock",
        "latency_ms": 0,
        "error_message": None,
    },
    "circuit_breaker": {"failure_threshold": 3, "cooldown_seconds": 60},
}


def normalize_model_settings(settings: dict | None) -> dict:
    """Merge persisted settings with current built-in provider invariants."""
    if not isinstance(settings, dict):
        normalized = deepcopy(DEFAULT_MODEL_SETTINGS)
    else:
        normalized = deepcopy(settings)
    defaults = deepcopy(DEFAULT_MODEL_SETTINGS)
    normalized.setdefault("default_provider", defaults["default_provider"])
    if not normalized.get("default_model") or normalized.get("default_model") == "default":
        normalized["default_model"] = defaults["default_model"]
    normalized.setdefault("providers", [])
    normalized.setdefault("rate_limits", defaults["rate_limits"])
    normalized.setdefault("health", defaults["health"])
    normalized.setdefault("circuit_breaker", defaults["circuit_breaker"])
    if normalized.get("default_provider") in LEGACY_BUILTIN_PROVIDER_NAMES:
        normalized["default_provider"] = defaults["default_provider"]
    if normalized.get("default_model") in LEGACY_BUILTIN_MODEL_NAMES:
        normalized["default_model"] = defaults["default_model"]

    providers = normalized["providers"]
    if not isinstance(providers, list):
        providers = []
        normalized["providers"] = providers
    providers[:] = [
        provider
        for provider in providers
        if not (
            isinstance(provider, dict) and provider.get("name") in LEGACY_BUILTIN_PROVIDER_NAMES
        )
    ]
    for provider in defaults["providers"]:
        if provider.get("name") in {"deepseek-flash", "deepseek-pro"}:
            _upsert_builtin_deepseek_provider(providers=providers, default_provider=provider)
    return normalized


def _upsert_builtin_deepseek_provider(*, providers: list, default_provider: dict) -> None:
    forced_keys = {
        "label",
        "api_format",
        "model",
        "base_url",
        "api_key_env",
        "model_context_window_tokens",
        "max_output_tokens",
        "rate_limit_tpm",
        "health_timeout_seconds",
    }
    for index, provider in enumerate(providers):
        if isinstance(provider, dict) and provider.get("name") == default_provider["name"]:
            merged = {**deepcopy(default_provider), **deepcopy(provider)}
            for key in forced_keys:
                merged[key] = deepcopy(default_provider[key])
            providers[index] = merged
            return
    providers.append(deepcopy(default_provider))


@dataclass(frozen=True)
class ResolvedModelSettings:
    organization_id: str | None
    owner_user_id: str | None
    default_provider: str
    default_model: str
    provider: dict
    rate_limit_rpm: int
    rate_limit_tpm: int
    circuit_breaker: dict


class ModelRateLimitError(ModelGatewayError):
    pass


class ModelCircuitOpenError(ModelGatewayError):
    pass


class ModelRateLimiter:
    _calls: dict[str, list[float]] = {}
    _tokens: dict[str, list[tuple[float, int]]] = {}

    @classmethod
    def check(
        cls,
        *,
        key: str,
        rpm: int,
        tpm: int,
        estimated_tokens: int,
        now: float | None = None,
    ) -> None:
        if rpm <= 0 and tpm <= 0:
            return
        current_time = now or time.time()
        window_start = current_time - 60
        timestamps = [
            timestamp for timestamp in cls._calls.get(key, []) if timestamp >= window_start
        ]
        token_entries = [entry for entry in cls._tokens.get(key, []) if entry[0] >= window_start]
        if rpm > 0 and len(timestamps) >= rpm:
            cls._calls[key] = timestamps
            cls._tokens[key] = token_entries
            raise ModelRateLimitError("model rate limit exceeded")
        token_total = sum(tokens for _, tokens in token_entries)
        if tpm > 0 and token_total + estimated_tokens > tpm:
            cls._calls[key] = timestamps
            cls._tokens[key] = token_entries
            raise ModelRateLimitError("model tpm limit exceeded")
        timestamps.append(current_time)
        token_entries.append((current_time, estimated_tokens))
        cls._calls[key] = timestamps
        cls._tokens[key] = token_entries

    @classmethod
    def clear(cls) -> None:
        cls._calls.clear()
        cls._tokens.clear()


class ModelCircuitBreaker:
    _states: dict[str, dict] = {}

    @classmethod
    def check(cls, *, key: str, now: float | None = None) -> None:
        state = cls._states.get(key, {})
        opened_until = float(state.get("opened_until") or 0)
        if opened_until <= 0:
            return
        current_time = now or time.time()
        if opened_until > current_time:
            raise ModelCircuitOpenError("model provider circuit open")
        state["opened_until"] = 0
        cls._states[key] = state

    @classmethod
    def record_success(cls, *, key: str) -> None:
        cls._states[key] = {
            "consecutive_failures": 0,
            "opened_until": 0,
        }

    @classmethod
    def record_failure(
        cls,
        *,
        key: str,
        failure_threshold: int,
        cooldown_seconds: int,
        now: float | None = None,
    ) -> None:
        if failure_threshold <= 0 or cooldown_seconds <= 0:
            return
        current_time = now or time.time()
        state = cls._states.get(key, {})
        consecutive_failures = int(state.get("consecutive_failures") or 0) + 1
        opened_until = float(state.get("opened_until") or 0)
        if consecutive_failures >= failure_threshold:
            opened_until = current_time + cooldown_seconds
        cls._states[key] = {
            "consecutive_failures": consecutive_failures,
            "opened_until": opened_until,
        }

    @classmethod
    def state(cls, *, key: str, now: float | None = None) -> dict:
        state = cls._states.get(key, {})
        current_time = now or time.time()
        opened_until = float(state.get("opened_until") or 0)
        is_open = opened_until > current_time
        return {
            "status": "open" if is_open else "closed",
            "consecutive_failures": int(state.get("consecutive_failures") or 0),
            "opened_until": datetime.fromtimestamp(opened_until).isoformat() if is_open else None,
        }

    @classmethod
    def clear(cls) -> None:
        cls._states.clear()


class ModelGateway(Protocol):
    def complete(self, request: ModelRequest) -> ModelResponse:
        """Call an OpenAI-compatible gateway through the platform boundary."""

    def stream(self, request: ModelRequest) -> Iterator[ModelStreamChunk]:
        """Stream a completion chunk-by-chunk. Terminates with done=True."""


def _fallback_stream(response: ModelResponse) -> Iterator[ModelStreamChunk]:
    """
    Adapt a non-streaming `ModelResponse` into a degenerate 2-chunk stream.
    Used by gateways / providers that cannot do real incremental SSE so the
    downstream consumer contract (one or more text chunks + terminal usage +
    `done=True`) is honoured without special-casing in callers.
    """
    yield ModelStreamChunk(text=response.content)
    yield ModelStreamChunk(
        usage=dict(response.usage),
        raw_response=dict(response.raw_response),
        done=True,
    )


class MockModelGateway:
    def complete(self, request: ModelRequest) -> ModelResponse:
        model_calls_total.inc()
        content = _mock_model_content(request)
        model_tokens_input_total.inc(sum(len(message.content) for message in request.messages) // 4)
        model_tokens_output_total.inc(max(1, len(content) // 4))
        return ModelResponse(
            content=content,
            model_provider=request.model_provider,
            model_name=request.model_name,
            usage={
                "prompt_tokens": sum(len(message.content) for message in request.messages) // 4,
                "completion_tokens": max(1, len(content) // 4),
            },
            raw_response={"mode": "mock"},
        )

    def stream(self, request: ModelRequest) -> Iterator[ModelStreamChunk]:
        yield from _fallback_stream(self.complete(request))


def _mock_model_content(request: ModelRequest) -> str:
    if request.response_format == "text":
        goal = next(
            (
                message.content.strip()
                for message in reversed(request.messages)
                if message.role == "user" and message.content.strip()
            ),
            "Workspace chat",
        )
        return (
            "这是本地 mock 模型回复，用于 Docker 私有交付环境的无 API Key 验证。"
            f"我已收到你的请求：{goal}"
        )
    return "{}"


class OpenAICompatibleModelGateway:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        settings = get_settings()
        self.base_url = str(base_url or settings.model_gateway_base_url)
        self.api_key = api_key if api_key is not None else settings.model_gateway_api_key
        self.timeout_seconds = timeout_seconds

    def complete(self, request_payload: ModelRequest) -> ModelResponse:
        started_at = time.monotonic()
        if self._uses_local_mock():
            response = MockModelGateway().complete(request_payload)
            model_call_duration_seconds.observe(time.monotonic() - started_at)
            return response

        payload = self._payload(request_payload)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        http_request = request.Request(
            urljoin(self.base_url.rstrip("/") + "/", "chat/completions"),
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            model_call_errors_total.inc()
            raise ModelGatewayError(self._format_http_error(exc)) from exc
        except (OSError, json.JSONDecodeError) as exc:
            model_call_errors_total.inc()
            raise ModelGatewayError(str(exc)) from exc

        usage = raw.get("usage", {})
        content = self._extract_content(raw)
        model_calls_total.inc()
        model_tokens_input_total.inc(int(usage.get("prompt_tokens", 0) or 0))
        model_tokens_output_total.inc(int(usage.get("completion_tokens", 0) or 0))
        model_call_duration_seconds.observe(time.monotonic() - started_at)
        return ModelResponse(
            content=content,
            model_provider=request_payload.model_provider,
            model_name=request_payload.model_name,
            usage=usage,
            raw_response=raw,
        )

    def _uses_local_mock(self) -> bool:
        return self.api_key in {"", "replace-me"} or self.base_url.endswith("/mock-model")

    def _extract_content(self, raw: dict) -> str:
        choices = raw.get("choices", [])
        if not choices:
            raise ModelGatewayError("model response has no choices")
        message = choices[0].get("message", {})
        content = message.get("content")
        if not isinstance(content, str):
            raise ModelGatewayError("model response content is missing")
        return content

    def stream(self, request_payload: ModelRequest) -> Iterator[ModelStreamChunk]:
        """
        OpenAI-compatible SSE stream (`/chat/completions` with `stream: true`).
        Each upstream frame `data: {...}` carries `choices[0].delta.content`
        for the token delta plus a terminal `[DONE]` sentinel. The final
        `chunk` typically includes `usage` on providers that report it
        post-stream (OpenAI 2024+, most compatible backends).
        """
        started_at = time.monotonic()
        if self._uses_local_mock():
            yield from _fallback_stream(self.complete(request_payload))
            model_call_duration_seconds.observe(time.monotonic() - started_at)
            return

        payload = self._payload(request_payload, stream=True)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "text/event-stream",
        }
        http_request = request.Request(
            urljoin(self.base_url.rstrip("/") + "/", "chat/completions"),
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        text_total = ""
        usage: dict = {}
        raw_last: dict = {}
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                    if not line:
                        continue
                    if line.startswith(":"):
                        # SSE comment / heartbeat
                        continue
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "" or data == "[DONE]":
                        continue
                    try:
                        frame = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    raw_last = frame
                    choices = frame.get("choices") or []
                    if choices:
                        delta = choices[0].get("delta") or {}
                        piece = delta.get("content")
                        if isinstance(piece, str) and piece:
                            text_total += piece
                            yield ModelStreamChunk(text=piece)
                    frame_usage = frame.get("usage")
                    if isinstance(frame_usage, dict):
                        usage = frame_usage
        except error.HTTPError as exc:
            model_call_errors_total.inc()
            raise ModelGatewayError(self._format_http_error(exc)) from exc
        except (OSError, json.JSONDecodeError) as exc:
            model_call_errors_total.inc()
            raise ModelGatewayError(str(exc)) from exc

        if not text_total:
            raise ModelGatewayError("model response content is missing")

        normalized_usage = {
            **usage,
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(
                usage.get("completion_tokens") or max(1, len(text_total) // 4)
            ),
        }
        model_calls_total.inc()
        model_tokens_input_total.inc(int(normalized_usage.get("prompt_tokens", 0) or 0))
        model_tokens_output_total.inc(int(normalized_usage.get("completion_tokens", 0) or 0))
        model_call_duration_seconds.observe(time.monotonic() - started_at)
        yield ModelStreamChunk(
            usage=normalized_usage,
            raw_response=raw_last or {"stream": "openai_compatible"},
            done=True,
        )

    def _payload(self, request_payload: ModelRequest, *, stream: bool = False) -> dict:
        payload: dict = {
            "model": request_payload.model_name,
            "messages": [message.model_dump() for message in request_payload.messages],
        }
        response_format = self._response_format_payload(request_payload.response_format)
        if response_format is not None:
            payload["response_format"] = response_format
        if stream:
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}
        return payload

    def _response_format_payload(self, response_format: str) -> dict | None:
        normalized = response_format.strip().lower()
        if normalized in {"", "text"}:
            return None
        if normalized in {"json", "json_object"}:
            return {"type": "json_object"}
        return {"type": normalized}

    def _format_http_error(self, exc: error.HTTPError) -> str:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except OSError:
            body = ""
        detail = body.strip()
        if len(detail) > 500:
            detail = f"{detail[:500]}..."
        if detail:
            return f"upstream model gateway returned HTTP {exc.code}: {detail}"
        return f"upstream model gateway returned HTTP {exc.code}: {exc.reason}"


class AnthropicCompatibleModelGateway:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: int = 30,
        max_tokens: int = 4096,
    ) -> None:
        settings = get_settings()
        self.base_url = str(base_url or settings.model_gateway_base_url)
        self.api_key = api_key if api_key is not None else settings.model_gateway_api_key
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens

    def complete(self, request_payload: ModelRequest) -> ModelResponse:
        started_at = time.monotonic()
        if self._uses_local_mock():
            response = MockModelGateway().complete(request_payload)
            model_call_duration_seconds.observe(time.monotonic() - started_at)
            return response

        payload = self._payload(request_payload)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        http_request = request.Request(
            urljoin(self.base_url.rstrip("/") + "/", "v1/messages"),
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except (OSError, error.HTTPError, json.JSONDecodeError) as exc:
            model_call_errors_total.inc()
            raise ModelGatewayError(str(exc)) from exc

        usage = self._normalize_usage(raw.get("usage", {}))
        content = self._extract_content(raw)
        model_calls_total.inc()
        model_tokens_input_total.inc(int(usage.get("prompt_tokens", 0) or 0))
        model_tokens_output_total.inc(int(usage.get("completion_tokens", 0) or 0))
        model_call_duration_seconds.observe(time.monotonic() - started_at)
        return ModelResponse(
            content=content,
            model_provider=request_payload.model_provider,
            model_name=request_payload.model_name,
            usage=usage,
            raw_response=raw,
        )

    def _payload(self, request_payload: ModelRequest) -> dict:
        messages = []
        system_parts = []
        for message in request_payload.messages:
            if message.role == "system":
                system_parts.append(message.content)
                continue
            role = message.role if message.role in {"user", "assistant"} else "user"
            messages.append({"role": role, "content": message.content})
        if not messages:
            messages.append({"role": "user", "content": ""})
        payload: dict = {
            "model": request_payload.model_name,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        if request_payload.response_format == "json":
            payload["system"] = (
                str(payload.get("system") or "")
                + "\n\nReturn only valid JSON without Markdown fences."
            ).strip()
        return payload

    def _uses_local_mock(self) -> bool:
        return self.api_key in {"", "replace-me"} or self.base_url.endswith("/mock-model")

    def _normalize_usage(self, usage: dict) -> dict:
        prompt_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        return {
            **usage,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        }

    def _extract_content(self, raw: dict) -> str:
        content = raw.get("content")
        if isinstance(content, str):
            return content
        if not isinstance(content, list) or not content:
            raise ModelGatewayError("model response content is missing")
        text_parts = [
            block.get("text")
            for block in content
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        ]
        if not text_parts:
            raise ModelGatewayError("model response text content is missing")
        return "\n".join(text_parts)

    def stream(self, request_payload: ModelRequest) -> Iterator[ModelStreamChunk]:
        """
        Anthropic-compatible SSE stream (`/v1/messages` with `stream: true`).
        Upstream event taxonomy we actually consume:
          - `message_start`       — usage baseline (prompt tokens)
          - `content_block_delta` — `delta.text` is the token increment
          - `message_delta`       — usage completion (output tokens)
          - `message_stop`        — terminal sentinel
        Everything else (`ping`, `content_block_start`, `content_block_stop`)
        is ignored. Parsing is defensive: malformed frames fall through and
        we rely on the total-text emptiness check for error surfacing.
        """
        started_at = time.monotonic()
        if self._uses_local_mock():
            yield from _fallback_stream(self.complete(request_payload))
            model_call_duration_seconds.observe(time.monotonic() - started_at)
            return

        payload = self._payload(request_payload)
        payload["stream"] = True
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "text/event-stream",
            "anthropic-version": "2023-06-01",
        }
        http_request = request.Request(
            urljoin(self.base_url.rstrip("/") + "/", "v1/messages"),
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        text_total = ""
        usage: dict = {}
        last_frame: dict = {}
        current_event: str | None = None
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                    if line == "":
                        current_event = None
                        continue
                    if line.startswith(":"):
                        continue
                    if line.startswith("event:"):
                        current_event = line[6:].strip()
                        continue
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data:
                        continue
                    try:
                        frame = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    last_frame = frame
                    ftype = (
                        frame.get("type") if isinstance(frame.get("type"), str) else current_event
                    )
                    if ftype == "content_block_delta":
                        delta = frame.get("delta") or {}
                        if delta.get("type") == "text_delta":
                            piece = delta.get("text")
                            if isinstance(piece, str) and piece:
                                text_total += piece
                                yield ModelStreamChunk(text=piece)
                    elif ftype == "message_start":
                        msg = frame.get("message") or {}
                        msg_usage = msg.get("usage")
                        if isinstance(msg_usage, dict):
                            usage.update(msg_usage)
                    elif ftype == "message_delta":
                        msg_usage = frame.get("usage")
                        if isinstance(msg_usage, dict):
                            usage.update(msg_usage)
                    elif ftype == "error":
                        err = frame.get("error") or {}
                        message = err.get("message") or str(frame)
                        raise ModelGatewayError(message)
                    # message_stop, content_block_start/stop, ping → ignore
        except (OSError, error.HTTPError, json.JSONDecodeError) as exc:
            model_call_errors_total.inc()
            raise ModelGatewayError(str(exc)) from exc

        if not text_total:
            raise ModelGatewayError("model response text content is missing")

        normalized = self._normalize_usage(usage)
        if not normalized.get("completion_tokens"):
            normalized["completion_tokens"] = max(1, len(text_total) // 4)
        model_calls_total.inc()
        model_tokens_input_total.inc(int(normalized.get("prompt_tokens", 0) or 0))
        model_tokens_output_total.inc(int(normalized.get("completion_tokens", 0) or 0))
        model_call_duration_seconds.observe(time.monotonic() - started_at)
        yield ModelStreamChunk(
            usage=normalized,
            raw_response=last_frame or {"stream": "anthropic"},
            done=True,
        )


class ModelSettingsResolver:
    def __init__(self, session: Session) -> None:
        self.session = session

    def resolve(
        self,
        *,
        task_id: str,
        request_payload: ModelRequest,
    ) -> tuple[ModelRequest, ResolvedModelSettings]:
        task = self.session.get(Task, task_id)
        organization_id = task.organization_id if task is not None else None
        owner_user_id = task.created_by if task is not None else None
        settings = self._settings_for_org(organization_id)
        default_provider = str(settings.get("default_provider") or "openai-compatible")
        default_model = str(settings.get("default_model") or "default")
        provider_name = request_payload.model_provider or default_provider
        if provider_name == "default":
            provider_name = default_provider
        model_name = request_payload.model_name
        if not model_name or model_name == "default":
            model_name = default_model
        provider = self._provider(settings=settings, provider_name=provider_name)
        rpm = int(
            provider.get("rate_limit_rpm") or settings.get("rate_limits", {}).get("rpm") or 600
        )
        tpm = int(
            provider.get("rate_limit_tpm") or settings.get("rate_limits", {}).get("tpm") or 120000
        )
        circuit_breaker = {
            **dict(settings.get("circuit_breaker") or {}),
            **dict(provider.get("circuit_breaker") or {}),
        }
        circuit_breaker.setdefault("failure_threshold", 3)
        circuit_breaker.setdefault("cooldown_seconds", 60)
        resolved_request = request_payload.model_copy(
            update={"model_provider": provider_name, "model_name": model_name}
        )
        return (
            resolved_request,
            ResolvedModelSettings(
                organization_id=organization_id,
                owner_user_id=owner_user_id,
                default_provider=default_provider,
                default_model=default_model,
                provider=provider,
                rate_limit_rpm=rpm,
                rate_limit_tpm=tpm,
                circuit_breaker=circuit_breaker,
            ),
        )

    def _settings_for_org(self, organization_id: str | None) -> dict:
        if organization_id is None:
            return normalize_model_settings(DEFAULT_MODEL_SETTINGS)
        setting = self.session.execute(
            select(SystemSetting).where(
                SystemSetting.organization_id == organization_id,
                SystemSetting.key == MODEL_SETTINGS_KEY,
            )
        ).scalar_one_or_none()
        if setting is None:
            return normalize_model_settings(DEFAULT_MODEL_SETTINGS)
        return normalize_model_settings(setting.value_json)

    def _provider(self, *, settings: dict, provider_name: str) -> dict:
        for provider in settings.get("providers", []):
            if provider.get("name") == provider_name:
                return provider
        return {"name": provider_name, "status": "healthy"}


class ModelHealthChecker:
    def __init__(self, session: Session) -> None:
        self.session = session

    def check(self, *, organization_id: str) -> list[dict]:
        settings = self._settings_for_org(organization_id)
        default_model = str(settings.get("default_model") or "default")
        results = []
        for provider in settings.get("providers", []):
            started_at = time.monotonic()
            status = str(provider.get("status") or "healthy")
            mode = "configured"
            error_message = None
            provider_name = str(provider.get("name") or "unknown")
            model_name = str(provider.get("model") or default_model)
            circuit_key = f"{organization_id}:{provider_name}:{model_name}"
            if provider.get("api_key") in {None, "", "replace-me"} and not provider.get("base_url"):
                mode = "mock"
                status = "healthy"
            else:
                mode = "probe"
                try:
                    model_gateway_for_provider(
                        provider,
                        timeout_seconds=int(provider.get("health_timeout_seconds") or 5),
                        session=self.session,
                        organization_id=organization_id,
                    ).complete(
                        ModelRequest(
                            model_provider=provider_name,
                            model_name=model_name,
                            response_format="text",
                            messages=[
                                ModelMessage(
                                    role="user",
                                    content="health check",
                                )
                            ],
                        )
                    )
                    status = "healthy"
                except Exception as exc:
                    status = "unhealthy"
                    error_message = str(exc)
            if status not in {"healthy", "degraded", "unhealthy"}:
                error_message = f"provider status is {status}"
                status = "unhealthy"
            latency_ms = int((time.monotonic() - started_at) * 1000)
            circuit_state = ModelCircuitBreaker.state(key=circuit_key)
            results.append(
                {
                    "provider": provider_name,
                    "model": model_name,
                    "status": status,
                    "mode": mode,
                    "checked_at": utc_now(),
                    "latency_ms": latency_ms,
                    "error_message": error_message,
                    "circuit_status": circuit_state["status"],
                    "circuit_open_until": circuit_state["opened_until"],
                    "consecutive_failures": circuit_state["consecutive_failures"],
                }
            )
            provider["status"] = status
            provider["last_health"] = {
                "status": status,
                "mode": mode,
                "checked_at": results[-1]["checked_at"].isoformat(),
                "latency_ms": latency_ms,
                "error_message": error_message,
            }
        if results:
            worst_status = "healthy"
            if any(result["status"] == "unhealthy" for result in results):
                worst_status = "unhealthy"
            elif any(result["status"] == "degraded" for result in results):
                worst_status = "degraded"
            settings["health"] = {
                "status": worst_status,
                "updated_at": utc_now().isoformat(),
                "mode": "probe" if any(result["mode"] == "probe" for result in results) else "mock",
                "latency_ms": max(result["latency_ms"] for result in results),
                "error_message": next(
                    (
                        result["error_message"]
                        for result in results
                        if result["error_message"] is not None
                    ),
                    None,
                ),
            }
            self._write_settings_for_org(organization_id=organization_id, settings=settings)
        return results

    def _settings_for_org(self, organization_id: str) -> dict:
        setting = self.session.execute(
            select(SystemSetting).where(
                SystemSetting.organization_id == organization_id,
                SystemSetting.key == MODEL_SETTINGS_KEY,
            )
        ).scalar_one_or_none()
        if setting is None:
            return normalize_model_settings(DEFAULT_MODEL_SETTINGS)
        return normalize_model_settings(setting.value_json)

    def _write_settings_for_org(self, *, organization_id: str, settings: dict) -> None:
        settings = _store_provider_api_keys_for_gateway(
            self.session,
            organization_id=organization_id,
            settings=settings,
        )
        setting = self.session.execute(
            select(SystemSetting).where(
                SystemSetting.organization_id == organization_id,
                SystemSetting.key == MODEL_SETTINGS_KEY,
            )
        ).scalar_one_or_none()
        if setting is None:
            setting = SystemSetting(
                organization_id=organization_id,
                key=MODEL_SETTINGS_KEY,
                value_json=deepcopy(settings),
                updated_by="system",
                updated_at=utc_now(),
            )
            self.session.add(setting)
        else:
            setting.value_json = deepcopy(settings)
            setting.updated_at = utc_now()
        self.session.flush()


class AuditedModelGateway:
    def __init__(
        self,
        *,
        session: Session,
        task_id: str,
        agent_run_id: str | None = None,
        gateway: ModelGateway | None = None,
        grounding_correlation_id: str | None = None,
        prompt_manifest_id: str | None = None,
        prompt_manifest_version: str | None = None,
        retrieval_evidence_ids: list[str] | None = None,
        evidence_text_sha256: str | None = None,
        context_manifest_id: str | None = None,
    ) -> None:
        self.session = session
        self.task_id = task_id
        self.agent_run_id = agent_run_id
        self.gateway = gateway
        self.event_store = EventStore(session)
        self.grounding_correlation_id = grounding_correlation_id
        self.prompt_manifest_id = prompt_manifest_id
        self.prompt_manifest_version = prompt_manifest_version
        self.retrieval_evidence_ids = retrieval_evidence_ids or []
        self.evidence_text_sha256 = evidence_text_sha256
        self.context_manifest_id = context_manifest_id

    def _capability_snapshot_json(self) -> dict:
        task = self.session.get(Task, self.task_id)
        if task is None or not isinstance(task.capability_snapshot_json, dict):
            return {}
        return task.capability_snapshot_json

    def _context_optimizer_request_metadata(self) -> dict:
        if self.context_manifest_id is None:
            return {}
        manifest = self.session.get(ContextAssemblyManifest, self.context_manifest_id)
        if manifest is None or not isinstance(manifest.token_budget_json, dict):
            return {}
        token_budget = manifest.token_budget_json
        metadata: dict = {
            "optimizer_capability_version_ids": token_budget.get(
                "optimizer_capability_version_ids", []
            ),
            "optimizer_policy_hash": token_budget.get("optimizer_policy_hash"),
        }
        effective_strategy = token_budget.get("effective_strategy", {})
        if isinstance(effective_strategy, dict) and effective_strategy.get("low_cost_route_hint"):
            metadata["low_cost_route"] = True
            metadata["low_cost_routing_reason"] = str(
                effective_strategy["low_cost_route_hint"]
            )
        return {key: value for key, value in metadata.items() if value not in (None, [], {})}

    def _generation_parameters(self, provider: dict) -> dict:
        parameters: dict = {}
        if provider.get("max_output_tokens") is not None:
            parameters["max_tokens"] = int(provider.get("max_output_tokens") or 0)
        if provider.get("temperature") is not None:
            parameters["temperature"] = provider.get("temperature")
        if provider.get("top_p") is not None:
            parameters["top_p"] = provider.get("top_p")
        return parameters

    def _request_message_hashes(self, request_payload: ModelRequest) -> list[dict]:
        return [
            {
                "index": index,
                "role": message.role,
                "content_sha256": hashlib.sha256(message.content.encode("utf-8")).hexdigest(),
            }
            for index, message in enumerate(request_payload.messages)
        ]

    def _request_message_hashes_sha256(self, request_message_hashes: list[dict]) -> str:
        encoded = json.dumps(
            request_message_hashes,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def complete(
        self,
        request_payload: ModelRequest,
        *,
        fallback_requests: list[ModelRequest] | None = None,
    ) -> ModelResponse:
        fallbacks = fallback_requests or []
        primary_error: str | None = None
        try:
            return self._attempt(request_payload, attempt_index=1)
        except ModelGatewayError as exc:
            primary_error = str(exc)
            if not fallbacks:
                raise

        last_error: ModelGatewayError | None = None
        for fallback_index, fallback in enumerate(fallbacks, start=1):
            model_fallback_total.labels(
                primary_provider=request_payload.model_provider,
                fallback_provider=fallback.model_provider,
            ).inc()
            self.event_store.append(
                task_id=self.task_id,
                agent_run_id=self.agent_run_id,
                event_type=EventType.MODEL_FALLBACK_USED,
                payload_json={
                    "primary_model_provider": request_payload.model_provider,
                    "primary_model_name": request_payload.model_name,
                    "model_provider": fallback.model_provider,
                    "model_name": fallback.model_name,
                    "fallback_index": fallback_index,
                    "fallback_count": len(fallbacks),
                    "reason": primary_error,
                },
            )
            try:
                return self._attempt(fallback, attempt_index=fallback_index + 1)
            except ModelGatewayError as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise ModelGatewayError("model gateway failed")

    def _attempt(self, request_payload: ModelRequest, *, attempt_index: int) -> ModelResponse:
        request_payload, settings = ModelSettingsResolver(self.session).resolve(
            task_id=self.task_id,
            request_payload=request_payload,
        )
        self._validate_grounding_binding(request_payload)
        self._validate_context_manifest_binding()
        limiter_key = (
            f"{settings.organization_id or 'global'}:"
            f"{request_payload.model_provider}:{request_payload.model_name}"
        )
        circuit_key = limiter_key
        estimated_prompt_tokens = self._estimate_prompt_tokens(request_payload)
        gateway = self.gateway or self._gateway_from_settings(settings)
        started_at = time.monotonic()
        generation_parameters = self._generation_parameters(settings.provider)
        request_message_hashes = self._request_message_hashes(request_payload)
        request_message_hashes_sha256 = self._request_message_hashes_sha256(request_message_hashes)
        model_request_sha256 = self._model_request_sha256(
            request_payload,
            generation_parameters=generation_parameters,
            request_message_hashes=request_message_hashes,
            request_message_hashes_sha256=request_message_hashes_sha256,
        )
        model_call = ModelCall(
            task_id=self.task_id,
            agent_run_id=self.agent_run_id,
            model_provider=request_payload.model_provider,
            model_name=request_payload.model_name,
            status="RUNNING",
            prompt_tokens=0,
            completion_tokens=0,
            duration_ms=0,
            grounding_correlation_id=self.grounding_correlation_id,
            prompt_manifest_id=self.prompt_manifest_id,
            context_manifest_id=self.context_manifest_id,
            capability_snapshot_json=self._capability_snapshot_json(),
            model_request_sha256=model_request_sha256,
            model_request_hash_schema_version=2,
            request_message_hashes_json=request_message_hashes,
            request_message_hashes_sha256=request_message_hashes_sha256,
            hash_recomputability_status="recomputable_v2",
            attempt_index=attempt_index,
            request_json=self._safe_request_json(
                request_payload,
                generation_parameters=generation_parameters,
                request_message_hashes=request_message_hashes,
                request_message_hashes_sha256=request_message_hashes_sha256,
                model_request_sha256=model_request_sha256,
            ),
            response_json={},
            created_at=utc_now(),
        )
        self.session.add(model_call)
        self.session.flush()
        self.event_store.append(
            task_id=self.task_id,
            agent_run_id=self.agent_run_id,
            event_type=EventType.MODEL_CALLED,
            payload_json={
                "model_call_id": model_call.id,
                "model_provider": request_payload.model_provider,
                "model_name": request_payload.model_name,
                "prompt_message_count": len(request_payload.messages),
                "grounding_correlation_id": self.grounding_correlation_id,
                "prompt_manifest_id": self.prompt_manifest_id,
                "context_manifest_id": self.context_manifest_id,
                "model_request_sha256": model_request_sha256,
                "attempt_index": attempt_index,
            },
        )
        self.session.commit()
        try:
            with traced_operation(
                self.session,
                "model_call",
                task_id=self.task_id,
                agent_run_id=self.agent_run_id,
                kind="client",
                attributes={
                    "model_call_id": model_call.id,
                    "model_provider": request_payload.model_provider,
                    "model_name": request_payload.model_name,
                    "attempt_index": attempt_index,
                },
            ):
                ModelCircuitBreaker.check(key=circuit_key)
                ModelRateLimiter.check(
                    key=limiter_key,
                    rpm=settings.rate_limit_rpm,
                    tpm=settings.rate_limit_tpm,
                    estimated_tokens=estimated_prompt_tokens,
                )
                response_payload = gateway.complete(request_payload)
        except Exception as exc:
            if not isinstance(exc, (ModelRateLimitError, ModelCircuitOpenError)):
                ModelCircuitBreaker.record_failure(
                    key=circuit_key,
                    failure_threshold=int(settings.circuit_breaker.get("failure_threshold") or 3),
                    cooldown_seconds=int(settings.circuit_breaker.get("cooldown_seconds") or 60),
                )
            model_call.status = "FAILED"
            model_call.terminal_status = "failed"
            model_call.duration_ms = int((time.monotonic() - started_at) * 1000)
            model_call.error_message = str(exc)
            self.event_store.append(
                task_id=self.task_id,
                agent_run_id=self.agent_run_id,
                event_type=EventType.MODEL_CALL_FAILED,
                payload_json={
                    "model_call_id": model_call.id,
                    "model_provider": request_payload.model_provider,
                    "model_name": request_payload.model_name,
                    "error": str(exc),
                    "grounding_correlation_id": self.grounding_correlation_id,
                    "prompt_manifest_id": self.prompt_manifest_id,
                    "context_manifest_id": self.context_manifest_id,
                    "attempt_index": attempt_index,
                    "terminal_status": model_call.terminal_status,
                },
            )
            self.session.flush()
            if isinstance(exc, ModelGatewayError):
                raise
            raise ModelGatewayError(str(exc)) from exc

        usage = response_payload.usage
        ModelCircuitBreaker.record_success(key=circuit_key)
        model_call.status = "SUCCESS"
        model_call.terminal_status = "success"
        model_call.prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        model_call.completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        model_call.duration_ms = int((time.monotonic() - started_at) * 1000)
        model_call.response_json = {
            "content_preview": response_payload.content[:2000],
            "usage": usage,
            "raw_response": response_payload.raw_response,
        }
        self.event_store.append(
            task_id=self.task_id,
            agent_run_id=self.agent_run_id,
            event_type=EventType.MODEL_RESPONSE_RECEIVED,
            payload_json={
                "model_call_id": model_call.id,
                "model_provider": response_payload.model_provider,
                "model_name": response_payload.model_name,
                "prompt_tokens": model_call.prompt_tokens,
                "completion_tokens": model_call.completion_tokens,
                "duration_ms": model_call.duration_ms,
                "grounding_correlation_id": self.grounding_correlation_id,
                "prompt_manifest_id": self.prompt_manifest_id,
                "context_manifest_id": self.context_manifest_id,
                "model_request_sha256": model_request_sha256,
                "attempt_index": attempt_index,
                "terminal_status": model_call.terminal_status,
            },
        )
        self.session.flush()
        return response_payload

    def _safe_request_json(
        self,
        request_payload: ModelRequest,
        *,
        generation_parameters: dict,
        request_message_hashes: list[dict],
        request_message_hashes_sha256: str,
        model_request_sha256: str,
    ) -> dict:
        estimated_prompt_tokens = self._estimate_prompt_tokens(request_payload)
        return {
            "model_provider": request_payload.model_provider,
            "model_name": request_payload.model_name,
            "response_format": request_payload.response_format,
            "generation_parameters": generation_parameters,
            "estimated_prompt_tokens": estimated_prompt_tokens,
            "grounding_correlation_id": self.grounding_correlation_id,
            "prompt_manifest_id": self.prompt_manifest_id,
            "context_manifest_id": self.context_manifest_id,
            **self._context_optimizer_request_metadata(),
            "prompt_manifest_version": self.prompt_manifest_version,
            "retrieval_evidence_ids": sorted(self.retrieval_evidence_ids),
            "evidence_text_sha256": self.evidence_text_sha256,
            "model_request_hash_schema_version": 2,
            "request_message_hashes": request_message_hashes,
            "request_message_hashes_sha256": request_message_hashes_sha256,
            "model_request_sha256": model_request_sha256,
            "messages": [
                {
                    "role": message.role,
                    "content_length": len(message.content),
                    "content_sha256": request_message_hashes[index]["content_sha256"],
                }
                for index, message in enumerate(request_payload.messages)
            ],
        }

    def _model_request_sha256(
        self,
        request_payload: ModelRequest,
        *,
        generation_parameters: dict | None = None,
        request_message_hashes: list[dict] | None = None,
        request_message_hashes_sha256: str | None = None,
    ) -> str:
        message_hashes = request_message_hashes or self._request_message_hashes(request_payload)
        message_hashes_sha256 = request_message_hashes_sha256 or (
            self._request_message_hashes_sha256(message_hashes)
        )
        canonical_payload = {
            "model_provider": request_payload.model_provider,
            "model_name": request_payload.model_name,
            "response_format": request_payload.response_format,
            "generation_parameters": generation_parameters or {},
            "request_message_hashes_json": message_hashes,
            "request_message_hashes_sha256": message_hashes_sha256,
            "retrieval_evidence_ids": sorted(self.retrieval_evidence_ids),
            "prompt_manifest_id": self.prompt_manifest_id,
            "context_manifest_id": self.context_manifest_id,
            "prompt_manifest_version": self.prompt_manifest_version,
            "evidence_text_sha256": self.evidence_text_sha256,
        }
        if self.context_manifest_id is None:
            canonical_payload.pop("context_manifest_id", None)
        encoded = json.dumps(
            canonical_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _validate_grounding_binding(self, request_payload: ModelRequest) -> None:
        if self.prompt_manifest_id is None:
            return
        manifest = self.session.get(PromptAssemblyManifest, self.prompt_manifest_id)
        if manifest is None:
            raise ModelGatewayError("prompt manifest not found for grounded model call")
        if manifest.run_id != self.task_id:
            raise ModelGatewayError("prompt manifest does not belong to model call task")
        if self.grounding_correlation_id != manifest.grounding_correlation_id:
            raise ModelGatewayError("grounding correlation does not match prompt manifest")
        if sorted(self.retrieval_evidence_ids) != sorted(manifest.included_retrieval_hit_ids_json):
            raise ModelGatewayError("retrieval evidence ids do not match prompt manifest")
        if self.evidence_text_sha256 != manifest.evidence_text_sha256:
            raise ModelGatewayError("evidence hash does not match prompt manifest")
        manifest_metadata = (
            manifest.metadata_json if isinstance(manifest.metadata_json, dict) else {}
        )
        manifest_version = str(
            manifest_metadata.get("prompt_manifest_version")
            or manifest_metadata.get("schema_version")
            or ""
        )
        if self.prompt_manifest_version != manifest_version:
            raise ModelGatewayError("prompt manifest version does not match")
        evidence_message_hashes = {
            hashlib.sha256(message.content.encode("utf-8")).hexdigest()
            for message in request_payload.messages
        }
        if manifest.evidence_text_sha256 not in evidence_message_hashes:
            raise ModelGatewayError("model messages do not include prompt manifest evidence")

    def _validate_context_manifest_binding(self) -> None:
        if self.context_manifest_id is None:
            return
        manifest = self.session.get(ContextAssemblyManifest, self.context_manifest_id)
        if manifest is None:
            raise ModelGatewayError("context manifest not found for model call")
        if manifest.run_id != self.task_id:
            raise ModelGatewayError("context manifest does not belong to model call task")
        if manifest.prompt_manifest_id != self.prompt_manifest_id:
            raise ModelGatewayError("context manifest prompt manifest mirror does not match")

    # -----------------------------------------------------------------
    # Streaming variant (v4 bugfix — true token-by-token SSE).
    # -----------------------------------------------------------------
    def stream(
        self,
        request_payload: ModelRequest,
        *,
        fallback_requests: list[ModelRequest] | None = None,
    ) -> Iterator[ModelStreamChunk]:
        """
        Audited streaming counterpart to `complete`. Yields
        `ModelStreamChunk` from the resolved gateway, writing the same
        `ModelCall` row + `MODEL_CALLED` / `MODEL_RESPONSE_RECEIVED` /
        `MODEL_CALL_FAILED` events as the blocking path. The `ModelCall`
        status flips to `SUCCESS` only after the terminal `done=True`
        chunk is observed. Fallback providers run sequentially with the
        same event trace as `complete` uses.
        """
        fallbacks = fallback_requests or []
        primary_error: str | None = None
        try:
            yield from self._attempt_stream(request_payload, attempt_index=1)
            return
        except ModelGatewayError as exc:
            primary_error = str(exc)
            if not fallbacks:
                raise

        last_error: ModelGatewayError | None = None
        for fallback_index, fallback in enumerate(fallbacks, start=1):
            model_fallback_total.labels(
                primary_provider=request_payload.model_provider,
                fallback_provider=fallback.model_provider,
            ).inc()
            self.event_store.append(
                task_id=self.task_id,
                agent_run_id=self.agent_run_id,
                event_type=EventType.MODEL_FALLBACK_USED,
                payload_json={
                    "primary_model_provider": request_payload.model_provider,
                    "primary_model_name": request_payload.model_name,
                    "model_provider": fallback.model_provider,
                    "model_name": fallback.model_name,
                    "fallback_index": fallback_index,
                    "fallback_count": len(fallbacks),
                    "reason": primary_error,
                },
            )
            try:
                yield from self._attempt_stream(fallback, attempt_index=fallback_index + 1)
                return
            except ModelGatewayError as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise ModelGatewayError("model gateway failed")

    def _attempt_stream(
        self,
        request_payload: ModelRequest,
        *,
        attempt_index: int,
    ) -> Iterator[ModelStreamChunk]:
        request_payload, settings = ModelSettingsResolver(self.session).resolve(
            task_id=self.task_id,
            request_payload=request_payload,
        )
        self._validate_grounding_binding(request_payload)
        self._validate_context_manifest_binding()
        limiter_key = (
            f"{settings.organization_id or 'global'}:"
            f"{request_payload.model_provider}:{request_payload.model_name}"
        )
        circuit_key = limiter_key
        estimated_prompt_tokens = self._estimate_prompt_tokens(request_payload)
        gateway = self.gateway or self._gateway_from_settings(settings)
        started_at = time.monotonic()
        generation_parameters = self._generation_parameters(settings.provider)
        request_message_hashes = self._request_message_hashes(request_payload)
        request_message_hashes_sha256 = self._request_message_hashes_sha256(request_message_hashes)
        model_request_sha256 = self._model_request_sha256(
            request_payload,
            generation_parameters=generation_parameters,
            request_message_hashes=request_message_hashes,
            request_message_hashes_sha256=request_message_hashes_sha256,
        )
        model_call = ModelCall(
            task_id=self.task_id,
            agent_run_id=self.agent_run_id,
            model_provider=request_payload.model_provider,
            model_name=request_payload.model_name,
            status="RUNNING",
            prompt_tokens=0,
            completion_tokens=0,
            duration_ms=0,
            grounding_correlation_id=self.grounding_correlation_id,
            prompt_manifest_id=self.prompt_manifest_id,
            context_manifest_id=self.context_manifest_id,
            capability_snapshot_json=self._capability_snapshot_json(),
            model_request_sha256=model_request_sha256,
            model_request_hash_schema_version=2,
            request_message_hashes_json=request_message_hashes,
            request_message_hashes_sha256=request_message_hashes_sha256,
            hash_recomputability_status="recomputable_v2",
            attempt_index=attempt_index,
            request_json=self._safe_request_json(
                request_payload,
                generation_parameters=generation_parameters,
                request_message_hashes=request_message_hashes,
                request_message_hashes_sha256=request_message_hashes_sha256,
                model_request_sha256=model_request_sha256,
            ),
            response_json={},
            created_at=utc_now(),
        )
        self.session.add(model_call)
        self.session.flush()
        self.event_store.append(
            task_id=self.task_id,
            agent_run_id=self.agent_run_id,
            event_type=EventType.MODEL_CALLED,
            payload_json={
                "model_call_id": model_call.id,
                "model_provider": request_payload.model_provider,
                "model_name": request_payload.model_name,
                "prompt_message_count": len(request_payload.messages),
                "streaming": True,
                "grounding_correlation_id": self.grounding_correlation_id,
                "prompt_manifest_id": self.prompt_manifest_id,
                "context_manifest_id": self.context_manifest_id,
                "model_request_sha256": model_request_sha256,
                "attempt_index": attempt_index,
            },
        )
        self.session.commit()
        text_accumulator = ""
        usage: dict = {}
        raw_response: dict = {}
        terminal_chunk: ModelStreamChunk | None = None
        try:
            with traced_operation(
                self.session,
                "model_call_stream",
                task_id=self.task_id,
                agent_run_id=self.agent_run_id,
                kind="client",
                attributes={
                    "model_call_id": model_call.id,
                    "model_provider": request_payload.model_provider,
                    "model_name": request_payload.model_name,
                    "attempt_index": attempt_index,
                    "streaming": True,
                },
            ):
                ModelCircuitBreaker.check(key=circuit_key)
                ModelRateLimiter.check(
                    key=limiter_key,
                    rpm=settings.rate_limit_rpm,
                    tpm=settings.rate_limit_tpm,
                    estimated_tokens=estimated_prompt_tokens,
                )
                for chunk in gateway.stream(request_payload):
                    if chunk.text:
                        text_accumulator += chunk.text
                        yield chunk
                    if chunk.usage:
                        usage.update(chunk.usage)
                    if chunk.raw_response:
                        raw_response = chunk.raw_response
                    if chunk.done:
                        terminal_chunk = chunk
                        break
        except GeneratorExit:
            model_call.status = "FAILED"
            model_call.terminal_status = "stream_aborted"
            model_call.duration_ms = int((time.monotonic() - started_at) * 1000)
            model_call.error_message = "stream closed before completion"
            self.event_store.append(
                task_id=self.task_id,
                agent_run_id=self.agent_run_id,
                event_type=EventType.MODEL_CALL_FAILED,
                payload_json={
                    "model_call_id": model_call.id,
                    "model_provider": request_payload.model_provider,
                    "model_name": request_payload.model_name,
                    "error": model_call.error_message,
                    "streaming": True,
                    "cancelled": True,
                    "grounding_correlation_id": self.grounding_correlation_id,
                    "prompt_manifest_id": self.prompt_manifest_id,
                    "context_manifest_id": self.context_manifest_id,
                    "attempt_index": attempt_index,
                    "terminal_status": model_call.terminal_status,
                },
            )
            self.session.flush()
            raise
        except Exception as exc:
            if not isinstance(exc, (ModelRateLimitError, ModelCircuitOpenError)):
                ModelCircuitBreaker.record_failure(
                    key=circuit_key,
                    failure_threshold=int(settings.circuit_breaker.get("failure_threshold") or 3),
                    cooldown_seconds=int(settings.circuit_breaker.get("cooldown_seconds") or 60),
                )
            model_call.status = "FAILED"
            model_call.terminal_status = "failed"
            model_call.duration_ms = int((time.monotonic() - started_at) * 1000)
            model_call.error_message = str(exc)
            self.event_store.append(
                task_id=self.task_id,
                agent_run_id=self.agent_run_id,
                event_type=EventType.MODEL_CALL_FAILED,
                payload_json={
                    "model_call_id": model_call.id,
                    "model_provider": request_payload.model_provider,
                    "model_name": request_payload.model_name,
                    "error": str(exc),
                    "grounding_correlation_id": self.grounding_correlation_id,
                    "prompt_manifest_id": self.prompt_manifest_id,
                    "context_manifest_id": self.context_manifest_id,
                    "attempt_index": attempt_index,
                    "terminal_status": model_call.terminal_status,
                },
            )
            self.session.flush()
            if isinstance(exc, ModelGatewayError):
                raise
            raise ModelGatewayError(str(exc)) from exc

        ModelCircuitBreaker.record_success(key=circuit_key)
        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(
            usage.get("completion_tokens", 0) or max(1, len(text_accumulator) // 4)
        )
        model_call.status = "SUCCESS"
        model_call.terminal_status = "success"
        model_call.prompt_tokens = prompt_tokens
        model_call.completion_tokens = completion_tokens
        model_call.duration_ms = int((time.monotonic() - started_at) * 1000)
        model_call.response_json = {
            "content_preview": text_accumulator[:2000],
            "usage": {
                **usage,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
            "raw_response": raw_response,
            "stream": True,
        }
        self.event_store.append(
            task_id=self.task_id,
            agent_run_id=self.agent_run_id,
            event_type=EventType.MODEL_RESPONSE_RECEIVED,
            payload_json={
                "model_call_id": model_call.id,
                "model_provider": request_payload.model_provider,
                "model_name": request_payload.model_name,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "duration_ms": model_call.duration_ms,
                "streaming": True,
                "grounding_correlation_id": self.grounding_correlation_id,
                "prompt_manifest_id": self.prompt_manifest_id,
                "context_manifest_id": self.context_manifest_id,
                "model_request_sha256": model_request_sha256,
                "attempt_index": attempt_index,
                "terminal_status": model_call.terminal_status,
            },
        )
        self.session.flush()
        if terminal_chunk is not None:
            yield terminal_chunk

    def _estimate_prompt_tokens(self, request_payload: ModelRequest) -> int:
        content_length = sum(len(message.content) for message in request_payload.messages)
        message_overhead = len(request_payload.messages) * 4
        return max(1, (content_length // 4) + message_overhead)

    def _gateway_from_settings(self, settings: ResolvedModelSettings) -> ModelGateway:
        return model_gateway_for_provider(
            settings.provider,
            session=self.session,
            organization_id=settings.organization_id,
            user_id=settings.owner_user_id,
        )


def provider_api_key(
    provider: dict,
    *,
    session: Session | None = None,
    organization_id: str | None = None,
    user_id: str | None = None,
) -> str | None:
    provider_name = str(provider.get("name") or provider.get("model_provider") or "").strip()
    api_key_env = provider.get("api_key_env")
    if provider_name and session is not None and organization_id:
        resolved = resolve_secret(
            session,
            organization_id=organization_id,
            user_id=user_id,
            provider=provider_name,
            purpose=SECRET_PURPOSE_MODEL_PROVIDER,
            env_candidates=env_candidates_for_provider(
                provider_name,
                str(api_key_env) if isinstance(api_key_env, str) else None,
            ),
        )
        if resolved.found:
            return resolved.value
    api_key = provider.get("api_key")
    if isinstance(api_key, str) and api_key not in {"", "replace-me"}:
        return api_key
    if isinstance(api_key_env, str) and api_key_env:
        env_value = os.environ.get(api_key_env)
        if env_value:
            return env_value
        settings_value = _settings_api_key_for_env(api_key_env)
        if settings_value:
            return settings_value
        return api_key
    return api_key if isinstance(api_key, str) else None


def _store_provider_api_keys_for_gateway(
    session: Session,
    *,
    organization_id: str,
    settings: dict,
) -> dict:
    sanitized = deepcopy(settings)
    providers = sanitized.get("providers")
    if not isinstance(providers, list):
        return sanitized
    for provider in providers:
        if not isinstance(provider, dict):
            continue
        raw_key = str(provider.get("api_key") or "").strip()
        provider["api_key"] = ""
        if not raw_key or raw_key == "replace-me":
            continue
        provider_name = str(provider.get("name") or "").strip()
        if not provider_name:
            continue
        row = upsert_secret(
            session,
            organization_id=organization_id,
            actor_id="system",
            scope=SECRET_SCOPE_ORG,
            owner_user_id=None,
            provider=provider_name,
            purpose=SECRET_PURPOSE_MODEL_PROVIDER,
            secret_ref=f"secret://models/{provider_name}/api-key",
            secret_value=raw_key,
        )
        provider["api_key_configured"] = True
        provider["api_key_source"] = SECRET_SOURCE_ORG
        provider["api_key_secret_id"] = row.id
    return sanitized


def _settings_api_key_for_env(api_key_env: str) -> str | None:
    settings = get_settings()
    if api_key_env == DEEPSEEK_API_KEY_ENV:
        return settings.deepseek_api_key or None
    return None


def model_gateway_for_provider(
    provider: dict,
    *,
    timeout_seconds: int | None = None,
    session: Session | None = None,
    organization_id: str | None = None,
    user_id: str | None = None,
) -> ModelGateway:
    timeout = int(timeout_seconds or provider.get("timeout_seconds") or 30)
    api_key = provider_api_key(
        provider,
        session=session,
        organization_id=organization_id,
        user_id=user_id,
    )
    if str(provider.get("api_format") or "openai").lower() == "anthropic":
        return AnthropicCompatibleModelGateway(
            base_url=provider.get("base_url"),
            api_key=api_key,
            timeout_seconds=timeout,
            max_tokens=int(provider.get("max_output_tokens") or 4096),
        )
    return OpenAICompatibleModelGateway(
        base_url=provider.get("base_url"),
        api_key=api_key,
        timeout_seconds=timeout,
    )
