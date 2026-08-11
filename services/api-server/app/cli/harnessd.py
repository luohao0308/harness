from __future__ import annotations

import argparse
import asyncio
import importlib
import io
import json
import logging
import os
import signal
import socket
import sys
import threading
import warnings
from collections.abc import Generator
from contextlib import asynccontextmanager, contextmanager, redirect_stderr
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings, get_settings, install_runtime_settings
from app.db.sqlite_candidate_migration import migrate_sqlite_candidate
from app.db.sqlite_runtime_directory import SQLiteRuntimePaths
from app.db.sqlite_runtime_lock import SQLiteRuntimeLock
from app.local_runtime.bootstrap import LocalRuntimeBootstrap, read_bootstrap_from_fd

HANDSHAKE_PROTOCOL_VERSION = 1
LOOPBACK_HOST = "127.0.0.1"
LOG_FILE_NAME = "harnessd.jsonl"
RENDERER_PATH = "/desktop/"
EAGER_LOCAL_RUNTIME_ROUTER_MODULES = (
    ("app.api.health", ""),
    ("app.local_runtime.api", "/api"),
)
DEFERRED_LOCAL_RUNTIME_ROUTER_MODULES = (
    ("app.api.agent_templates", "/api"),
    ("app.api.agent_versions", "/api"),
    ("app.api.agents", "/api"),
    ("app.api.api_keys", "/api"),
    ("app.api.audit", "/api"),
    ("app.api.auth", "/api"),
    ("app.api.autofix", "/api"),
    ("app.api.data_management", "/api"),
    ("app.api.demo", "/api"),
    ("app.api.desktop_sync", "/api"),
    ("app.api.evals", "/api"),
    ("app.api.events", "/api"),
    ("app.api.frontend_errors", "/api"),
    ("app.api.gateway", "/api"),
    ("app.api.metrics", ""),
    ("app.api.mobile", "/api"),
    ("app.api.observability", "/api"),
    ("app.api.onboarding", "/api"),
    ("app.api.plugins", "/api"),
    ("app.api.retention", "/api"),
    ("app.api.sandboxes", "/api"),
    ("app.api.secrets", "/api"),
    ("app.api.sessions", "/api"),
    ("app.api.settings", "/api"),
    ("app.api.subagent_marketplace", "/api"),
    ("app.api.subagent_specialists", "/api"),
    ("app.api.subagents", "/api"),
    ("app.api.tasks", "/api"),
    ("app.api.teams", "/api"),
    ("app.api.terminal", ""),
    ("app.api.triggers", "/api"),
    ("app.api.tools", "/api"),
    ("app.api.users", "/api"),
    ("app.api.validation", "/api"),
)
LOCAL_RUNTIME_ROUTER_MODULES = (
    *EAGER_LOCAL_RUNTIME_ROUTER_MODULES,
    *DEFERRED_LOCAL_RUNTIME_ROUTER_MODULES,
)
RENDERER_SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; "
        "form-action 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; "
        "worker-src 'self' blob:; manifest-src 'self'"
    ),
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


def _runtime_version() -> str:
    try:
        return metadata.version("agent-harness-api-server")
    except metadata.PackageNotFoundError:
        return "0.1.0"


def _resource_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parents[2]


def renderer_directory() -> Path:
    packaged = _resource_root() / "renderer"
    if packaged.is_dir():
        return packaged
    return _resource_root().parents[1] / "apps" / "agent-console" / "dist"


class _SecretRedactionFilter(logging.Filter):
    def __init__(self, secrets: tuple[str, ...]) -> None:
        super().__init__()
        self._secrets = tuple(secret for secret in secrets if secret)

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for secret in self._secrets:
            message = message.replace(secret, "[REDACTED]")
        record.msg = message
        record.args = ()
        return True


class _RuntimeJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "created_at": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "service": getattr(record, "service", "harnessd"),
            "message": record.getMessage(),
            "event_type": getattr(record, "event_type", None),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _bootstrap_secrets(bootstrap: LocalRuntimeBootstrap) -> tuple[str, ...]:
    return (
        bootstrap.session_signing_secret.get_secret_value(),
        bootstrap.vault_encryption_secret.get_secret_value(),
        bootstrap.desktop_bootstrap_token.get_secret_value(),
        bootstrap.model_api_key.get_secret_value(),
    )


