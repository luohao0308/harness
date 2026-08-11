import asyncio
import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.services.terminal_capability_store import (
    InMemoryTerminalCapabilityStore,
    TerminalCapabilityStoreUnavailable,
    get_terminal_capability_store,
    reset_terminal_capability_store_for_tests,
    set_terminal_capability_store_for_tests,
)


class FakeTerminalSession:
    last_cwd = None
    last_env = None

    def __init__(self, terminal_id, websocket, cwd=None, env=None):
        self.terminal_id = terminal_id
        self.websocket = websocket
        self.cwd = cwd
        self.env = env or {}
        self.closed = False
        self.resize_calls = []
        FakeTerminalSession.last_cwd = cwd
        FakeTerminalSession.last_env = env or {}

    async def start(self):
        return None

    async def write_input(self, data):
        await self.websocket.send_json(
            {
                "type": "output",
                "terminalId": self.terminal_id,
                "data": data,
            }
        )

    def resize(self, rows, cols):
        self.resize_calls.append((rows, cols))

    async def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def reset_terminal_auth_state():
    import app.api.terminal as terminal_api

    set_terminal_capability_store_for_tests(
        InMemoryTerminalCapabilityStore(
            token_ttl_seconds=terminal_api._TERMINAL_TOKEN_TTL_SECONDS,
            max_sessions=terminal_api._MAX_TERMINAL_SESSIONS_PER_USER,
            lease_seconds=terminal_api._TERMINAL_SESSION_LEASE_SECONDS,
        )
    )
    yield
    reset_terminal_capability_store_for_tests()


def _create_terminal_token(client: TestClient, terminal_id: str = "term-2") -> str:
    response = client.post(
        "/api/terminal/tokens",
        json={"terminal_id": terminal_id},
        headers={"Authorization": "Bearer dev-engineer-token"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["terminal_id"] == terminal_id
    assert payload["expires_at"]
    return payload["token"]


def test_terminal_shell_command_skips_user_startup_scripts():
    import app.api.terminal as terminal_api

    assert terminal_api._interactive_shell_command("/bin/zsh") == ["/bin/zsh", "-f", "-i"]
    assert terminal_api._interactive_shell_command("/bin/bash") == [
        "/bin/bash",
        "--noprofile",
        "--norc",
        "-i",
    ]
    assert terminal_api._interactive_shell_command("/bin/sh") == ["/bin/sh", "-i"]


def test_real_terminal_ctrl_c_interrupts_foreground_process_and_shell_survives(tmp_path):
    import app.api.terminal as terminal_api

    class RecordingWebSocket:
        def __init__(self):
            self.events = []

        async def send_json(self, payload):
            self.events.append(payload)

        def output(self):
            return "".join(
                event.get("data", "")
                for event in self.events
                if event.get("type") == "output"
            )

    async def exercise_terminal():
        websocket = RecordingWebSocket()
        cwd = str(tmp_path.resolve())
        session = terminal_api.TerminalSession(
            terminal_id="interrupt-probe",
            websocket=websocket,
            cwd=cwd,
            env=terminal_api._terminal_env(cwd),
        )
        try:
            await session.start()
            await _wait_until(lambda: session.master_fd is not None, timeout=1)
            await session.write_input("sleep 20\r")
            await _wait_until(lambda: "sleep 20" in websocket.output(), timeout=2)
            await asyncio.sleep(0.2)

            interrupted_at = time.monotonic()
            await session.write_input("\x03")
            await session.write_input("printf 'TERMINAL_SURVIVED\\n'\r")
            await _wait_until(
                lambda: "TERMINAL_SURVIVED\r\n" in websocket.output(),
                timeout=3,
            )

            assert time.monotonic() - interrupted_at < 3
            assert session.process is not None
            assert session.process.poll() is None
        finally:
            await session.close()

    async def _wait_until(predicate, *, timeout):
        deadline = asyncio.get_running_loop().time() + timeout
        while not predicate():
            if asyncio.get_running_loop().time() >= deadline:
                raise AssertionError("terminal output did not arrive before timeout")
            await asyncio.sleep(0.02)

    asyncio.run(exercise_terminal())


def test_terminal_websocket_accepts_local_origin_and_echoes_protocol(monkeypatch):
    import app.api.terminal as terminal_api

    monkeypatch.setattr(terminal_api, "TerminalSession", FakeTerminalSession)
    client = TestClient(app)
    token = _create_terminal_token(client, "term-2")

    with client.websocket_connect(
        f"/ws/terminal?terminal_id=term-2&terminal_token={token}",
        headers={"origin": "http://127.0.0.1:5173"},
    ) as websocket:
        websocket.send_json({"type": "input", "terminalId": "term-2", "data": "echo smoke\r"})

        assert websocket.receive_json() == {
            "type": "output",
            "terminalId": "term-2",
            "data": "echo smoke\r",
        }


def test_terminal_websocket_accepts_trusted_desktop_origin(monkeypatch):
    import app.api.terminal as terminal_api

    monkeypatch.setattr(terminal_api, "TerminalSession", FakeTerminalSession)
    client = TestClient(app)
    token = _create_terminal_token(client, "desktop-term")

    with client.websocket_connect(
        f"/ws/terminal?terminal_id=desktop-term&terminal_token={token}",
        headers={"origin": "harness-app://renderer"},
    ) as websocket:
        websocket.send_json(
            {"type": "input", "terminalId": "desktop-term", "data": "echo desktop\r"}
        )
        assert websocket.receive_json()["data"] == "echo desktop\r"


def test_terminal_websocket_rejects_non_local_origin():
    client = TestClient(app)
    token = _create_terminal_token(client, "term-1")

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            f"/ws/terminal?terminal_id=term-1&terminal_token={token}",
            headers={"origin": "https://example.com"},
        ):
            pass


def test_terminal_token_endpoint_requires_current_principal():
    client = TestClient(app)

    response = client.post("/api/terminal/tokens", json={"terminal_id": "term-1"})

    assert response.status_code == 401


def test_terminal_token_endpoint_fails_closed_when_capability_store_is_unavailable():
    class UnavailableStore:
        def issue_token(self, **_kwargs):
            raise TerminalCapabilityStoreUnavailable

    set_terminal_capability_store_for_tests(UnavailableStore())
    client = TestClient(app)

    response = client.post(
        "/api/terminal/tokens",
        json={"terminal_id": "term-1"},
        headers={"Authorization": "Bearer dev-engineer-token"},
    )

    assert response.status_code == 503


def test_terminal_websocket_rejects_missing_token():
    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/ws/terminal?terminal_id=term-1",
            headers={"origin": "http://127.0.0.1:5173"},
        ):
            pass


