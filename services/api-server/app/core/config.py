import re
from functools import lru_cache
from ipaddress import ip_address
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import AnyHttpUrl, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

AUTH_JWT_SECRET_PLACEHOLDER = "replace-with-openssl-rand-hex-32"
HARNESS_SECRET_ENCRYPTION_KEY_PLACEHOLDER = "replace-with-generated-fernet-key"
AUTH_SECRET_DOCS_URL = "docs/project-memory/runbooks/first-run-admin.md"
AI_PROVIDER_MODEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")


def _validate_ai_provider_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise ValueError("AI_PROVIDER_BASE_URL must be an HTTPS URL or HTTP loopback URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("AI_PROVIDER_BASE_URL must not include credentials, query, or fragment")
    if parsed.scheme == "http":
        try:
            is_loopback = ip_address(parsed.hostname).is_loopback
        except ValueError:
            is_loopback = parsed.hostname.lower() == "localhost"
        if not is_loopback:
            raise ValueError("AI_PROVIDER_BASE_URL only permits HTTP for loopback hosts")
    return normalized


def _validate_ai_provider_model(value: str) -> str:
    normalized = value.strip()
    if not AI_PROVIDER_MODEL_PATTERN.fullmatch(normalized):
        raise ValueError("AI provider model IDs must be 1-160 safe identifier characters")
    return normalized


class Settings(BaseSettings):
    runtime_profile: str = Field(default="server", alias="RUNTIME_PROFILE")
    runtime_data_dir: Path | None = Field(default=None, alias="RUNTIME_DATA_DIR")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_base_url: AnyHttpUrl = Field(default="http://localhost:3000", alias="APP_BASE_URL")
    console_base_url: AnyHttpUrl = Field(default="http://localhost:5173", alias="CONSOLE_BASE_URL")
    api_base_url: AnyHttpUrl = Field(default="http://localhost:8000", alias="API_BASE_URL")
    database_url: str = Field(
        default="postgresql+psycopg://agent:agent@localhost:5432/agent_harness",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    model_gateway_base_url: AnyHttpUrl = Field(
        default="http://localhost:8000/mock-model",
        alias="MODEL_GATEWAY_BASE_URL",
    )
    model_gateway_api_key: str = Field(
        default="replace-me",
        alias="MODEL_GATEWAY_API_KEY",
        repr=False,
    )
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    ai_provider_protocol: str = Field(default="chat_completions", alias="AI_PROVIDER_PROTOCOL")
    ai_provider_base_url: str = Field(
        default="https://ai.112102.xyz/v1",
        alias="AI_PROVIDER_BASE_URL",
    )
    ai_provider_model: str = Field(default="minimax-m3", alias="AI_PROVIDER_MODEL")
    ai_provider_models: Annotated[tuple[str, ...], NoDecode] = Field(
        default=(
            "deepseek-v4-flash", "gpt-oss-120b", "mimo-v2.5", "minimax-m3",
            "nvidia-gpt-oss",
        ),
        alias="AI_PROVIDER_MODELS",
    )
    ai_provider_name: str = Field(
        default="chybenzun-openai-compatible",
        alias="AI_PROVIDER_NAME",
    )
    ai_provider_api_key: str = Field(default="", alias="AI_PROVIDER_API_KEY", repr=False)
    tavily_api_key: str = Field(default="", alias="TAVILY_API_KEY")
    dify_api_key: str = Field(default="", alias="DIFY_API_KEY")
    harness_secret_encryption_key: str = Field(
        default="",
        alias="HARNESS_SECRET_ENCRYPTION_KEY",
        repr=False,
    )
    harness_secret_encryption_key_id: str = Field(
        default="local-v1",
        alias="HARNESS_SECRET_ENCRYPTION_KEY_ID",
    )
    legacy_env_secret_fallback_enabled: bool = Field(
        default=True,
        alias="LEGACY_ENV_SECRET_FALLBACK_ENABLED",
    )
    docker_host: str = Field(default="unix:///var/run/docker.sock", alias="DOCKER_HOST")
    prometheus_base_url: AnyHttpUrl = Field(
        default="http://localhost:9091",
        alias="PROMETHEUS_BASE_URL",
    )
    grafana_base_url: AnyHttpUrl = Field(
        default="http://localhost:3001",
        alias="GRAFANA_BASE_URL",
    )
    grafana_username: str = Field(default="admin", alias="GRAFANA_USERNAME")
    grafana_password: str = Field(default="admin", alias="GRAFANA_PASSWORD")
    loki_base_url: AnyHttpUrl = Field(default="http://localhost:3100", alias="LOKI_BASE_URL")
    otel_collector_http_url: AnyHttpUrl = Field(
        default="http://localhost:4318",
        alias="OTEL_COLLECTOR_HTTP_URL",
    )
    otel_exporter_otlp_endpoint: str = Field(
        default="",
        alias="OTEL_EXPORTER_OTLP_ENDPOINT",
    )
    tempo_base_url: AnyHttpUrl = Field(default="http://localhost:3200", alias="TEMPO_BASE_URL")
    observability_export_dir: str = Field(
        default="/tmp/agent-harness/exports",
        alias="OBSERVABILITY_EXPORT_DIR",
    )
    auth_jwt_secret: str = Field(default="", alias="AUTH_JWT_SECRET", repr=False)
    local_desktop_bootstrap_token: str = Field(
        default="",
        alias="LOCAL_DESKTOP_BOOTSTRAP_TOKEN",
        repr=False,
    )
    local_web_bootstrap_ttl_seconds: int = Field(
        default=60,
        ge=1,
        le=300,
        alias="LOCAL_WEB_BOOTSTRAP_TTL_SECONDS",
    )
    persistent_secret_storage_available: bool = Field(
        default=True,
        alias="PERSISTENT_SECRET_STORAGE_AVAILABLE",
    )
    auth_public_registration_enabled: bool | None = Field(
        default=None,
        alias="AUTH_PUBLIC_REGISTRATION_ENABLED",
    )
    auth_access_token_minutes: int = Field(default=60, alias="AUTH_ACCESS_TOKEN_MINUTES")
    auth_refresh_token_days: int = Field(default=30, alias="AUTH_REFRESH_TOKEN_DAYS")
    saml_rate_limit_max_requests: int = Field(default=20, alias="SAML_RATE_LIMIT_MAX_REQUESTS")
    saml_rate_limit_window_seconds: int = Field(default=60, alias="SAML_RATE_LIMIT_WINDOW_SECONDS")
    harness_initial_admin_email: str = Field(default="", alias="HARNESS_INITIAL_ADMIN_EMAIL")
    harness_initial_admin_password: str = Field(default="", alias="HARNESS_INITIAL_ADMIN_PASSWORD")
    context_manifest_retention_days: int = Field(
        default=90,
        alias="CONTEXT_MANIFEST_RETENTION_DAYS",
    )
    feature_flags: str = Field(
        default=(
            "trusted_url_install,file_upload_install,dify_connector,file_knowledge_upload,"
            "workspace_auto_orchestration,token_estimated_baseline,"
            "langgraph_workflow_import_enabled,langchain_adapter_enabled"
        ),
        alias="FEATURE_FLAGS",
    )
    capability_trusted_hosts: str = Field(
        default="github.com,raw.githubusercontent.com,example.com",
        alias="CAPABILITY_TRUSTED_HOSTS",
    )
    mcp_remote_allowed_hosts: str = Field(default="", alias="MCP_REMOTE_ALLOWED_HOSTS")
    local_agent_npx_package: str = Field(default="", alias="LOCAL_AGENT_NPX_PACKAGE")
    local_agent_npx_registry: str = Field(
        default="https://registry.npmmirror.com",
        alias="LOCAL_AGENT_NPX_REGISTRY",
    )

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=(".env", "services/api-server/.env"),
        extra="ignore",
    )

    @field_validator("ai_provider_protocol")
    @classmethod
    def validate_ai_provider_protocol(cls, value: str) -> str:
        if value.strip() != "chat_completions":
            raise ValueError("AI_PROVIDER_PROTOCOL must be chat_completions")
        return "chat_completions"

    @field_validator("runtime_profile")
    @classmethod
    def validate_runtime_profile(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"server", "local"}:
            raise ValueError("RUNTIME_PROFILE must be server or local")
        return normalized

    @field_validator("ai_provider_base_url")
    @classmethod
    def validate_ai_provider_base_url(cls, value: str) -> str:
        return _validate_ai_provider_base_url(value)

    @field_validator("ai_provider_model")
    @classmethod
    def validate_ai_provider_model(cls, value: str) -> str:
        return _validate_ai_provider_model(value)

    @field_validator("ai_provider_models", mode="before")
    @classmethod
    def parse_ai_provider_models(cls, value: str | tuple[str, ...] | list[str]) -> tuple[str, ...]:
        entries = value.split(",") if isinstance(value, str) else value
        if not isinstance(entries, (tuple, list)):
            raise ValueError("AI_PROVIDER_MODELS must be a comma-separated model list")
        models: list[str] = []
        for entry in entries:
            model = _validate_ai_provider_model(str(entry))
            if model not in models:
                models.append(model)
        if not models:
            raise ValueError("AI_PROVIDER_MODELS must include at least one model")
        return tuple(models)

    @field_validator("ai_provider_name")
    @classmethod
    def validate_ai_provider_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > 80 or any(
            ord(char) < 32 or ord(char) == 127 for char in normalized
        ):
            raise ValueError("AI_PROVIDER_NAME must be 1-80 printable characters")
        return normalized

    @model_validator(mode="after")
    def validate_ai_provider_default_model(self) -> "Settings":
        if self.ai_provider_model not in self.ai_provider_models:
            raise ValueError("AI_PROVIDER_MODEL must be included in AI_PROVIDER_MODELS")
        if self.runtime_profile == "local":
            if self.runtime_data_dir is None:
                raise ValueError("RUNTIME_DATA_DIR is required for the local runtime profile")
            if not self.database_url.startswith("sqlite"):
                raise ValueError("The local runtime profile requires a SQLite database URL")
            parsed_api_url = urlsplit(str(self.api_base_url))
            if parsed_api_url.hostname is None or not _is_loopback_host(parsed_api_url.hostname):
                raise ValueError("The local runtime profile requires a loopback API base URL")
        return self


@lru_cache
def get_settings() -> Settings:
    return _runtime_settings_override or Settings()


_runtime_settings_override: Settings | None = None


def install_runtime_settings(settings: Settings) -> None:
    """Install settings constructed from a trusted in-process bootstrap channel."""
    global _runtime_settings_override
    _runtime_settings_override = settings
    get_settings.cache_clear()


def clear_runtime_settings() -> None:
    """Clear an in-process bootstrap override, primarily for isolated tests."""
    global _runtime_settings_override
    _runtime_settings_override = None
    get_settings.cache_clear()


def enabled_feature_flags(settings: Settings | None = None) -> set[str]:
    source = (settings or get_settings()).feature_flags
    return {flag.strip() for flag in source.split(",") if flag.strip()}


def feature_enabled(name: str, settings: Settings | None = None) -> bool:
    return name in enabled_feature_flags(settings)


def public_registration_enabled(settings: Settings | None = None) -> bool:
    current = settings or get_settings()
    if current.runtime_profile == "local":
        return False
    if current.auth_public_registration_enabled is not None:
        return current.auth_public_registration_enabled
    return current.app_env.strip().lower() in {"development", "test"}


def validate_auth_jwt_secret(settings: Settings) -> None:
    secret = settings.auth_jwt_secret.strip()
    if not secret:
        raise RuntimeError(
            "AUTH_JWT_SECRET is required. Generate one with `openssl rand -hex 32`; "
            f"see {AUTH_SECRET_DOCS_URL}."
        )
    if secret == AUTH_JWT_SECRET_PLACEHOLDER:
        raise RuntimeError(
            "AUTH_JWT_SECRET still uses the example placeholder. Generate one with "
            f"`openssl rand -hex 32`; see {AUTH_SECRET_DOCS_URL}."
        )
    if len(secret) < 32:
        raise RuntimeError(
            "AUTH_JWT_SECRET must be at least 32 characters. Generate one with "
            f"`openssl rand -hex 32`; see {AUTH_SECRET_DOCS_URL}."
        )
    if settings.app_env.strip().lower() == "production" and secret.startswith("dev-only-"):
        raise RuntimeError(
            "AUTH_JWT_SECRET must not use a dev-only value in production. Generate one with "
            f"`openssl rand -hex 32`; see {AUTH_SECRET_DOCS_URL}."
        )


def validate_secret_encryption_key(settings: Settings) -> None:
    if settings.app_env.strip().lower() != "production":
        return
    secret = settings.harness_secret_encryption_key.strip()
    if not secret:
        raise RuntimeError(
            "HARNESS_SECRET_ENCRYPTION_KEY is required in production. Generate it with "
            f"`python3 scripts/generate-runtime-secrets.py`; see {AUTH_SECRET_DOCS_URL}."
        )
    if secret == HARNESS_SECRET_ENCRYPTION_KEY_PLACEHOLDER:
        raise RuntimeError(
            "HARNESS_SECRET_ENCRYPTION_KEY still uses the example placeholder. Generate it with "
            f"`python3 scripts/generate-runtime-secrets.py`; see {AUTH_SECRET_DOCS_URL}."
        )
    if len(secret) < 32:
        raise RuntimeError(
            "HARNESS_SECRET_ENCRYPTION_KEY must be at least 32 characters. Generate it with "
            f"`python3 scripts/generate-runtime-secrets.py`; see {AUTH_SECRET_DOCS_URL}."
        )
    if secret.startswith("dev-only-"):
        raise RuntimeError(
            "HARNESS_SECRET_ENCRYPTION_KEY must not use a dev-only value in production. "
            "Generate it with `python3 scripts/generate-runtime-secrets.py`; "
            f"see {AUTH_SECRET_DOCS_URL}."
        )


def validate_ai_provider_api_key(settings: Settings) -> None:
    if settings.runtime_profile == "local":
        return
    if settings.app_env.strip().lower() != "production":
        return
    secret = settings.ai_provider_api_key.strip()
    if not secret:
        raise RuntimeError(
            "AI_PROVIDER_API_KEY is required in production for the platform-managed model provider"
        )
    if secret == "replace-me":
        raise RuntimeError("AI_PROVIDER_API_KEY must not use the example placeholder in production")


def validate_startup_settings(settings: Settings | None = None) -> None:
    current = settings or get_settings()
    validate_auth_jwt_secret(current)
    validate_secret_encryption_key(current)
    validate_ai_provider_api_key(current)


def _is_loopback_host(hostname: str) -> bool:
    try:
        return ip_address(hostname).is_loopback
    except ValueError:
        return hostname.lower() == "localhost"