def configure_runtime_logging(data_dir: Path, bootstrap: LocalRuntimeBootstrap) -> Path:
    logs_dir = data_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    log_path = logs_dir / LOG_FILE_NAME
    log_path.touch(mode=0o600, exist_ok=True)
    try:
        log_path.chmod(0o600)
    except OSError:
        pass

    formatter = _RuntimeJsonFormatter()
    redaction_filter = _SecretRedactionFilter(_bootstrap_secrets(bootstrap))
    stderr_handler = logging.StreamHandler(sys.stderr)
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    for handler in (stderr_handler, file_handler):
        handler.setFormatter(formatter)
        handler.addFilter(redaction_filter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(stderr_handler)
    root_logger.addHandler(file_handler)
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "alembic"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.disabled = False
        logger.setLevel(logging.INFO)
        logger.propagate = True
    return log_path


def bind_loopback_socket(port: int) -> socket.socket:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((LOOPBACK_HOST, port))
        listener.listen(2048)
        listener.setblocking(False)
        return listener
    except BaseException:
        listener.close()
        raise


def build_ready_handshake(listener: socket.socket) -> dict[str, Any]:
    host, port = listener.getsockname()[:2]
    return {
        "protocol_version": HANDSHAKE_PROTOCOL_VERSION,
        "runtime_version": _runtime_version(),
        "origin": f"http://{host}:{port}",
        "health_path": "/api/health/readiness",
        "desktop_session_path": "/api/local-runtime/desktop-session",
        "renderer_path": RENDERER_PATH,
    }


def emit_ready_handshake(handshake: dict[str, Any]) -> None:
    payload = json.dumps(handshake, separators=(",", ":"), sort_keys=True) + "\n"
    os.write(sys.stdout.fileno(), payload.encode("utf-8"))


def runtime_paths(data_dir: Path) -> SQLiteRuntimePaths:
    runtime_dir = data_dir.resolve()
    backups_dir = runtime_dir / "backups"
    logs_dir = runtime_dir / "logs"
    for directory in (runtime_dir, backups_dir, logs_dir):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return SQLiteRuntimePaths(
        user_data_dir=runtime_dir.parent,
        runtime_dir=runtime_dir,
        backups_dir=backups_dir,
        logs_dir=logs_dir,
        manifest_path=runtime_dir / "runtime.json",
        lock_path=runtime_dir / "runtime.lock",
    )


def run_migrations(paths: SQLiteRuntimePaths, runtime_lock: SQLiteRuntimeLock) -> Path:
    resource_root = _resource_root()
    previous_working_directory = Path.cwd()
    try:
        os.chdir(resource_root)
        with redirect_stderr(io.StringIO()):
            return migrate_sqlite_candidate(
                paths,
                alembic_ini=resource_root / "alembic.ini",
                runtime_lock=runtime_lock,
            )
    finally:
        os.chdir(previous_working_directory)


def attach_static_renderer(app: Any, directory: Path | None = None) -> Path:
    from fastapi.responses import FileResponse
    from starlette.staticfiles import StaticFiles

    static_dir = (directory or renderer_directory()).resolve()
    index_path = static_dir / "index.html"
    if not index_path.is_file():
        raise FileNotFoundError(f"renderer index is missing: {index_path}")
    app.add_middleware(StaticRendererSecurityHeadersMiddleware)
    assets_dir = static_dir / "assets"
    if assets_dir.is_dir():
        app.mount(
            "/desktop/assets",
            StaticFiles(directory=assets_dir),
            name="desktop-renderer-assets",
        )

    @app.api_route(
        "/desktop/{renderer_path:path}",
        methods=["GET", "HEAD"],
        include_in_schema=False,
    )
    async def renderer_fallback(renderer_path: str):
        normalized = renderer_path.lstrip("/")
        candidate = (static_dir / normalized).resolve()
        try:
            candidate.relative_to(static_dir)
        except ValueError:
            return FileResponse(index_path)
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index_path)

    return static_dir


class StaticRendererSecurityHeadersMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/desktop"):
            await self.app(scope, receive, send)
            return

        async def send_with_security_headers(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {name.lower() for name, _value in headers}
                headers.extend(
                    (name.encode("latin-1"), value.encode("latin-1"))
                    for name, value in RENDERER_SECURITY_HEADERS.items()
                    if name.lower().encode("latin-1") not in existing
                )
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_security_headers)


