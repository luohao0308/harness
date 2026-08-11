from __future__ import annotations

import hashlib
import json
import math
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
from sqlalchemy import select, update
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
    SecretResolution,
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


class ModelAuthError(ModelGatewayError):
    pass


class ModelSetupRequiredError(ModelGatewayError):
    code = "MODEL_SETUP_REQUIRED"


class ModelCallCancelledError(ModelGatewayError):
    code = "MODEL_CALL_CANCELLED"


MODEL_SETTINGS_KEY = "settings.models"
PLATFORM_API_KEY_ENV = "AI_PROVIDER_API_KEY"
MODEL_GATEWAY_USER_AGENT = "Harness-AI-Gateway/1.0"
LEGACY_BUILTIN_PROVIDER_MODELS = {
    "minimax": {"MiniMax-M2.7-highspeed"},
    "deepseek": {"deepseek-chat", "deepseek-reasoner"},
    "deepseek-flash": {"deepseek-v4-flash"},
    "deepseek-pro": {"deepseek-v4-pro"},
    "openai-compatible": {"gpt-5.5"},
}
DEEPSEEK_SECRET_PROVIDER = "deepseek"
DEEPSEEK_SECRET_ALIASES = ("deepseek", "deepseek-flash", "deepseek-pro")
KNOWN_MODEL_LABELS = {
    "deepseek-v4-flash": "DeepSeek V4 Flash",
    "deepseek-v4-pro": "DeepSeek V4 Pro",
    "doubao-seed-2-1-pro": "Doubao Seed 2.1 Pro",
    "doubao-seed-2-1-turbo": "Doubao Seed 2.1 Turbo",
    "gemini-3.5-flash": "Gemini 3.5 Flash",
    "gemini-3.1-pro": "Gemini 3.1 Pro",
    "gpt-5.6-terra": "GPT-5.6 Terra",
    "glm-5.2-fast-preview": "GLM 5.2 Fast Preview",
    "glm-5.2": "GLM 5.2",
    "kimi-k2.6": "Kimi K2.6",
    "kimi-k2.7-code": "Kimi K2.7 Code",
    "minimax-m3": "MiniMax M3",
    "mimo-v2.5": "MiMo V2.5",
    "qwen3.7-plus": "Qwen 3.7 Plus",
    "qwen3.7-max": "Qwen 3.7 Max",
    "step-3.7-flash": "Step 3.7 Flash",
}


def _is_legacy_builtin_provider(provider: object) -> bool:
    if not isinstance(provider, dict):
        return False
    name = str(provider.get("name") or "")
    model = str(provider.get("model") or "")
    return model in LEGACY_BUILTIN_PROVIDER_MODELS.get(name, set())


def _is_legacy_builtin_selection(provider_name: object, model_name: object) -> bool:
    return str(model_name or "") in LEGACY_BUILTIN_PROVIDER_MODELS.get(
        str(provider_name or ""),
        set(),
    )


def _platform_provider(model: str) -> dict:
    settings = get_settings()
    return {
        "name": settings.ai_provider_name,
        "label": KNOWN_MODEL_LABELS.get(model, model),
        "status": "healthy",
        "api_format": "openai",
        "protocol": settings.ai_provider_protocol,
        "model": model,
        "allowed_models": list(settings.ai_provider_models),
        "secret_provider": settings.ai_provider_name,
        "base_url": settings.ai_provider_base_url,
        "api_key": "",
        "api_key_env": PLATFORM_API_KEY_ENV,
        "managed_by_platform": True,
        "platform_managed": True,
        "temperature": 0.2,
        "include_stream_usage": False,
        "timeout_seconds": 90,
        "health_timeout_seconds": 5,
        "rate_limit_rpm": 300,
        "rate_limit_tpm": 120000,
        "circuit_breaker": {"failure_threshold": 3, "cooldown_seconds": 60},
    }


