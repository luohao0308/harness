from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.bootstrap.local_owner import bootstrap_local_owner
from app.core.config import get_settings
from app.local_runtime.workspace_authorization import WORKSPACE_AUTHORIZATION_STORE
from app.main import app

AUTH_HEADERS = {"Authorization": "Bearer dev-engineer-token"}


def _local_settings(monkeypatch):
    settings = get_settings().model_copy(
        update={
            "runtime_profile": "local",
            "local_desktop_bootstrap_token": "desktop-bootstrap-token-at-least-32-characters",
        }
    )
    monkeypatch.setattr("app.local_runtime.api.get_settings", lambda: settings)
    monkeypatch.setattr("app.api.triggers.get_settings", lambda: settings)
    return settings


def _issue(
    root: Path,
    *,
    profile_id: str = "profile-a",
    user_id: str = "dev-engineer",
    organization_id: str = "dev-org",
) -> str:
    token, _expires_at = WORKSPACE_AUTHORIZATION_STORE.issue(
        signing_secret="desktop-bootstrap-token-at-least-32-characters",
        user_id=user_id,
        organization_id=organization_id,
        profile_id=profile_id,
        root_path=root.resolve(),
        label=root.name,
        ttl_seconds=300,
    )
    return token


def test_workspace_authorization_endpoint_returns_opaque_grant_without_path(
    tmp_path: Path,
    db_session: Session,
    monkeypatch,
) -> None:
    settings = _local_settings(monkeypatch)
    bootstrap_local_owner(db_session)
    root = tmp_path / "private-workspace"
    root.mkdir()
    client = TestClient(app, base_url="http://127.0.0.1:8000")

    response = client.post(
        "/api/local-runtime/workspace-authorization",
        headers={"X-Harness-Desktop-Bootstrap": settings.local_desktop_bootstrap_token},
        json={"profile_id": "profile-a", "root_path": str(root)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["label"] == "private-workspace"
    assert body["authorization"].startswith("hwa1_")
    assert str(root) not in response.text
    assert "root_path" not in body


def test_file_trigger_requires_matching_workspace_authorization(
    tmp_path: Path,
    db_session: Session,
    monkeypatch,
) -> None:
    _local_settings(monkeypatch)
    root = tmp_path / "workspace"
    root.mkdir()
    client = TestClient(app)

    missing = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={"type": "file", "config_json": {"pattern": "**/*.md"}},
    )
    forged = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={
            "type": "file",
            "config_json": {
                "workspace_authorization": "hwa1_forged.invalid",
                "pattern": "**/*.md",
            },
        },
    )
    wrong_user = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={
            "type": "file",
            "config_json": {
                "workspace_authorization": _issue(root, user_id="dev-admin"),
                "pattern": "**/*.md",
            },
        },
    )
    valid = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={
            "type": "file",
            "config_json": {
                "workspace_authorization": _issue(root),
                "pattern": "**/*.md",
            },
        },
    )

    assert missing.status_code == 422
    assert forged.status_code == 403
    assert wrong_user.status_code == 403
    assert valid.status_code == 201
    assert str(root) not in valid.text
    assert "workspace_authorization" not in valid.json()["trigger"]["config_json"]
    assert valid.json()["trigger"]["config_json"]["workspace_root_label"] == root.name


def test_git_trigger_authorizes_only_the_selected_top_level(
    tmp_path: Path,
    db_session: Session,
    monkeypatch,
) -> None:
    _local_settings(monkeypatch)
    repo = tmp_path / "repo"
    child = repo / "child"
    child.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True, shell=False)
    client = TestClient(app)

    child_response = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={
            "type": "git",
            "config_json": {"workspace_authorization": _issue(child)},
        },
    )
    repo_response = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={
            "type": "git",
            "config_json": {"workspace_authorization": _issue(repo)},
        },
    )

    assert child_response.status_code == 422
    assert repo_response.status_code == 201
    assert str(repo) not in repo_response.text
    assert repo_response.json()["trigger"]["config_json"]["repo_root_label"] == repo.name
