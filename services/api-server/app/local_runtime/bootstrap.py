from __future__ import annotations

import json
import os
import re
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, SecretStr, field_validator

from app.core.config import Settings, install_runtime_settings

MAX_BOOTSTRAP_BYTES = 64 * 1024
DEFAULT_MODEL_BASE_URL = "https://chybenzun.top/v1"
DEFAULT_MODEL_NAME = "deepseek-v4-flash"
MODEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")


def validate_model_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    if len(normalized) > 2048:
        raise ValueError("model base URL must not exceed 2048 characters")
    parsed = urlsplit(normalized)
    try:
        _port = parsed.port
    except ValueError as exc:
        raise ValueError("model base URL has an invalid port") from exc
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise ValueError("model base URL must use HTTPS or loopback HTTP")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("model base URL must not include credentials, query, or fragment")
    if parsed.scheme == "http":
        try:
            is_loopback = ip_address(parsed.hostname).is_loopback
        except ValueError:
            is_loopback = parsed.hostname.lower() == "localhost"
        if not is_loopback:
            raise ValueError("model base URL only permits HTTP for loopback hosts")
    return normalized


def validate_model_id(value: str) -> str:
    normalized = value.strip()
    if not MODEL_ID_PATTERN.fullmatch(normalized):
        raise ValueError("model ID must be 1-160 safe identifier characters")
    return normalized


class LocalRuntimeBootstrap(BaseModel):
    """Secrets and paths delivered by Electron over a private inherited pipe."""

    runtime_data_dir: Path
    session_signing_secret: SecretStr = Field(min_length=32)
    vault_encryption_secret: SecretStr = Field(min_length=32)
    desktop_bootstrap_token: SecretStr = Field(min_length=32)
    model_api_key: SecretStr = Field(default=SecretStr(""))
    model_base_url: str = DEFAULT_MODEL_BASE_URL
    model_name: str = DEFAULT_MODEL_NAME
    persistent_secret_storage: bool = True

    @field_validator("runtime_data_dir")
    @classmethod
    def validate_runtime_data_dir(cls, value: Path) -> Path:
        resolved = value.expanduser().resolve()
        if not resolved.is_absolute():
            raise ValueError("runtime_data_dir must be absolute")
        return resolved

    @field_validator("model_base_url")
    @classmethod
    def validate_bootstrap_model_base_url(cls, value: str) -> str:
        return validate_model_base_url(value)

    @field_validator("model_name")
    @classmethod
    def validate_bootstrap_model_name(cls, value: str) -> str:
        return validate_model_id(value)

    def to_settings(self) -> Settings:
        database_path = self.runtime_data_dir / "harness.sqlite3"
        model_key = self.model_api_key.get_secret_value()
        return Settings(
            RUNTIME_PROFILE="local",
            RUNTIME_DATA_DIR=self.runtime_data_dir,
            APP_ENV="production",
            APP_BASE_URL="http://127.0.0.1:8000",
            CONSOLE_BASE_URL="http://127.0.0.1:8000",
            API_BASE_URL="http://127.0.0.1:8000",
            DATABASE_URL=f"sqlite+pysqlite:///{database_path}",
            AUTH_JWT_SECRET=self.session_signing_secret.get_secret_value(),
            HARNESS_SECRET_ENCRYPTION_KEY=self.vault_encryption_secret.get_secret_value(),
            LOCAL_DESKTOP_BOOTSTRAP_TOKEN=self.desktop_bootstrap_token.get_secret_value(),
            AI_PROVIDER_API_KEY=model_key,
            AI_PROVIDER_BASE_URL=self.model_base_url,
            MODEL_GATEWAY_BASE_URL=self.model_base_url,
            MODEL_GATEWAY_API_KEY=model_key,
            AI_PROVIDER_MODEL=self.model_name,
            AI_PROVIDER_MODELS=(self.model_name,),
            AUTH_PUBLIC_REGISTRATION_ENABLED=False,
            PERSISTENT_SECRET_STORAGE_AVAILABLE=self.persistent_secret_storage,
        )

    def install(self) -> Settings:
        settings = self.to_settings()
        install_runtime_settings(settings)
        return settings


def read_bootstrap_from_fd(fd: int = 3) -> LocalRuntimeBootstrap:
    """Read one bootstrap document from an inherited descriptor, never argv or env."""
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = os.read(fd, min(8192, MAX_BOOTSTRAP_BYTES + 1 - size))
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
        if size > MAX_BOOTSTRAP_BYTES:
            raise ValueError("local runtime bootstrap payload exceeds 64 KiB")
    if not chunks:
        raise ValueError("local runtime bootstrap pipe was empty")
    try:
        payload = json.loads(b"".join(chunks))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("local runtime bootstrap payload is not valid JSON") from exc
    return LocalRuntimeBootstrap.model_validate(payload)


def install_bootstrap_from_fd(fd: int = 3) -> Settings:
    """Install settings before importing the FastAPI application module."""
    return read_bootstrap_from_fd(fd).install()
