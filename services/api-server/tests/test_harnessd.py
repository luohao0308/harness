from __future__ import annotations

import asyncio
import json
import logging
import socket
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.cli import harnessd
from app.local_runtime.bootstrap import LocalRuntimeBootstrap


def _bootstrap(tmp_path: Path, *, canary: str = "model-secret-canary-at-least-32-characters"):
    return LocalRuntimeBootstrap(
        runtime_data_dir=tmp_path,
        session_signing_secret="session-secret-at-least-32-characters-long",
        vault_encryption_secret="vault-secret-at-least-32-characters-long",
        desktop_bootstrap_token="desktop-token-at-least-32-characters-long",
        model_api_key=canary,
    )


def _route_paths(routes) -> set[str]:
    paths: set[str] = set()
    for route in routes:
        path = getattr(route, "path", None)
        if isinstance(path, str):
            paths.add(path)
        nested_routes = getattr(route, "routes", None)
        if nested_routes:
            paths.update(_route_paths(nested_routes))
    return paths


def test_bind_loopback_socket_uses_dynamic_port_and_ready_schema() -> None:
    listener = harnessd.bind_loopback_socket(0)
    try:
        payload = harnessd.build_ready_handshake(listener)
    finally:
        listener.close()

    assert payload == {
        "protocol_version": 1,
        "runtime_version": "0.1.0",
        "origin": payload["origin"],
        "health_path": "/api/health/readiness",
        "desktop_session_path": "/api/local-runtime/desktop-session",
        "renderer_path": "/desktop/",
    }
    assert payload["origin"].startswith("http://127.0.0.1:")
    assert int(payload["origin"].rsplit(":", 1)[1]) > 0


def test_runtime_logging_writes_structured_redacted_stderr_and_file(
    tmp_path: Path,
    capfd: pytest.CaptureFixture[str],
) -> None:
    canary = "model-secret-canary-at-least-32-characters"
    log_path = harnessd.configure_runtime_logging(tmp_path, _bootstrap(tmp_path, canary=canary))

    logging.getLogger("test.harnessd").error("credential=%s", canary)
    stderr = capfd.readouterr().err
    file_payload = log_path.read_text(encoding="utf-8")

    assert canary not in stderr
    assert canary not in file_payload
    assert "[REDACTED]" in stderr
    assert "[REDACTED]" in file_payload
    assert json.loads(stderr)["service"] == "harnessd"
    assert json.loads(file_payload)["level"] == "ERROR"
    logging.getLogger().handlers.clear()


def test_run_migrations_uses_packaged_alembic_assets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, Path, object]] = []
    paths = harnessd.runtime_paths(tmp_path)
    runtime_lock = harnessd.SQLiteRuntimeLock(paths.lock_path).acquire()

    def fake_migrate(candidate_paths, *, alembic_ini, runtime_lock) -> Path:
        calls.append((str(alembic_ini), candidate_paths.runtime_dir, runtime_lock))
        return candidate_paths.default_database_path

    monkeypatch.setattr(harnessd, "migrate_sqlite_candidate", fake_migrate)
    try:
        harnessd.run_migrations(paths, runtime_lock)
    finally:
        runtime_lock.release()

    assert calls == [
        (
            str(Path(harnessd.__file__).resolve().parents[2] / "alembic.ini"),
            tmp_path,
            runtime_lock,
        )
    ]


def test_static_renderer_serves_assets_and_history_without_swallowing_api(tmp_path: Path) -> None:
    renderer = tmp_path / "renderer"
    assets = renderer / "assets"
    assets.mkdir(parents=True)
    (renderer / "index.html").write_text(
        '<main>Harness</main><script src="https://attacker.invalid/payload.js"></script>',
        encoding="utf-8",
    )
    (assets / "app.js").write_text("window.HARNESS = true", encoding="utf-8")
    app = FastAPI()
    harnessd.attach_static_renderer(app, renderer)
    client = TestClient(app)

    history = client.get("/desktop/agents/default/workspace")
    asset = client.get("/desktop/assets/app.js")

    assert "<main>Harness</main>" in history.text
    assert asset.text == "window.HARNESS = true"
    for response in (history, asset):
        csp = response.headers["content-security-policy"]
        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp
        assert "attacker.invalid" not in csp
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert "camera=()" in response.headers["permissions-policy"]
    assert client.get("/api/missing").status_code == 404
    assert client.get("/health").status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "/api/saml/login",
        "/api/auth/login",
        "/api/auth/register",
        "/api/auth/oauth/github",
    ],
)
def test_local_app_disables_server_login_surfaces(path: str) -> None:
    assert harnessd._is_server_login_path(path)


