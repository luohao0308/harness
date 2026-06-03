from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.model_gateway import (
    DEFAULT_MODEL_SETTINGS,
    MODEL_SETTINGS_KEY,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelStreamChunk,
    model_gateway_for_provider,
    normalize_model_settings,
)
from app.db.models import SystemSetting


class TeamModelRuntime(Protocol):
    def complete(
        self,
        *,
        organization_id: str,
        model_provider: str,
        model_name: str,
        messages: list[ModelMessage],
    ) -> ModelResponse:
        """Run one normal Team conversation turn."""

    def stream(
        self,
        *,
        organization_id: str,
        model_provider: str,
        model_name: str,
        messages: list[ModelMessage],
    ) -> Iterator[ModelStreamChunk]:
        """Stream one Team conversation turn."""


@dataclass
class GatewayTeamModelRuntime:
    session: Session

    def complete(
        self,
        *,
        organization_id: str,
        model_provider: str,
        model_name: str,
        messages: list[ModelMessage],
    ) -> ModelResponse:
        provider_name, resolved_model_name, provider = self._resolved_provider(
            organization_id=organization_id,
            model_provider=model_provider,
            model_name=model_name,
        )
        response = model_gateway_for_provider(provider).complete(
            ModelRequest(
                model_provider=provider_name,
                model_name=resolved_model_name,
                response_format="text",
                messages=messages,
            )
        )
        return response.model_copy(
            update={
                "model_provider": provider_name,
                "model_name": resolved_model_name,
            }
        )

    def stream(
        self,
        *,
        organization_id: str,
        model_provider: str,
        model_name: str,
        messages: list[ModelMessage],
    ) -> Iterator[ModelStreamChunk]:
        provider_name, resolved_model_name, provider = self._resolved_provider(
            organization_id=organization_id,
            model_provider=model_provider,
            model_name=model_name,
        )
        yield from model_gateway_for_provider(provider).stream(
            ModelRequest(
                model_provider=provider_name,
                model_name=resolved_model_name,
                response_format="text",
                messages=messages,
            )
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

    @staticmethod
    def _provider(*, settings: dict, provider_name: str) -> dict:
        for provider in settings.get("providers", []):
            if isinstance(provider, dict) and provider.get("name") == provider_name:
                return provider
        return {"name": provider_name, "status": "healthy"}

    def _resolved_provider(
        self,
        *,
        organization_id: str,
        model_provider: str,
        model_name: str,
    ) -> tuple[str, str, dict]:
        settings = self._settings_for_org(organization_id)
        default_provider = str(settings.get("default_provider") or "openai-compatible")
        default_model = str(settings.get("default_model") or "default")
        provider_name = model_provider or default_provider
        if provider_name == "default":
            provider_name = default_provider
        resolved_model_name = model_name
        if not resolved_model_name or resolved_model_name == "default":
            resolved_model_name = default_model
        return (
            provider_name,
            resolved_model_name,
            self._provider(settings=settings, provider_name=provider_name),
        )