def _settings_for_origin(settings: Settings, listener: socket.socket) -> Settings:
    handshake = build_ready_handshake(listener)
    origin = handshake["origin"]
    return settings.model_copy(
        update={
            "api_base_url": origin,
            "app_base_url": origin,
            "console_base_url": origin,
        }
    )


def _is_server_login_path(path: str) -> bool:
    return (
        path.startswith("/api/saml")
        or path in {"/api/auth/login", "/api/auth/register"}
        or path.startswith("/api/auth/oauth")
    )


class ReadyServer(uvicorn.Server):
    def __init__(self, config: uvicorn.Config, handshake: dict[str, Any]) -> None:
        super().__init__(config)
        self._handshake = handshake
        self._handshake_emitted = False

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await super().startup(sockets=sockets)
        if self.started and not self.should_exit and not self._handshake_emitted:
            emit_ready_handshake(self._handshake)
            self._handshake_emitted = True

    @contextmanager
    def capture_signals(self) -> Generator[None, None, None]:
        if threading.current_thread() is not threading.main_thread():
            yield
            return
        handled_signals = tuple(uvicorn.server.HANDLED_SIGNALS)
        original_handlers = {
            handled_signal: signal.signal(handled_signal, self.handle_exit)
            for handled_signal in handled_signals
        }
        try:
            yield
        finally:
            for handled_signal, handler in original_handlers.items():
                signal.signal(handled_signal, handler)


def build_local_runtime_app() -> FastAPI:
    """Build the SQLite-only desktop API without importing the server application graph."""
    from app.bootstrap.local_owner import bootstrap_local_owner
    from app.db.session import SessionLocal, engine
    from app.local_runtime.security import LocalRuntimeRequestBoundaryMiddleware
    from app.runtime_jobs.scheduler import RuntimeJobCoordinator

    @contextmanager
    def _owner_session():
        with SessionLocal() as session:
            bootstrap_local_owner(session)
            yield

    @contextmanager
    def _accepting_requests(local_app: FastAPI):
        local_app.state.accepting_sse = True
        try:
            yield
        finally:
            local_app.state.accepting_sse = False

    @asynccontextmanager
    async def lifespan(local_app: FastAPI):
        coordinator = RuntimeJobCoordinator(engine=engine)
        with _owner_session(), _accepting_requests(local_app):
            await coordinator.start()
            local_app.state.runtime_job_coordinator = coordinator
            try:
                yield
            finally:
                await coordinator.stop()

    local_app = FastAPI(
        title="Harness Local Runtime API",
        version=_runtime_version(),
        lifespan=lifespan,
    )

    for module_name, prefix in EAGER_LOCAL_RUNTIME_ROUTER_MODULES:
        module = importlib.import_module(module_name)
        local_app.include_router(module.router, prefix=prefix)

    deferred_routes_loaded = False
    deferred_defaults_initialized = False
    deferred_load_lock = threading.Lock()

    def load_deferred_routers() -> None:
        nonlocal deferred_routes_loaded
        if deferred_routes_loaded:
            return
        with deferred_load_lock:
            if deferred_routes_loaded:
                return
            deferred_router = APIRouter()
            for module_name, prefix in DEFERRED_LOCAL_RUNTIME_ROUTER_MODULES:
                module = importlib.import_module(module_name)
                deferred_router.include_router(module.router, prefix=prefix)
            local_app.include_router(deferred_router)
            deferred_routes_loaded = True
            local_app.openapi_schema = None

    def initialize_deferred_defaults() -> None:
        nonlocal deferred_defaults_initialized
        if deferred_defaults_initialized:
            return
        with deferred_load_lock:
            if deferred_defaults_initialized:
                return
            from app.agents.registry import ensure_default_agents

            with SessionLocal.begin() as session:
                ensure_default_agents(session, "")
            deferred_defaults_initialized = True

    def hydrate_deferred_routers() -> None:
        load_deferred_routers()
        initialize_deferred_defaults()

    original_openapi = local_app.openapi

    def openapi_with_deferred_routes():
        load_deferred_routers()
        return original_openapi()

    local_app.openapi = openapi_with_deferred_routes

    @local_app.middleware("http")
    async def load_business_routes_on_demand(request, call_next):
        path = request.url.path
        eager_path = (
            path == "/health"
            or path.startswith("/api/health/")
            or path.startswith("/api/local-runtime/")
            or path == "/desktop"
            or path.startswith("/desktop/")
        )
        if not eager_path:
            hydrate_deferred_routers()
        return await call_next(request)

    @local_app.middleware("http")
    async def disable_server_login_surfaces(request, call_next):
        if _is_server_login_path(request.url.path):
            from fastapi.responses import JSONResponse

            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        return await call_next(request)

    settings = get_settings()
    origin = str(settings.api_base_url).rstrip("/")
    local_app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin, "harness-app://renderer"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    local_app.add_middleware(LocalRuntimeRequestBoundaryMiddleware)
    return local_app