def is_platform_model_provider(provider: object) -> bool:
    if not isinstance(provider, dict):
        return False
    settings = get_settings()
    return (
        provider.get("managed_by_platform") is True
        and provider.get("platform_managed") is True
        and str(provider.get("name") or "") == settings.ai_provider_name
        and str(provider.get("model") or "") in settings.ai_provider_models
        and str(provider.get("base_url") or "").rstrip("/")
        == settings.ai_provider_base_url.rstrip("/")
        and str(provider.get("api_key_env") or "") == PLATFORM_API_KEY_ENV
        and str(provider.get("protocol") or "") == settings.ai_provider_protocol
        and str(provider.get("api_format") or "").lower() == "openai"
    )


def validate_platform_model_selection(provider_name: str, model_name: str) -> None:
    settings = get_settings()
    if provider_name == settings.ai_provider_name and model_name not in settings.ai_provider_models:
        raise ModelGatewayError("requested model is not allowed by the platform provider")


def _platform_default_model_settings() -> dict:
    settings = get_settings()
    return {
        "default_provider": settings.ai_provider_name,
        "default_model": settings.ai_provider_model,
        "providers": [_platform_provider(model) for model in settings.ai_provider_models],
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


DEFAULT_MODEL_SETTINGS = _platform_default_model_settings()


def normalize_model_settings(settings: dict | None) -> dict:
    """Merge persisted settings with current built-in provider invariants."""
    defaults = _platform_default_model_settings()
    if settings is DEFAULT_MODEL_SETTINGS or not isinstance(settings, dict):
        normalized = deepcopy(defaults)
    else:
        normalized = deepcopy(settings)
    normalized.setdefault("default_provider", defaults["default_provider"])
    original_default_provider = normalized.get("default_provider")
    original_default_model = normalized.get("default_model")
    if not normalized.get("default_model") or normalized.get("default_model") == "default":
        normalized["default_model"] = defaults["default_model"]
    normalized.setdefault("providers", [])
    normalized.setdefault("rate_limits", defaults["rate_limits"])
    normalized.setdefault("health", defaults["health"])
    normalized.setdefault("circuit_breaker", defaults["circuit_breaker"])
    if _is_legacy_builtin_selection(original_default_provider, original_default_model):
        normalized["default_provider"] = defaults["default_provider"]
        normalized["default_model"] = defaults["default_model"]
    if (
        normalized.get("default_provider") == defaults["default_provider"]
        and normalized.get("default_model")
        not in get_settings().ai_provider_models
    ):
        normalized["default_model"] = defaults["default_model"]

    providers = normalized["providers"]
    if not isinstance(providers, list):
        providers = []
        normalized["providers"] = providers
    platform_name = get_settings().ai_provider_name
    preserved_providers = []
    for provider in providers:
        if _is_legacy_builtin_provider(provider):
            continue
        if isinstance(provider, dict) and provider.get("name") == platform_name:
            continue
        if isinstance(provider, dict):
            provider.pop("managed_by_platform", None)
            provider.pop("platform_managed", None)
            provider.pop("allowed_models", None)
            if provider.get("api_key_env") == PLATFORM_API_KEY_ENV:
                provider["api_key_env"] = ""
        preserved_providers.append(provider)
    providers[:] = preserved_providers
    providers.extend(deepcopy(defaults["providers"]))
    return normalized


def model_provider_secret_provider(
    provider: str | dict,
    secret_provider: str | None = None,
) -> str:
    names = model_provider_secret_names(provider, secret_provider=secret_provider)
    if names:
        return names[0]
    return _model_provider_name(provider).strip()


def model_provider_secret_names(
    provider: str | dict,
    *,
    secret_provider: str | None = None,
) -> list[str]:
    provider_name = _model_provider_name(provider).strip()
    explicit_secret_provider = _model_provider_secret_provider_value(
        provider,
        explicit=secret_provider,
    )
    ordered: list[str] = []
    if explicit_secret_provider:
        ordered.append(
            DEEPSEEK_SECRET_PROVIDER
            if _is_deepseek_secret_name(explicit_secret_provider)
            else explicit_secret_provider
        )
        if provider_name:
            ordered.append(provider_name)
    elif _is_deepseek_secret_name(provider_name):
        ordered.append(DEEPSEEK_SECRET_PROVIDER)
    elif provider_name:
        ordered.append(provider_name)
    if _is_deepseek_secret_name(explicit_secret_provider) or _is_deepseek_secret_name(
        provider_name
    ):
        ordered.extend(DEEPSEEK_SECRET_ALIASES)
    deduped: list[str] = []
    for name in ordered:
        if name and name not in deduped:
            deduped.append(name)
    return deduped


def _model_provider_name(provider: str | dict) -> str:
    if isinstance(provider, dict):
        return str(provider.get("name") or provider.get("model_provider") or "").strip()
    return str(provider or "").strip()


def _model_provider_secret_provider_value(
    provider: str | dict,
    *,
    explicit: str | None = None,
) -> str:
    if explicit is not None:
        return str(explicit or "").strip()
    if isinstance(provider, dict):
        return str(provider.get("secret_provider") or "").strip()
    return ""


def _is_deepseek_secret_name(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized in DEEPSEEK_SECRET_ALIASES


def _model_provider_env_candidates(
    *,
    provider_name: str,
    secret_provider: str | None,
    api_key_env: str | None,
) -> list[str]:
    candidates = env_candidates_for_provider(provider_name, api_key_env)
    if secret_provider:
        candidates.extend(env_candidates_for_provider(secret_provider, api_key_env))
    deduped: list[str] = []
    for candidate in candidates:
        name = candidate.strip().upper()
        if name and name not in deduped:
            deduped.append(name)
    return deduped


def resolve_model_provider_secret(
    *,
    session: Session | None,
    organization_id: str | None,
    user_id: str | None,
    provider_name: str,
    secret_provider: str | None = None,
    api_key_env: str | None = None,
    platform_managed: bool = False,
) -> SecretResolution:
    if platform_managed:
        platform_key = _settings_api_key_for_env(PLATFORM_API_KEY_ENV)
        if platform_key:
            return SecretResolution(value=platform_key, source="env_platform")
        return SecretResolution(value="", source="missing")
    if api_key_env == PLATFORM_API_KEY_ENV:
        api_key_env = None
    secret_names = model_provider_secret_names(
        provider_name,
        secret_provider=secret_provider,
    )
    for secret_name in secret_names:
        resolved = resolve_secret(
            session,
            organization_id=organization_id,
            user_id=user_id,
            provider=secret_name,
            purpose=SECRET_PURPOSE_MODEL_PROVIDER,
            env_candidates=[],
        )
        if resolved.found:
            return resolved
    env_provider_name = secret_names[0] if secret_names else provider_name
    env_candidates = _model_provider_env_candidates(
        provider_name=provider_name,
        secret_provider=secret_provider,
        api_key_env=api_key_env,
    )
    env_candidates = [
        candidate for candidate in env_candidates if candidate != PLATFORM_API_KEY_ENV
    ]
    return resolve_secret(
        session,
        organization_id=organization_id,
        user_id=user_id,
        provider=env_provider_name,
        purpose=SECRET_PURPOSE_MODEL_PROVIDER,
        env_candidates=env_candidates,
    )


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
        temperature: float = 0.2,
        include_stream_usage: bool = True,
        max_tokens: int | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = str(base_url or settings.model_gateway_base_url)
        self.api_key = api_key if api_key is not None else settings.model_gateway_api_key
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.include_stream_usage = include_stream_usage
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
            "User-Agent": MODEL_GATEWAY_USER_AGENT,
        }
        http_request = request.Request(
            urljoin(self.base_url.rstrip("/") + "/", "chat/completions"),
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                raw = self._decode_completion_response(response.read().decode("utf-8"))
            usage = self._normalize_usage(raw.get("usage"))
            content = self._extract_content(raw)
        except error.HTTPError as exc:
            model_call_errors_total.inc()
            formatted = self._format_http_error(exc)
            if exc.code in {401, 403}:
                raise ModelAuthError(formatted) from exc
            raise ModelGatewayError(formatted) from exc
        except ModelGatewayError:
            model_call_errors_total.inc()
            raise
        except (OSError, json.JSONDecodeError) as exc:
            model_call_errors_total.inc()
            raise ModelGatewayError(str(exc)) from exc

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

    @staticmethod
    def _normalize_usage(raw_usage: object) -> dict:
        if raw_usage is None:
            return {}
        if not isinstance(raw_usage, dict):
            raise ModelGatewayError("model response usage must be an object")
        usage = dict(raw_usage)
        for key in ("prompt_tokens", "completion_tokens"):
            value = usage.get(key)
            if value is None:
                continue
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ModelGatewayError(f"model response {key} must be a non-negative integer")
        return usage

    def _decode_completion_response(self, body: str) -> dict:
        try:
            raw = json.loads(body)
        except json.JSONDecodeError as exc:
            if exc.msg != "Extra data":
                raise
            return self._collapse_concatenated_completion_chunks(body)
        if not isinstance(raw, dict):
            raise ModelGatewayError("model response must be a JSON object")
        return raw

    def _collapse_concatenated_completion_chunks(self, body: str) -> dict:
        decoder = json.JSONDecoder()
        position = 0
        chunk_count = 0
        content_parts: list[str] = []
        usage: dict = {}
        finish_reason: object = None
        response_metadata: dict = {}
        response_identity: dict[str, object] = {}
        terminal_seen = False
        usage_seen = False

        while position < len(body):
            while position < len(body) and body[position].isspace():
                position += 1
            if position >= len(body):
                break
            try:
                chunk, position = decoder.raw_decode(body, position)
            except json.JSONDecodeError as exc:
                raise ModelGatewayError(
                    "model response contains malformed concatenated completion chunks"
                ) from exc
            if not isinstance(chunk, dict) or chunk.get("object") != "chat.completion.chunk":
                raise ModelGatewayError(
                    "model response contains unsupported concatenated JSON documents"
                )
            if usage_seen:
                raise ModelGatewayError(
                    "model completion chunks contain a document after usage"
                )

            chunk_count += 1
            for key in ("id", "created", "model", "system_fingerprint"):
                value = chunk.get(key)
                if value is None:
                    continue
                if key in {"id", "model"}:
                    expected = response_identity.setdefault(key, value)
                    if value != expected:
                        raise ModelGatewayError(
                            f"model completion chunks have inconsistent {key} values"
                        )
                response_metadata[key] = value

            choices = chunk.get("choices", [])
            if not isinstance(choices, list):
                raise ModelGatewayError("model completion chunk choices must be a list")
            chunk_usage = chunk.get("usage")
            if terminal_seen:
                if choices or chunk_usage is None:
                    raise ModelGatewayError(
                        "model completion chunks only allow a usage-only final document "
                        "after the terminal choice"
                    )
                if not isinstance(chunk_usage, dict):
                    raise ModelGatewayError("model completion chunk usage must be an object")
                usage = chunk_usage
                usage_seen = True
                continue

            choice = None
            for item in choices:
                if not isinstance(item, dict):
                    raise ModelGatewayError("model completion chunk choice must be an object")
                if item.get("index", 0) != 0:
                    raise ModelGatewayError(
                        "model completion chunk choice index must be 0"
                    )
                if choice is not None:
                    raise ModelGatewayError(
                        "model completion chunk must contain at most one choice"
                    )
                choice = item
            if choice is not None:
                delta = choice.get("delta") or {}
                if not isinstance(delta, dict):
                    raise ModelGatewayError("model completion chunk delta must be an object")
                piece = self._stream_delta_text(delta.get("content"))
                if piece:
                    if terminal_seen:
                        raise ModelGatewayError(
                            "model completion chunks contain content after termination"
                        )
                    content_parts.append(piece)
                chunk_finish_reason = choice.get("finish_reason")
                if chunk_finish_reason is not None:
                    if not isinstance(chunk_finish_reason, str) or not chunk_finish_reason:
                        raise ModelGatewayError(
                            "model completion chunk finish reason must be a non-empty string"
                        )
                    if terminal_seen:
                        raise ModelGatewayError(
                            "model completion chunks contain multiple terminal choices"
                        )
                    finish_reason = chunk_finish_reason
                    terminal_seen = True

            if chunk_usage is not None:
                if not isinstance(chunk_usage, dict):
                    raise ModelGatewayError("model completion chunk usage must be an object")
                usage = chunk_usage
                usage_seen = True

        if chunk_count < 2:
            raise ModelGatewayError(
                "model response did not contain multiple completion chunks"
            )
        if not terminal_seen:
            raise ModelGatewayError(
                "model completion chunks ended without a terminal finish reason"
            )
        content = "".join(content_parts)
        if not content:
            raise ModelGatewayError("model completion chunks did not produce content")

        return {
            **response_metadata,
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content,
                    },
                    "finish_reason": finish_reason,
                }
            ],
            "usage": usage,
            "compatibility_mode": "concatenated_chat_completion_chunks",
            "chunk_count": chunk_count,
        }

    def _uses_local_mock(self) -> bool:
        uses_mock = self.api_key in {"", "replace-me"} or self.base_url.endswith("/mock-model")
        if uses_mock and get_settings().runtime_profile == "local":
            raise ModelSetupRequiredError("Model provider setup is required")
        return uses_mock

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
            "User-Agent": MODEL_GATEWAY_USER_AGENT,
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
                    if data == "":
                        continue
                    if data == "[DONE]":
                        break
                    try:
                        frame = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    raw_last = frame
                    choices = frame.get("choices") or []
                    if choices:
                        delta = choices[0].get("delta") or {}
                        piece = self._stream_delta_text(delta.get("content"))
                        if piece:
                            text_total += piece
                            yield ModelStreamChunk(text=piece)
                    frame_usage = frame.get("usage")
                    if isinstance(frame_usage, dict):
                        usage = frame_usage
        except error.HTTPError as exc:
            model_call_errors_total.inc()
            formatted = self._format_http_error(exc)
            if exc.code in {401, 403}:
                raise ModelAuthError(formatted) from exc
            raise ModelGatewayError(formatted) from exc
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
            "temperature": self.temperature,
        }
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens
        response_format = self._response_format_payload(request_payload.response_format)
        if response_format is not None:
            payload["response_format"] = response_format
        if stream:
            payload["stream"] = True
            if self.include_stream_usage:
                payload["stream_options"] = {"include_usage": True}
        return payload

    @staticmethod
    def _stream_delta_text(content: object) -> str:
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return ""
        pieces = []
        for item in content:
            if isinstance(item, str):
                pieces.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                pieces.append(item["text"])
        return "".join(pieces)

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
        detail = self._redact_known_secret(body.strip())
        if len(detail) > 500:
            detail = f"{detail[:500]}..."
        if detail:
            return f"upstream model gateway returned HTTP {exc.code}: {detail}"
        return f"upstream model gateway returned HTTP {exc.code}: {exc.reason}"

    def _redact_known_secret(self, value: str) -> str:
        secret = str(self.api_key or "").strip()
        if not secret or secret == "replace-me" or secret not in value:
            return value
        suffix = secret[-4:] if len(secret) >= 4 else "****"
        return value.replace(secret, f"****{suffix}")


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
        uses_mock = self.api_key in {"", "replace-me"} or self.base_url.endswith("/mock-model")
        if uses_mock and get_settings().runtime_profile == "local":
            raise ModelSetupRequiredError("Model provider setup is required")
        return uses_mock

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
        provider = self._provider(
            settings=settings,
            provider_name=provider_name,
            model_name=model_name,
        )
        validate_platform_model_selection(provider_name, model_name)
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

    def _provider(self, *, settings: dict, provider_name: str, model_name: str) -> dict:
        matching_provider: dict | None = None
        for provider in settings.get("providers", []):
            if provider.get("name") == provider_name:
                if provider.get("model") == model_name:
                    return provider
                if matching_provider is None:
                    matching_provider = provider
        if matching_provider is not None:
            return matching_provider
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
                    _model_gateway_for_provider_compat(
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
        request_metadata: dict | None = None,
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
        self.request_metadata = request_metadata or {}

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

    def _extra_request_metadata(self) -> dict:
        return {
            str(key): value
            for key, value in self.request_metadata.items()
            if isinstance(key, str) and value not in (None, [], {})
        }

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

    def _transition_running_model_call(
        self,
        model_call: ModelCall,
        **values,
    ) -> bool:
        # traced_operation persists its span in this session. Commit that span
        # first, then use a conditional update so a cancellation committed by
        # another request cannot be overwritten by a late provider result.
        self.session.commit()
        result = self.session.execute(
            update(ModelCall)
            .where(ModelCall.id == model_call.id, ModelCall.status == "RUNNING")
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            self.session.rollback()
            self.session.refresh(model_call)
            return False
        self.session.refresh(model_call)
        return True

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
        except ModelCallCancelledError:
            raise
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
            except ModelCallCancelledError:
                raise
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
                extra_metadata=self._extra_request_metadata(),
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
            transitioned = self._transition_running_model_call(
                model_call,
                status="FAILED",
                terminal_status="failed",
                duration_ms=int((time.monotonic() - started_at) * 1000),
                error_message=str(exc),
            )
            if not transitioned:
                raise ModelCallCancelledError(
                    model_call.error_message or "model call cancelled"
                ) from exc
            if not isinstance(exc, (ModelRateLimitError, ModelCircuitOpenError)):
                ModelCircuitBreaker.record_failure(
                    key=circuit_key,
                    failure_threshold=int(settings.circuit_breaker.get("failure_threshold") or 3),
                    cooldown_seconds=int(settings.circuit_breaker.get("cooldown_seconds") or 60),
                )
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
        transitioned = self._transition_running_model_call(
            model_call,
            status="SUCCESS",
            terminal_status="success",
            prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage.get("completion_tokens", 0) or 0),
            duration_ms=int((time.monotonic() - started_at) * 1000),
            response_json={
                "content_preview": response_payload.content[:2000],
                "usage": usage,
                "raw_response": response_payload.raw_response,
            },
            error_message=None,
        )
        if not transitioned:
            raise ModelCallCancelledError(model_call.error_message or "model call cancelled")
        ModelCircuitBreaker.record_success(key=circuit_key)
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
        extra_metadata: dict | None = None,
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
            **(extra_metadata or {}),
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
        except ModelCallCancelledError:
            raise
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
            except ModelCallCancelledError:
                raise
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
                extra_metadata=self._extra_request_metadata(),
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
            transitioned = self._transition_running_model_call(
                model_call,
                status="FAILED",
                terminal_status="stream_aborted",
                duration_ms=int((time.monotonic() - started_at) * 1000),
                error_message="stream closed before completion",
            )
            if not transitioned:
                raise
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
            self.session.commit()
            raise
        except Exception as exc:
            transitioned = self._transition_running_model_call(
                model_call,
                status="FAILED",
                terminal_status="failed",
                duration_ms=int((time.monotonic() - started_at) * 1000),
                error_message=str(exc),
            )
            if not transitioned:
                raise ModelCallCancelledError(
                    model_call.error_message or "model call cancelled"
                ) from exc
            if not isinstance(exc, (ModelRateLimitError, ModelCircuitOpenError)):
                ModelCircuitBreaker.record_failure(
                    key=circuit_key,
                    failure_threshold=int(settings.circuit_breaker.get("failure_threshold") or 3),
                    cooldown_seconds=int(settings.circuit_breaker.get("cooldown_seconds") or 60),
                )
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

        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(
            usage.get("completion_tokens", 0) or max(1, len(text_accumulator) // 4)
        )
        transitioned = self._transition_running_model_call(
            model_call,
            status="SUCCESS",
            terminal_status="success",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_ms=int((time.monotonic() - started_at) * 1000),
            response_json={
                "content_preview": text_accumulator[:2000],
                "usage": {
                    **usage,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                },
                "raw_response": raw_response,
                "stream": True,
            },
            error_message=None,
        )
        if not transitioned:
            raise ModelCallCancelledError(model_call.error_message or "model call cancelled")
        ModelCircuitBreaker.record_success(key=circuit_key)
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
        return _model_gateway_for_provider_compat(
            settings.provider,
            timeout_seconds=None,
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
    secret_provider = str(provider.get("secret_provider") or "").strip()
    api_key_env = provider.get("api_key_env")
    if is_platform_model_provider(provider):
        return _settings_api_key_for_env(PLATFORM_API_KEY_ENV)
    if provider_name and session is not None and organization_id:
        resolved = resolve_model_provider_secret(
            session=session,
            organization_id=organization_id,
            user_id=user_id,
            provider_name=provider_name,
            secret_provider=secret_provider,
            api_key_env=str(api_key_env) if isinstance(api_key_env, str) else None,
        )
        if resolved.found:
            return resolved.value
    api_key = provider.get("api_key")
    if isinstance(api_key, str) and api_key not in {"", "replace-me"}:
        return api_key
    if isinstance(api_key_env, str) and api_key_env:
        if api_key_env == PLATFORM_API_KEY_ENV:
            return api_key if isinstance(api_key, str) else None
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
        secret_provider = model_provider_secret_provider(provider)
        row = upsert_secret(
            session,
            organization_id=organization_id,
            actor_id="system",
            scope=SECRET_SCOPE_ORG,
            owner_user_id=None,
            provider=secret_provider,
            purpose=SECRET_PURPOSE_MODEL_PROVIDER,
            secret_ref=f"secret://models/{secret_provider}/api-key",
            secret_value=raw_key,
        )
        provider["api_key_configured"] = True
        provider["api_key_source"] = SECRET_SOURCE_ORG
        provider["api_key_secret_id"] = row.id
    return sanitized


def _settings_api_key_for_env(api_key_env: str) -> str | None:
    settings = get_settings()
    if api_key_env == PLATFORM_API_KEY_ENV:
        return settings.ai_provider_api_key or None
    if api_key_env == "DEEPSEEK_API_KEY":
        return settings.deepseek_api_key or None
    return None


def _model_gateway_for_provider_compat(
    provider: dict,
    *,
    timeout_seconds: int | None = None,
    session: Session | None = None,
    organization_id: str | None = None,
    user_id: str | None = None,
) -> ModelGateway:
    try:
        return model_gateway_for_provider(
            provider,
            timeout_seconds=timeout_seconds,
            session=session,
            organization_id=organization_id,
            user_id=user_id,
        )
    except TypeError as exc:
        if "unexpected keyword argument" not in str(exc):
            raise
        return model_gateway_for_provider(provider, timeout_seconds=timeout_seconds)


def model_gateway_for_provider(
    provider: dict,
    *,
    timeout_seconds: int | None = None,
    session: Session | None = None,
    organization_id: str | None = None,
    user_id: str | None = None,
) -> ModelGateway:
    timeout = int(timeout_seconds or provider.get("timeout_seconds") or 30)
    configured_max_tokens = provider.get("max_output_tokens")
    if configured_max_tokens is not None and (
        not isinstance(configured_max_tokens, int)
        or isinstance(configured_max_tokens, bool)
        or configured_max_tokens <= 0
    ):
        raise ModelGatewayError("provider max_output_tokens must be a positive integer")
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
            max_tokens=configured_max_tokens or 4096,
        )
    configured_temperature = provider.get("temperature")
    if configured_temperature is None:
        temperature = 0.2
    else:
        if isinstance(configured_temperature, bool):
            raise ModelGatewayError("provider temperature must be a finite number from 0 to 2")
        try:
            temperature = float(configured_temperature)
        except (TypeError, ValueError) as exc:
            raise ModelGatewayError(
                "provider temperature must be a finite number from 0 to 2"
            ) from exc
        if not math.isfinite(temperature) or not 0 <= temperature <= 2:
            raise ModelGatewayError("provider temperature must be a finite number from 0 to 2")
    return OpenAICompatibleModelGateway(
        base_url=provider.get("base_url"),
        api_key=api_key,
        timeout_seconds=timeout,
        temperature=temperature,
        include_stream_usage=bool(provider.get("include_stream_usage", True)),
        max_tokens=configured_max_tokens,
    )
