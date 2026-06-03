from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

AUTH_JWT_SECRET_PLACEHOLDER = "replace-with-openssl-rand-hex-32"
HARNESS_SECRET_ENCRYPTION_KEY_PLACEHOLDER = "replace-with-generated-fernet-key"
AUTH_SECRET_DOCS_URL = "docs/runbooks/first-run-admin.md"


class Settings(BaseSettings):
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
    model_gateway_api_key: str = Field(default="replace-me", alias="MODEL_GATEWAY_API_KEY")
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    tavily_api_key: str = Field(default="", alias="TAVILY_API_KEY")
    dify_api_key: str = Field(default="", alias="DIFY_API_KEY")
    harness_secret_encryption_key: str = Field(default="", alias="HARNESS_SECRET_ENCRYPTION_KEY")
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
    auth_jwt_secret: str = Field(default="", alias="AUTH_JWT_SECRET")
    auth_public_registration_enabled: bool | None = Field(
        default=None,
        alias="AUTH_PUBLIC_REGISTRATION_ENABLED",
    )
    auth_access_token_minutes: int = Field(default=60, alias="AUTH_ACCESS_TOKEN_MINUTES")
    auth_refresh_token_days: int = Field(default=30, alias="AUTH_REFRESH_TOKEN_DAYS")
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

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=(".env", "services/api-server/.env"),
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def enabled_feature_flags(settings: Settings | None = None) -> set[str]:
    source = (settings or get_settings()).feature_flags
    return {flag.strip() for flag in source.split(",") if flag.strip()}


def feature_enabled(name: str, settings: Settings | None = None) -> bool:
    return name in enabled_feature_flags(settings)


def public_registration_enabled(settings: Settings | None = None) -> bool:
    current = settings or get_settings()
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


def validate_startup_settings(settings: Settings | None = None) -> None:
    current = settings or get_settings()
    validate_auth_jwt_secret(current)
    validate_secret_encryption_key(current)
