from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=(".env", "services/api-server/.env"),
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
