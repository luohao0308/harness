from __future__ import annotations

import asyncio
import os
import pty
import signal
import struct
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

from app.security.auth import Principal
from app.services.terminal_capability_store import (
    TerminalCapabilityStore,
    TerminalCapabilityStoreUnavailable,
    TerminalSessionLimitReached,
    TerminalSessionReservation,
    get_terminal_capability_store,
)

router = APIRouter(tags=["terminal"])

_LOCAL_ORIGIN_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"}
_TRUSTED_DESKTOP_ORIGINS = {"harness-app://renderer"}
_TERMINAL_TOKEN_TTL_SECONDS = 30
_MAX_TERMINAL_SESSIONS_PER_USER = 4
_TERMINAL_SESSION_LEASE_SECONDS = 90
_TERMINAL_SESSION_HEARTBEAT_SECONDS = 30
_SENSITIVE_ENV_MARKERS = (
    "API_KEY",
    "AUTH",
    "CREDENTIAL",
    "JWT",
    "KEY",
    "PASSWORD",
    "SECRET",
    "SESSION",
    "TOKEN",
)
_BASE_ENV_KEYS = {
    "COLORTERM",
    "HOME",
    "LANG",
    "LOGNAME",
    "PATH",
    "SHELL",
    "TERM",
    "USER",
}


class TerminalTokenRequest(BaseModel):
    terminal_id: str = Field(default="terminal", max_length=80)


class TerminalTokenResponse(BaseModel):
    token: str
    terminal_id: str
    expires_at: str


def _is_local_origin(origin: str | None) -> bool:
    if not origin:
        return False
    if origin in _TRUSTED_DESKTOP_ORIGINS:
        return True
    parsed = urlsplit(origin)
    host = parsed.hostname or parsed.netloc
    return host in _LOCAL_ORIGIN_HOSTS


def _is_local_client(websocket: WebSocket) -> bool:
    client = websocket.client
    if client is None:
        return False
    return client.host in _LOCAL_ORIGIN_HOSTS


def _safe_terminal_id(value: Any) -> str:
    terminal_id = str(value or "terminal").strip()
    if not terminal_id:
        return "terminal"
    return terminal_id[:80]


def _default_shell() -> str:
    configured = os.environ.get("SHELL")
    if configured and os.path.exists(configured):
        return configured
    for candidate in ("/bin/zsh", "/bin/bash", "/bin/sh"):
        if os.path.exists(candidate):
            return candidate
    return "/bin/sh"


def _interactive_shell_command(shell: str) -> list[str]:
    shell_name = Path(shell).name
    if shell_name == "zsh":
        return [shell, "-f", "-i"]
    if shell_name == "bash":
        return [shell, "--noprofile", "--norc", "-i"]
    return [shell, "-i"]


def _terminal_cwd() -> str:
    for raw_path in (
        os.environ.get("HARNESS_TERMINAL_CWD"),
        os.environ.get("HARNESS_WORKSPACE_ROOT"),
        str(Path(__file__).resolve().parents[4]),
        str(Path.home()),
    ):
        if not raw_path:
            continue
        path = Path(raw_path).expanduser()
        if path.exists() and path.is_dir():
            return str(path.resolve())
    return str(Path.home())


def _terminal_env(cwd: str) -> dict[str, str]:
    env: dict[str, str] = {}
    for key, value in os.environ.items():
        normalized = key.upper()
        if any(marker in normalized for marker in _SENSITIVE_ENV_MARKERS):
            continue
        if key in _BASE_ENV_KEYS or normalized.startswith("LC_"):
            env[key] = value
    env["TERM"] = env.get("TERM", "xterm-256color")
    env["SHELL"] = _default_shell()
    env["PWD"] = cwd
    return env


