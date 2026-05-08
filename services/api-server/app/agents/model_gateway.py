from __future__ import annotations

import json
import time
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
from app.db.models import ModelCall, SystemSetting, Task, utc_now
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


class ModelGatewayError(RuntimeError):
    pass


MODEL_SETTINGS_KEY = "settings.models"


DEFAULT_MODEL_SETTINGS = {
    "default_provider": "openai-compatible",
    "default_model": "default",
    "providers": [
        {
            "name": "openai-compatible",
            "status": "healthy",
            "rate_limit_rpm": 600,
            "rate_limit_tpm": 120000,
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


@dataclass(frozen=True)
class ResolvedModelSettings:
    organization_id: str | None
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
        token_entries = [
            entry for entry in cls._tokens.get(key, []) if entry[0] >= window_start
        ]
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
            "opened_until": datetime.fromtimestamp(opened_until).isoformat()
            if is_open
            else None,
        }

    @classmethod
    def clear(cls) -> None:
        cls._states.clear()


class ModelGateway(Protocol):
    def complete(self, request: ModelRequest) -> ModelResponse:
        """Call an OpenAI-compatible gateway through the platform boundary."""


class MockModelGateway:
    def complete(self, request: ModelRequest) -> ModelResponse:
        model_calls_total.inc()
        model_tokens_input_total.inc(0)
        model_tokens_output_total.inc(0)
        return ModelResponse(
            content="{}",
            model_provider=request.model_provider,
            model_name=request.model_name,
            usage={"prompt_tokens": 0, "completion_tokens": 0},
            raw_response={"mode": "mock"},
        )


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

        payload = {
            "model": request_payload.model_name,
            "messages": [message.model_dump() for message in request_payload.messages],
            "response_format": {"type": request_payload.response_format},
        }
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
        except (OSError, error.HTTPError, json.JSONDecodeError) as exc:
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
        return self.api_key == "replace-me" or self.base_url.endswith("/mock-model")

    def _extract_content(self, raw: dict) -> str:
        choices = raw.get("choices", [])
        if not choices:
            raise ModelGatewayError("model response has no choices")
        message = choices[0].get("message", {})
        content = message.get("content")
        if not isinstance(content, str):
            raise ModelGatewayError("model response content is missing")
        return content


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
            provider.get("rate_limit_rpm")
            or settings.get("rate_limits", {}).get("rpm")
            or 600
        )
        tpm = int(
            provider.get("rate_limit_tpm")
            or settings.get("rate_limits", {}).get("tpm")
            or 120000
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
            return DEFAULT_MODEL_SETTINGS
        setting = self.session.execute(
            select(SystemSetting).where(
                SystemSetting.organization_id == organization_id,
                SystemSetting.key == MODEL_SETTINGS_KEY,
            )
        ).scalar_one_or_none()
        if setting is None:
            return deepcopy(DEFAULT_MODEL_SETTINGS)
        return setting.value_json

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
                    OpenAICompatibleModelGateway(
                        base_url=provider.get("base_url"),
                        api_key=provider.get("api_key"),
                        timeout_seconds=int(provider.get("health_timeout_seconds") or 5),
                    ).complete(
                        ModelRequest(
                            model_provider=provider_name,
                            model_name=model_name,
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
            return deepcopy(DEFAULT_MODEL_SETTINGS)
        return setting.value_json

    def _write_settings_for_org(self, *, organization_id: str, settings: dict) -> None:
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
    ) -> None:
        self.session = session
        self.task_id = task_id
        self.agent_run_id = agent_run_id
        self.gateway = gateway
        self.event_store = EventStore(session)

    def complete(
        self,
        request_payload: ModelRequest,
        *,
        fallback_requests: list[ModelRequest] | None = None,
    ) -> ModelResponse:
        fallbacks = fallback_requests or []
        primary_error: str | None = None
        try:
            return self._attempt(request_payload)
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
                return self._attempt(fallback)
            except ModelGatewayError as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise ModelGatewayError("model gateway failed")

    def _attempt(self, request_payload: ModelRequest) -> ModelResponse:
        request_payload, settings = ModelSettingsResolver(self.session).resolve(
            task_id=self.task_id,
            request_payload=request_payload,
        )
        limiter_key = (
            f"{settings.organization_id or 'global'}:"
            f"{request_payload.model_provider}:{request_payload.model_name}"
        )
        circuit_key = limiter_key
        estimated_prompt_tokens = self._estimate_prompt_tokens(request_payload)
        gateway = self.gateway or self._gateway_from_settings(settings.provider)
        started_at = time.monotonic()
        model_call = ModelCall(
            task_id=self.task_id,
            agent_run_id=self.agent_run_id,
            model_provider=request_payload.model_provider,
            model_name=request_payload.model_name,
            status="RUNNING",
            prompt_tokens=0,
            completion_tokens=0,
            duration_ms=0,
            request_json=self._safe_request_json(request_payload),
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
            },
        )
        try:
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
                    failure_threshold=int(
                        settings.circuit_breaker.get("failure_threshold") or 3
                    ),
                    cooldown_seconds=int(
                        settings.circuit_breaker.get("cooldown_seconds") or 60
                    ),
                )
            model_call.status = "FAILED"
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
                },
            )
            self.session.flush()
            if isinstance(exc, ModelGatewayError):
                raise
            raise ModelGatewayError(str(exc)) from exc

        usage = response_payload.usage
        ModelCircuitBreaker.record_success(key=circuit_key)
        model_call.status = "SUCCESS"
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
            },
        )
        self.session.flush()
        return response_payload

    def _safe_request_json(self, request_payload: ModelRequest) -> dict:
        estimated_prompt_tokens = self._estimate_prompt_tokens(request_payload)
        return {
            "model_provider": request_payload.model_provider,
            "model_name": request_payload.model_name,
            "response_format": request_payload.response_format,
            "estimated_prompt_tokens": estimated_prompt_tokens,
            "messages": [
                {
                    "role": message.role,
                    "content_preview": message.content[:500],
                    "content_length": len(message.content),
                }
                for message in request_payload.messages
            ],
        }

    def _estimate_prompt_tokens(self, request_payload: ModelRequest) -> int:
        content_length = sum(len(message.content) for message in request_payload.messages)
        message_overhead = len(request_payload.messages) * 4
        return max(1, (content_length // 4) + message_overhead)

    def _gateway_from_settings(self, provider: dict) -> ModelGateway:
        return OpenAICompatibleModelGateway(
            base_url=provider.get("base_url"),
            api_key=provider.get("api_key"),
            timeout_seconds=int(provider.get("timeout_seconds") or 30),
        )