async def serve(
    listener: socket.socket,
    static_dir: Path | None,
    bootstrap: LocalRuntimeBootstrap,
) -> None:
    configure_runtime_logging(bootstrap.runtime_data_dir, bootstrap)
    app = build_local_runtime_app()
    attach_static_renderer(app, static_dir)
    config = uvicorn.Config(
        app,
        host=LOOPBACK_HOST,
        port=0,
        log_config=None,
        access_log=True,
        lifespan="on",
        timeout_graceful_shutdown=10,
    )
    server = ReadyServer(config, build_ready_handshake(listener))
    await server.serve(sockets=[listener])
    if not server.started:
        raise RuntimeError("ASGI lifespan failed before harnessd readiness")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="harnessd",
        description="Run the loopback-only Harness desktop sidecar.",
    )
    parser.add_argument(
        "--bootstrap-fd",
        type=int,
        default=0,
        help="inherited descriptor containing one JSON bootstrap document (default: stdin)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        choices=range(0, 65536),
        metavar="PORT",
        help="loopback port; 0 selects an available port (default: 0)",
    )
    parser.add_argument(
        "--static-dir",
        type=Path,
        default=None,
        help="built Agent Console renderer directory (default: repository development build)",
    )
    return parser.parse_args(argv)


def _write_startup_failure() -> None:
    payload = {
        "type": "harnessd.startup_error",
        "protocol_version": HANDSHAKE_PROTOCOL_VERSION,
        "message": "harnessd failed before readiness; inspect the runtime log",
    }
    sys.stderr.write(json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n")
    sys.stderr.flush()


def main(argv: list[str] | None = None) -> int:
    warnings.filterwarnings(
        "ignore",
        message="OpenSSL 3's legacy provider failed to load.*",
    )
    args = _parse_args(argv)
    listener: socket.socket | None = None
    runtime_lock: SQLiteRuntimeLock | None = None
    bootstrap: LocalRuntimeBootstrap | None = None
    try:
        bootstrap = read_bootstrap_from_fd(args.bootstrap_fd)
        paths = runtime_paths(bootstrap.runtime_data_dir)
        runtime_lock = SQLiteRuntimeLock(paths.lock_path).acquire()
        settings = bootstrap.install()
        configure_runtime_logging(bootstrap.runtime_data_dir, bootstrap)
        listener = bind_loopback_socket(args.port)
        settings = _settings_for_origin(settings, listener)
        install_runtime_settings(settings)
        run_migrations(paths, runtime_lock)
        install_runtime_settings(
            settings.model_copy(update={"database_url": paths.database_url()})
        )
        configure_runtime_logging(bootstrap.runtime_data_dir, bootstrap)
        logging.getLogger(__name__).info(
            "local runtime migrations complete",
            extra={"service": "harnessd", "event_type": "runtime.migrations.complete"},
        )
        asyncio.run(serve(listener, args.static_dir, bootstrap))
        return 0
    except KeyboardInterrupt:
        return 0
    except BaseException:
        if bootstrap is not None:
            configure_runtime_logging(bootstrap.runtime_data_dir, bootstrap)
            logging.getLogger(__name__).exception(
                "harnessd startup failed",
                extra={"service": "harnessd", "event_type": "runtime.startup.failed"},
            )
        _write_startup_failure()
        return 1
    finally:
        if listener is not None:
            listener.close()
        if runtime_lock is not None:
            runtime_lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
