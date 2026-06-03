from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_API_URL = "http://127.0.0.1:8000"
CONFIG_DIR_NAME = ".hao"
CONFIG_FILE_NAME = "config.toml"
SESSION_DB_NAME = "hao.db"


@dataclass(frozen=True)
class HaoConfig:
    api_url: str = DEFAULT_API_URL
    token: str = ""
    home: Path = Path.home() / CONFIG_DIR_NAME

    @property
    def config_path(self) -> Path:
        return self.home / CONFIG_FILE_NAME

    @property
    def session_db_path(self) -> Path:
        return self.home / SESSION_DB_NAME

    @property
    def sessions_dir(self) -> Path:
        return self.home / "sessions"


def hao_home(env: Mapping[str, str] | None = None) -> Path:
    env = env or os.environ
    raw = env.get("HAO_HOME", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / CONFIG_DIR_NAME


def load_persisted_config(env: Mapping[str, str] | None = None) -> HaoConfig:
    env = env or os.environ
    home = hao_home(env)
    config_path = home / CONFIG_FILE_NAME
    data: dict[str, str] = {}
    if config_path.exists():
        with config_path.open("rb") as handle:
            loaded = tomllib.load(handle)
        api = loaded.get("api", {})
        if isinstance(api, dict):
            data["api_url"] = str(api.get("url", "")).strip()
            data["token"] = str(api.get("token", "")).strip()
    api_url = data.get("api_url", "").strip() or DEFAULT_API_URL
    token = data.get("token", "").strip()
    return HaoConfig(api_url=api_url, token=token, home=home)


def load_config(env: Mapping[str, str] | None = None) -> HaoConfig:
    env = env or os.environ
    saved = load_persisted_config(env)
    api_url = env.get("HAO_API_URL", saved.api_url).strip() or DEFAULT_API_URL
    token = env.get("HAO_API_TOKEN", saved.token).strip()
    return HaoConfig(api_url=api_url, token=token, home=saved.home)


def save_auth(config: HaoConfig, *, api_url: str, token: str) -> None:
    config.home.mkdir(parents=True, exist_ok=True)
    payload = (
        "[api]\n"
        f"url = {api_url!r}\n"
        f"token = {token!r}\n"
    )
    config.config_path.write_text(payload, encoding="utf-8")


def clear_persisted_token(config: HaoConfig) -> bool:
    if not config.config_path.exists():
        return False
    saved = load_persisted_config({"HAO_HOME": str(config.home)})
    save_auth(config, api_url=saved.api_url, token="")
    return True


def format_status(config: HaoConfig) -> str:
    token_status = "set" if config.token.strip() else "missing"
    return (
        f"api_url={config.api_url}\n"
        f"token={token_status}\n"
        f"home={config.home}\n"
        f"session_db={config.session_db_path}\n"
    )