@router.post("/api/terminal/tokens", response_model=TerminalTokenResponse)
def create_terminal_token(
    payload: TerminalTokenRequest,
    principal: Principal,
) -> TerminalTokenResponse:
    terminal_id = _safe_terminal_id(payload.terminal_id)
    store = get_terminal_capability_store(
        token_ttl_seconds=_TERMINAL_TOKEN_TTL_SECONDS,
        max_sessions=_MAX_TERMINAL_SESSIONS_PER_USER,
        lease_seconds=_TERMINAL_SESSION_LEASE_SECONDS,
    )
    try:
        record = store.issue_token(
            terminal_id=terminal_id,
            user_id=principal.user_id,
            organization_id=principal.organization_id,
        )
    except TerminalSessionLimitReached as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many active terminal sessions",
        ) from exc
    except TerminalCapabilityStoreUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Terminal capability service is temporarily unavailable",
        ) from exc
    expires_at = datetime.fromtimestamp(record.expires_at, tz=UTC).isoformat()
    return TerminalTokenResponse(
        token=record.token,
        terminal_id=terminal_id,
        expires_at=expires_at,
    )


@dataclass
class _PtyChildProcess:
    pid: int
    returncode: int | None = None

    def poll(self) -> int | None:
        if self.returncode is not None:
            return self.returncode
        try:
            waited_pid, status_code = os.waitpid(self.pid, os.WNOHANG)
        except ChildProcessError:
            return self.returncode
        if waited_pid == 0:
            return None
        self.returncode = os.waitstatus_to_exitcode(status_code)
        return self.returncode


@dataclass
class TerminalSession:
    terminal_id: str
    websocket: WebSocket
    cwd: str
    env: dict[str, str]
    process: _PtyChildProcess | None = None
    master_fd: int | None = None
    wait_task: asyncio.Task[None] | None = None
    closed: bool = False

    async def start(self) -> None:
        if self.process is not None:
            return

        shell = _default_shell()
        child_pid, master_fd = pty.fork()
        if child_pid == 0:
            try:
                os.chdir(self.cwd)
                os.execve(shell, _interactive_shell_command(shell), self.env)
            except BaseException:
                os._exit(127)

        os.set_blocking(master_fd, False)
        self.process = _PtyChildProcess(child_pid)
        self.master_fd = master_fd
        loop = asyncio.get_running_loop()
        loop.add_reader(master_fd, self._read_ready)
        self.wait_task = asyncio.create_task(self._wait_for_exit())

    async def write_input(self, data: str) -> None:
        if self.master_fd is None:
            return
        payload = data.encode("utf-8", errors="replace")
        if payload:
            with suppress(BlockingIOError, OSError):
                os.write(self.master_fd, payload)

    def resize(self, rows: int | None, cols: int | None) -> None:
        if self.master_fd is None or not rows or not cols:
            return
        with suppress(OSError):
            import fcntl
            import termios

            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
            if self.process is not None and self.process.poll() is None:
                os.killpg(self.process.pid, signal.SIGWINCH)

    async def close(self) -> None:
        self.closed = True
        if self.master_fd is not None:
            with suppress(ValueError, OSError):
                asyncio.get_running_loop().remove_reader(self.master_fd)

        if self.process is not None and self.process.poll() is None:
            with suppress(ProcessLookupError):
                os.killpg(self.process.pid, signal.SIGTERM)
            deadline = asyncio.get_running_loop().time() + 1
            while self.process.poll() is None and asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(0.05)
            if self.process.poll() is None:
                with suppress(ProcessLookupError):
                    os.killpg(self.process.pid, signal.SIGKILL)
                while self.process.poll() is None:
                    await asyncio.sleep(0.05)

        if self.wait_task is not None:
            self.wait_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.wait_task
            self.wait_task = None

        if self.master_fd is not None:
            with suppress(OSError):
                os.close(self.master_fd)
            self.master_fd = None

    def _read_ready(self) -> None:
        if self.closed or self.master_fd is None:
            return
        try:
            while True:
                chunk = os.read(self.master_fd, 4096)
                if not chunk:
                    asyncio.create_task(self._send_exit())
                    break
                asyncio.create_task(self._send_output(chunk))
        except BlockingIOError:
            pass
        except OSError:
            asyncio.create_task(self._send_exit())

    async def _send_output(self, chunk: bytes) -> None:
        with suppress(RuntimeError, WebSocketDisconnect):
            await self.websocket.send_json(
                {
                    "type": "output",
                    "terminalId": self.terminal_id,
                    "data": chunk.decode("utf-8", errors="replace"),
                }
            )

    async def _wait_for_exit(self) -> None:
        while self.process is not None and self.process.poll() is None and not self.closed:
            await asyncio.sleep(0.1)
        if not self.closed:
            await self._send_exit()

    async def _send_exit(self) -> None:
        self.closed = True
        if self.master_fd is not None:
            with suppress(ValueError, OSError):
                asyncio.get_running_loop().remove_reader(self.master_fd)
        exit_code = self.process.poll() if self.process is not None else None
        with suppress(RuntimeError, WebSocketDisconnect):
            await self.websocket.send_json(
                {
                    "type": "exit",
                    "terminalId": self.terminal_id,
                    "exitCode": exit_code,
                }
            )


