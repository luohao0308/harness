from __future__ import annotations

import json
import time
from dataclasses import dataclass
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
        {"name": "openai-compatible", "status": "healthy", "rate_limit_rpm": 600},
    ],
    "rate_limits": {"rpm": 600, "tpm": 120000},
    "health": {"status": "healthy", "updated_at": None},
}


@dataclass(frozen=True)
class ResolvedModelSettings:
    organization_id: str | None
    default_provider: str
    default_model: str
    provider: dict
    rate_limit_rpm: int


class ModelRateLimiter:
    _calls: dict[str, list[float]] = {}

    @classmethod
    def check(cls, *, key: str, rpm: int, now: float | None = None) -> None:
        if rpm <= 0:
            return
        current_time = now or time.time()
        window_start = current_time - 60
        timestamps = [
            timestamp for timestamp in cls._calls.get(key, []) if timestamp >= window_start
        ]
        if len(timestamps) >= rpm:
            cls._calls[key] = timestamps
            raise ModelGatewayError("model rate limit exceeded")
        timestamps.append(current_time)
        cls._calls[key] = timestamps

    @classmethod
    def clear(cls) -> None:
        cls._calls.clear()


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
            return DEFAULT_MODEL_SETTINGS
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
            if provider.get("api_key") in {None, "", "replace-me"} and not provider.get("base_url"):
                mode = "mock"
                status = "healthy"
            if status not in {"healthy", "degraded"}:
                error_message = f"provider status is {status}"
            results.append(
                {
                    "provider": str(provider.get("name") or "unknown"),
                    "model": str(provider.get("model") or default_model),
                    "status": status,
                    "mode": mode,
                    "checked_at": utc_now(),
                    "latency_ms": int((time.monotonic() - started_at) * 1000),
                    "error_message": error_message,
                }
            )
        return results

    def _settings_for_org(self, organization_id: str) -> dict:
        setting = self.session.execute(
            select(SystemSetting).where(
                SystemSetting.organization_id == organization_id,
                SystemSetting.key == MODEL_SETTINGS_KEY,
            )
        ).scalar_one_or_none()
        if setting is None:
            return DEFAULT_MODEL_SETTINGS
        return setting.value_json


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
        try:
            return self._attempt(request_payload)
        except ModelGatewayError:
            if not fallbacks:
                raise

        last_error: ModelGatewayError | None = None
        for fallback in fallbacks:
            self.event_store.append(
                task_id=self.task_id,
                agent_run_id=self.agent_run_id,
                event_type=EventType.MODEL_FALLBACK_USED,
                payload_json={
                    "model_provider": fallback.model_provider,
                    "model_name": fallback.model_name,
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
            ModelRateLimiter.check(key=limiter_key, rpm=settings.rate_limit_rpm)
            response_payload = gateway.complete(request_payload)
        except Exception as exc:
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
        return {
            "model_provider": request_payload.model_provider,
            "model_name": request_payload.model_name,
            "response_format": request_payload.response_format,
            "messages": [
                {
                    "role": message.role,
                    "content_preview": message.content[:500],
                    "content_length": len(message.content),
                }
                for message in request_payload.messages
            ],
        }

    def _gateway_from_settings(self, provider: dict) -> ModelGateway:
        return OpenAICompatibleModelGateway(
            base_url=provider.get("base_url"),
            api_key=provider.get("api_key"),
            timeout_seconds=int(provider.get("timeout_seconds") or 30),
        )
