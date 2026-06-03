"""Connector validation and contract helpers."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *


def _contains_raw_secret(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized not in {"auth_secret_ref", "secret_ref", "secret_scope"} and any(
                part in normalized for part in CONNECTOR_RAW_SECRET_KEYS
            ):
                return True
            if _contains_raw_secret(item):
                return True
    if isinstance(value, list):
        return any(_contains_raw_secret(item) for item in value)
    return False


def _endpoint_has_userinfo(endpoint: str | None) -> bool:
    if not endpoint:
        return False
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://[^/@]+@", endpoint.strip()))


def _redact_connector_secrets(value):
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized == "secret_ref":
                redacted[key] = item
            elif any(
                part in normalized
                for part in ("token", "password", "api_key", "apikey", "secret")
            ):
                redacted[key] = "[REDACTED]" if item else item
            else:
                redacted[key] = _redact_connector_secrets(item)
        return redacted
    if isinstance(value, list):
        return [_redact_connector_secrets(item) for item in value]
    return value


def _connector_release_state(provider: str, settings: dict) -> str:
    configured_state = str(settings.get("release_state") or "").strip().lower()
    connector_settings = {**settings, "provider": provider}
    if configured_state:
        connector_settings["release_state"] = configured_state
    return connector_release_state(connector_settings, source_type="connector")


def _connector_validation(provider: str, settings: dict) -> dict:
    errors: list[str] = []
    endpoint = str(settings.get("endpoint") or settings.get("uri") or "").strip()
    if connector_requires_secret_ref(provider) and not (
        settings.get("secret_ref") or settings.get("auth_secret_ref")
    ):
        errors.append("secret_ref_required")
    if connector_requires_endpoint(provider) and not endpoint:
        errors.append("endpoint_required")
    reference_fields = connector_required_reference_fields(provider)
    if reference_fields and not any(
        str(settings.get(field) or "").strip() for field in reference_fields
    ):
        errors.append("dataset_or_space_id_required")
    if _endpoint_has_userinfo(endpoint):
        errors.append("endpoint_must_not_include_credentials")
    metadata = settings.get("metadata") if isinstance(settings.get("metadata"), dict) else {}
    crawler_flags = {"crawl", "crawler", "recursive", "follow_links"}
    if any(flag in settings or flag in metadata for flag in crawler_flags):
        errors.append("crawler_style_connector_out_of_scope")
    if "max_depth" in settings or "max_depth" in metadata:
        errors.append("recursive_connector_depth_out_of_scope")
    if provider == "postgres" and not settings.get("read_only", True):
        errors.append("postgres_must_be_read_only_or_policy_bound")
    if provider in {"web_crawler", "crawler", "recursive_url"}:
        errors.append("web_crawler_out_of_scope")
    return {
        "provider": provider,
        "valid": not errors,
        "errors": errors,
        "secret_ref_present": bool(settings.get("secret_ref") or settings.get("auth_secret_ref")),
        "endpoint_present": bool(endpoint),
    }


def connector_validation_status(source: KnowledgeSource) -> tuple[str, list[str]]:
    settings = source.settings_json if isinstance(source.settings_json, dict) else {}
    provider = connector_provider_key(settings, source_type=source.source_type)
    if source.source_type != "connector":
        return "ready", []
    validation = _connector_validation(provider, settings)
    if validation["errors"]:
        return "invalid", list(validation["errors"])
    release_state = connector_release_state(settings, source_type=source.source_type)
    if release_state == CONNECTOR_RELEASE_STATE_USABLE:
        return "ready", []
    if release_state == CONNECTOR_RELEASE_STATE_CONFIGURED_BUT_UNAVAILABLE:
        return "configured", ["provider_configured_but_runtime_unavailable"]
    return "preview", ["preview_connector_not_counted_as_usable"]


def connector_coverage_matrix() -> dict[str, dict]:
    return connector_provider_release_matrix()


def connector_contract(
    *,
    provider: str,
    settings: dict | None = None,
    source_type: str | None = None,
) -> dict:
    normalized_provider = provider.strip().lower().replace("-", "_")
    redacted_settings = _redact_connector_secrets(settings or {})
    validation = _connector_validation(normalized_provider, redacted_settings)
    release_state = _connector_release_state(normalized_provider, redacted_settings)
    counts_as_usable = validation["valid"] and release_state == CONNECTOR_RELEASE_USABLE
    return {
        "connector_schema_version": "knowledge-connector-v1",
        "provider": normalized_provider,
        "source_type": source_type or "connector",
        "release_state": release_state,
        "counts_as_usable": counts_as_usable,
        "sync_state": "ready" if counts_as_usable else "configured_unavailable",
        "settings": redacted_settings,
        "validation": validation,
        "provider_coverage_matrix": connector_coverage_matrix(),
    }


def apply_connector_contract(source: KnowledgeSource) -> None:
    metadata = source.metadata_json if isinstance(source.metadata_json, dict) else {}
    settings = source.settings_json if isinstance(source.settings_json, dict) else {}
    provider = str(
        metadata.get("connector_provider") or settings.get("provider") or source.source_type
    )
    contract = connector_contract(
        provider=provider,
        settings=settings,
        source_type=source.source_type,
    )
    source.settings_json = contract["settings"]
    source.metadata_json = {
        **metadata,
        "connector": {key: value for key, value in contract.items() if key != "settings"},
        "connector_provider": contract["provider"],
        "release_state": contract["release_state"],
        "counts_as_usable": contract["counts_as_usable"],
    }
    if contract["counts_as_usable"]:
        source.health_status = SOURCE_HEALTH_HEALTHY
        source.last_ingestion_error = None
    else:
        source.health_status = SOURCE_HEALTH_ERROR
        source.last_ingestion_error = ",".join(contract["validation"]["errors"]) or contract[
            "release_state"
        ]


def connector_source_metadata(source: KnowledgeSource) -> dict:
    metadata = source.metadata_json if isinstance(source.metadata_json, dict) else {}
    connector = metadata.get("connector") if isinstance(metadata.get("connector"), dict) else {}
    return {
        "connector_provider": metadata.get("connector_provider"),
        "release_state": metadata.get("release_state"),
        "counts_as_usable": bool(metadata.get("counts_as_usable")),
        "sync_state": connector.get("sync_state"),
    }

__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