@router.websocket("/ws/terminal")
async def terminal_websocket(websocket: WebSocket) -> None:
    origin = websocket.headers.get("origin")
    if not (_is_local_origin(origin) or _is_local_client(websocket)):
        await websocket.close(code=1008)
        return

    terminal_id = _safe_terminal_id(websocket.query_params.get("terminal_id"))
    store = get_terminal_capability_store(
        token_ttl_seconds=_TERMINAL_TOKEN_TTL_SECONDS,
        max_sessions=_MAX_TERMINAL_SESSIONS_PER_USER,
        lease_seconds=_TERMINAL_SESSION_LEASE_SECONDS,
    )
    try:
        capability = await asyncio.to_thread(
            store.consume_and_reserve,
            token=websocket.query_params.get("terminal_token"),
            terminal_id=terminal_id,
        )
    except TerminalSessionLimitReached:
        await websocket.close(code=1013)
        return
    except TerminalCapabilityStoreUnavailable:
        await websocket.close(code=1013)
        return
    if capability is None:
        await websocket.close(code=1008)
        return
    _token_record, reservation = capability

    await websocket.accept()
    cwd = _terminal_cwd()
    session = TerminalSession(
        terminal_id=terminal_id,
        websocket=websocket,
        cwd=cwd,
        env=_terminal_env(cwd),
    )
    heartbeat_task: asyncio.Task[None] | None = None

    try:
        await session.start()
        heartbeat_task = asyncio.create_task(
            _maintain_terminal_session_lease(websocket, store, reservation)
        )
        while True:
            message = await websocket.receive_json()
            message_type = message.get("type")
            if message_type == "input":
                await session.write_input(str(message.get("data") or ""))
            elif message_type == "resize":
                rows = message.get("rows")
                cols = message.get("cols")
                session.resize(
                    int(rows) if rows is not None else None,
                    int(cols) if cols is not None else None,
                )
            else:
                await websocket.send_json(
                    {
                        "type": "error",
                        "terminalId": terminal_id,
                        "data": f"Unsupported terminal message type: {message_type}",
                    }
                )
    except WebSocketDisconnect:
        pass
    finally:
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat_task
        await session.close()
        with suppress(TerminalCapabilityStoreUnavailable):
            await asyncio.to_thread(store.release, reservation)


async def _maintain_terminal_session_lease(
    websocket: WebSocket,
    store: TerminalCapabilityStore,
    reservation: TerminalSessionReservation,
) -> None:
    while True:
        await asyncio.sleep(_TERMINAL_SESSION_HEARTBEAT_SECONDS)
        try:
            lease_active = await asyncio.to_thread(store.heartbeat, reservation)
        except TerminalCapabilityStoreUnavailable:
            lease_active = False
        if not lease_active:
            with suppress(RuntimeError):
                await websocket.close(code=1013)
            return