def test_terminal_websocket_rejects_reused_token(monkeypatch):
    import app.api.terminal as terminal_api

    monkeypatch.setattr(terminal_api, "TerminalSession", FakeTerminalSession)
    client = TestClient(app)
    token = _create_terminal_token(client, "term-1")

    with client.websocket_connect(
        f"/ws/terminal?terminal_id=term-1&terminal_token={token}",
        headers={"origin": "http://127.0.0.1:5173"},
    ):
        pass

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            f"/ws/terminal?terminal_id=term-1&terminal_token={token}",
            headers={"origin": "http://127.0.0.1:5173"},
        ):
            pass


def test_terminal_websocket_rejects_expired_token(monkeypatch):
    import app.services.terminal_capability_store as capability_store

    now = 1000.0
    monkeypatch.setattr(capability_store.time, "time", lambda: now)
    client = TestClient(app)
    token = _create_terminal_token(client, "term-1")
    now = 1040.0

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            f"/ws/terminal?terminal_id=term-1&terminal_token={token}",
            headers={"origin": "http://127.0.0.1:5173"},
        ):
            pass


def test_terminal_websocket_rejects_token_for_different_terminal():
    client = TestClient(app)
    token = _create_terminal_token(client, "term-1")

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            f"/ws/terminal?terminal_id=term-2&terminal_token={token}",
            headers={"origin": "http://127.0.0.1:5173"},
        ):
            pass


def test_terminal_session_cap_blocks_token_issue():
    import app.api.terminal as terminal_api

    client = TestClient(app)
    store = get_terminal_capability_store(
        token_ttl_seconds=terminal_api._TERMINAL_TOKEN_TTL_SECONDS,
        max_sessions=terminal_api._MAX_TERMINAL_SESSIONS_PER_USER,
        lease_seconds=terminal_api._TERMINAL_SESSION_LEASE_SECONDS,
    )
    for index in range(terminal_api._MAX_TERMINAL_SESSIONS_PER_USER):
        record = store.issue_token(
            terminal_id=f"reserved-{index}",
            user_id="dev-engineer",
            organization_id="dev-org",
        )
        assert store.consume_and_reserve(
            token=record.token,
            terminal_id=record.terminal_id,
        )

    response = client.post(
        "/api/terminal/tokens",
        json={"terminal_id": "term-1"},
        headers={"Authorization": "Bearer dev-engineer-token"},
    )

    assert response.status_code == 429


def test_terminal_session_uses_explicit_cwd_and_scrubbed_env(monkeypatch, tmp_path):
    import app.api.terminal as terminal_api

    monkeypatch.setattr(terminal_api, "TerminalSession", FakeTerminalSession)
    monkeypatch.setenv("HARNESS_TERMINAL_CWD", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    monkeypatch.setenv("HARNESS_AUTH_TOKEN", "secret-value")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    client = TestClient(app)
    token = _create_terminal_token(client, "term-1")

    with client.websocket_connect(
        f"/ws/terminal?terminal_id=term-1&terminal_token={token}",
        headers={"origin": "http://127.0.0.1:5173"},
    ):
        pass

    assert FakeTerminalSession.last_cwd == str(tmp_path.resolve())
    assert FakeTerminalSession.last_env["PATH"] == "/usr/bin:/bin"
    assert FakeTerminalSession.last_env["PWD"] == str(tmp_path.resolve())
    assert "OPENAI_API_KEY" not in FakeTerminalSession.last_env
    assert "HARNESS_AUTH_TOKEN" not in FakeTerminalSession.last_env