def test_local_app_keeps_desktop_session_surface() -> None:
    assert not harnessd._is_server_login_path("/api/local-runtime/desktop-session")


def test_local_app_includes_core_desktop_route_inventory() -> None:
    app = harnessd.build_local_runtime_app()
    startup_paths = _route_paths(app.routes)

    assert "/api/health/readiness" in startup_paths
    assert "/api/local-runtime/desktop-session" in startup_paths
    assert "/api/agents" not in startup_paths

    paths = app.openapi()["paths"]

    assert {
        "/api/agents/{agent_id}/runs/chat/stream",
        "/api/agents/{agent_id}/runs/plan/stream",
        "/api/agents/runs/{run_id}/workspace",
        "/api/tasks",
        "/api/tasks/{task_id}/events",
        "/api/tasks/{task_id}/tool-approvals/{approval_id}/approve",
        "/api/teams",
        "/api/terminal/tokens",
        "/api/tools/registry",
        "/api/subagents",
        "/api/evals/datasets",
        "/api/observability/summary",
        "/api/health/readiness",
    } <= paths.keys()

    route_count = len(app.routes)
    with ThreadPoolExecutor(max_workers=4) as pool:
        schemas = list(pool.map(lambda _index: app.openapi(), range(8)))
    assert all(schema["paths"].keys() == paths.keys() for schema in schemas)
    assert len(app.routes) == route_count


def test_ready_server_emits_handshake_once_after_successful_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emitted: list[dict] = []

    async def fake_startup(self, sockets=None) -> None:
        self.started = True

    monkeypatch.setattr(harnessd.uvicorn.Server, "startup", fake_startup)
    monkeypatch.setattr(harnessd, "emit_ready_handshake", emitted.append)
    handshake = {"protocol_version": 1, "origin": "http://127.0.0.1:12345"}
    server = harnessd.ReadyServer(harnessd.uvicorn.Config(lambda *_args: None), handshake)

    asyncio.run(server.startup())
    asyncio.run(server.startup())

    assert emitted == [handshake]


def test_main_installs_dynamic_origin_before_migration_and_serve(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bootstrap = _bootstrap(tmp_path)
    events: list[str] = []
    installed = []

    monkeypatch.setattr(harnessd, "read_bootstrap_from_fd", lambda _fd: bootstrap)
    monkeypatch.setattr(harnessd, "configure_runtime_logging", lambda *_args: tmp_path / "log")
    def fake_migration(paths, _runtime_lock) -> None:
        events.append("migrate")
        candidate = paths.runtime_dir / "harness-candidate-test.sqlite3"
        candidate.touch()
        paths.switch_active_database(
            candidate,
            previous_database=paths.default_database_path,
            alembic_revision="test-head",
        )

    monkeypatch.setattr(harnessd, "run_migrations", fake_migration)
    monkeypatch.setattr(
        harnessd,
        "install_runtime_settings",
        lambda settings: installed.append(settings),
    )

    async def fake_serve(
        listener: socket.socket,
        static_dir: Path | None,
        runtime_bootstrap: LocalRuntimeBootstrap,
    ) -> None:
        events.append("serve")

    monkeypatch.setattr(harnessd, "serve", fake_serve)

    assert harnessd.main(["--port", "0"]) == 0
    assert events == ["migrate", "serve"]
    assert str(installed[-1].api_base_url).startswith("http://127.0.0.1:")
    assert installed[-1].runtime_profile == "local"
    assert installed[-1].database_url.endswith("/harness-candidate-test.sqlite3")
