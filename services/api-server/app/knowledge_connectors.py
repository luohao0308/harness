from __future__ import annotations

import re
from typing import Any, Literal

from app.knowledge_dify import secret_ref_looks_like_raw_secret
from app.tools.capabilities import redact_secrets

CONNECTOR_RELEASE_STATE_USABLE = "usable"
CONNECTOR_RELEASE_STATE_CONFIGURED_BUT_UNAVAILABLE = "configured-but-unavailable"
CONNECTOR_RELEASE_STATE_PREVIEW_NOT_COUNTED = "preview-not-counted"

ConnectorReleaseState = Literal[
    "usable",
    "configured-but-unavailable",
    "preview-not-counted",
]

VALID_CONNECTOR_RELEASE_STATES: tuple[ConnectorReleaseState, ...] = (
    CONNECTOR_RELEASE_STATE_USABLE,
    CONNECTOR_RELEASE_STATE_CONFIGURED_BUT_UNAVAILABLE,
    CONNECTOR_RELEASE_STATE_PREVIEW_NOT_COUNTED,
)

_LOCAL_USABLE_PROVIDERS = {
    "uploaded_file",
    "markdown_directory",
    "local_upload",
    "inline_document",
}
_USABLE_EXTERNAL_PROVIDERS = {"coze", "dify"}
_CONFIGURED_BUT_UNAVAILABLE_PROVIDERS = {
    "langchain",
    "volcengine",
    "notion",
    "postgres",
    "ollama",
}
_PREVIEW_ONLY_PROVIDERS = {"ragflow", "local_dify", "local_ragflow"}
_CRAWLER_PROVIDERS = {"crawler", "web_crawler"}
_SECRET_REF_REQUIRED_PROVIDERS = (
    _USABLE_EXTERNAL_PROVIDERS
    | _CONFIGURED_BUT_UNAVAILABLE_PROVIDERS
    | _PREVIEW_ONLY_PROVIDERS
)
_ENDPOINT_REQUIRED_PROVIDERS = (
    _USABLE_EXTERNAL_PROVIDERS
    | _CONFIGURED_BUT_UNAVAILABLE_PROVIDERS
    | _PREVIEW_ONLY_PROVIDERS
)
_REFERENCE_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "dify": ("dataset_id",),
    "coze": ("dataset_id",),
    "ragflow": ("dataset_id",),
}
CONNECTOR_PROVIDER_LABELS = {
    "coze": "Coze API",
    "dify": "Dify API",
    "langchain": "LangChain Retriever",
    "ragflow": "RAGFlow API",
    "volcengine": "Volcengine Knowledge API",
    "local_dify": "Local Dify endpoint",
    "local_ragflow": "Local RAGFlow endpoint",
    "markdown_directory": "Local Markdown directory",
    "uploaded_file": "Uploaded file",
    "local_upload": "Uploaded file",
    "inline_document": "Inline document",
    "notion": "Notion API",
    "postgres": "Postgres read-only source",
    "ollama": "Ollama/local model source",
}


def _endpoint_has_userinfo(endpoint: str | None) -> bool:
    if not endpoint:
        return False
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://[^/@]+@", endpoint.strip()))


def _connector_requests_crawling(settings: dict[str, Any]) -> bool:
    metadata = settings.get("metadata") if isinstance(settings.get("metadata"), dict) else {}
    crawler_flags = ("crawl", "crawler", "recursive", "follow_links")
    if any(flag in settings or flag in metadata for flag in crawler_flags):
        return True
    return "max_depth" in settings or "max_depth" in metadata


def connector_provider_key(settings_json: dict[str, Any] | None, *, source_type: str) -> str:
    settings = settings_json if isinstance(settings_json, dict) else {}
    provider = str(
        settings.get("connector_provider")
        or settings.get("provider")
        or settings.get("source_provider")
        or ""
    ).strip().lower()
    if provider:
        return provider
    if source_type in {"text", "markdown", "document"}:
        return "uploaded_file"
    return source_type.strip().lower() or "uploaded_file"


def _normalized_release_state(value: Any) -> ConnectorReleaseState | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in VALID_CONNECTOR_RELEASE_STATES:
        return normalized  # type: ignore[return-value]
    return None


def connector_release_state(
    settings_json: dict[str, Any] | None,
    *,
    source_type: str,
) -> ConnectorReleaseState:
    settings = settings_json if isinstance(settings_json, dict) else {}
    provider = connector_provider_key(settings, source_type=source_type)
    if provider in _CRAWLER_PROVIDERS:
        raise ValueError("crawler connectors are not allowed")
    if provider in _LOCAL_USABLE_PROVIDERS:
        return CONNECTOR_RELEASE_STATE_USABLE
    if provider in _USABLE_EXTERNAL_PROVIDERS:
        return CONNECTOR_RELEASE_STATE_USABLE
    if provider in _CONFIGURED_BUT_UNAVAILABLE_PROVIDERS:
        return CONNECTOR_RELEASE_STATE_CONFIGURED_BUT_UNAVAILABLE
    if provider in _PREVIEW_ONLY_PROVIDERS:
        return CONNECTOR_RELEASE_STATE_PREVIEW_NOT_COUNTED
    explicit_state = _normalized_release_state(
        settings.get("connector_release_state") or settings.get("release_state")
    )
    if explicit_state is not None:
        return explicit_state
    if provider in _LOCAL_USABLE_PROVIDERS:
        return CONNECTOR_RELEASE_STATE_USABLE
    return CONNECTOR_RELEASE_STATE_PREVIEW_NOT_COUNTED


def connector_counts_toward_complete_usable(
    settings_json: dict[str, Any] | None,
    *,
    source_type: str,
) -> bool:
    return (
        connector_release_state(settings_json, source_type=source_type)
        == CONNECTOR_RELEASE_STATE_USABLE
    )


def connector_requires_secret_ref(provider: str) -> bool:
    return provider.strip().lower() in _SECRET_REF_REQUIRED_PROVIDERS


def connector_requires_endpoint(provider: str) -> bool:
    return provider.strip().lower() in _ENDPOINT_REQUIRED_PROVIDERS


def connector_required_reference_fields(provider: str) -> tuple[str, ...]:
    return _REFERENCE_REQUIRED_FIELDS.get(provider.strip().lower(), ())


def connector_provider_label(provider: str) -> str:
    normalized = provider.strip().lower()
    return CONNECTOR_PROVIDER_LABELS.get(normalized, normalized or "Unknown connector")


def connector_provider_release_matrix() -> dict[str, dict[str, str | bool]]:
    providers = (
        _LOCAL_USABLE_PROVIDERS
        | _USABLE_EXTERNAL_PROVIDERS
        | _CONFIGURED_BUT_UNAVAILABLE_PROVIDERS
        | _PREVIEW_ONLY_PROVIDERS
    )
    return {
        provider: {
            "provider": provider,
            "label": connector_provider_label(provider),
            "release_state": connector_release_state(
                {"provider": provider},
                source_type="connector",
            ),
            "counts_as_usable": connector_counts_toward_complete_usable(
                {"provider": provider},
                source_type="connector",
            ),
        }
        for provider in sorted(providers)
    }


def normalize_connector_settings(
    settings_json: dict[str, Any] | None,
    *,
    source_type: str,
) -> dict[str, Any]:
    settings = dict(settings_json or {})
    provider = connector_provider_key(settings, source_type=source_type)
    connector_kind = str(settings.get("connector_kind") or "").strip().lower()
    if provider in _CRAWLER_PROVIDERS or connector_kind in _CRAWLER_PROVIDERS:
        raise ValueError("crawler connectors are not allowed")
    if _connector_requests_crawling(settings):
        raise ValueError("crawler-style connector behavior is out of scope")
    if provider in _SECRET_REF_REQUIRED_PROVIDERS and not str(
        settings.get("secret_ref") or settings.get("connector_secret_ref") or ""
    ).strip():
        raise ValueError("connector secret_ref is required")
    secret_ref = str(settings.get("secret_ref") or settings.get("connector_secret_ref") or "")
    if secret_ref and secret_ref_looks_like_raw_secret(secret_ref):
        raise ValueError(
            "connector secret_ref must reference a server-side secret, not a raw secret"
        )
    if provider in _ENDPOINT_REQUIRED_PROVIDERS and not str(
        settings.get("endpoint") or settings.get("uri") or ""
    ).strip():
        raise ValueError("connector endpoint is required")
    reference_fields = connector_required_reference_fields(provider)
    if reference_fields and not any(
        str(settings.get(field) or "").strip() for field in reference_fields
    ):
        raise ValueError("connector dataset_id is required")
    if _endpoint_has_userinfo(str(settings.get("endpoint") or settings.get("uri") or "")):
        raise ValueError("connector endpoint must not include credentials")
    normalized = redact_secrets(settings)
    normalized["connector_provider"] = provider
    normalized["connector_release_state"] = connector_release_state(
        normalized,
        source_type=source_type,
    )
    normalized["connector_counts_toward_complete_usable"] = (
        normalized["connector_release_state"] == CONNECTOR_RELEASE_STATE_USABLE
    )
    return normalized
