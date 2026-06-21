from contextlib import asynccontextmanager
from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.agent_templates import router as agent_templates_router
from app.api.agent_versions import router as agent_versions_router
from app.api.agents import router as agents_router
from app.api.api_keys import router as api_keys_router
from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.autofix import router as autofix_router
from app.api.data_management import router as data_management_router
from app.api.demo import router as demo_router
from app.api.evals import router as evals_router
from app.api.events import router as events_router
from app.api.frontend_errors import router as frontend_errors_router
from app.api.health import router as health_router
from app.api.metrics import router as metrics_router
from app.api.observability import router as observability_router
from app.api.onboarding import router as onboarding_router
from app.api.retention import router as retention_router
from app.api.saml import router as saml_router
from app.api.sandboxes import router as sandboxes_router
from app.api.secrets import router as secrets_router
from app.api.sessions import router as sessions_router
from app.api.settings import router as settings_router
from app.api.subagent_marketplace import router as subagent_marketplace_router
from app.api.subagent_specialists import router as subagent_specialists_router
from app.api.subagents import router as subagents_router
from app.api.tasks import router as tasks_router
from app.api.teams import router as teams_router
from app.api.tools import router as tools_router
from app.api.users import router as users_router
from app.api.validation import router as validation_router
from app.bootstrap.first_admin import bootstrap_first_admin
from app.core.config import get_settings, validate_startup_settings
from app.core.logging import configure_json_logging
from app.core.tracing import OpenTelemetryTraceMiddleware
from app.db.session import SessionLocal
from app.security.auth import log_dev_token_status
from app.tools.adapter_registry import REGISTRY
from app.tools.adapters import ensure_builtin_adapters_registered

configure_json_logging()
settings = get_settings()

DEV_CONSOLE_PORTS = tuple(range(5173, 5180)) + (15174,)
DEV_CORS_ENVIRONMENTS = {"development", "test"}


def build_cors_origins() -> list[str]:
    configured_origins = {
        str(settings.console_base_url).rstrip("/"),
        str(settings.app_base_url).rstrip("/"),
        str(settings.api_base_url).rstrip("/"),
    }
    origins = set(configured_origins)
    local_aliases = {"localhost": "127.0.0.1", "127.0.0.1": "localhost"}
    for origin in configured_origins:
        parsed = urlsplit(origin)
        alias = local_aliases.get(parsed.hostname or "")
        if alias is None:
            continue
        netloc = parsed.netloc.replace(parsed.hostname or "", alias, 1)
        origins.add(urlunsplit((parsed.scheme, netloc, "", "", "")))

    if settings.app_env in DEV_CORS_ENVIRONMENTS:
        for host in ("localhost", "127.0.0.1", "0.0.0.0", "[::1]"):
            for port in DEV_CONSOLE_PORTS:
                origins.add(f"http://{host}:{port}")

    return sorted(origins)


def build_cors_origin_regex() -> str | None:
    if settings.app_env not in DEV_CORS_ENVIRONMENTS:
        return None

    ports = "|".join(str(port) for port in DEV_CONSOLE_PORTS)
    local_hosts = (
        r"localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]|"
        r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
        r"192\.168\.\d{1,3}\.\d{1,3}|"
        r"172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}"
    )
    return rf"^https?://(?:{local_hosts})(?::(?:{ports}))?$"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    startup_settings = get_settings()
    validate_startup_settings(startup_settings)
    log_dev_token_status(startup_settings)
    ensure_builtin_adapters_registered(REGISTRY)
    with SessionLocal() as session:
        bootstrap_first_admin(session, settings=startup_settings)
    try:
        yield
    finally:
        _app.state.accepting_sse = False


app = FastAPI(
    title="Harness API",
    version="0.1.0",
    summary="AI Harness Platform API",
    description=(
        "AI Harness Platform - Model + Harness = Agent. "
        "This API powers Agent configuration, Workspace runs, tools, MCP, knowledge, "
        "Eval, Observability, RBAC, retention, and deployment operations."
    ),
    contact={
        "name": "Harness Platform Maintainers",
        "url": "https://github.com/example/harness",
    },
    license_info={"name": "MIT"},
    openapi_tags=[
        {
            "name": "agents",
            "description": "Agent Studio, Workspace, memory, runs, and manifests.",
        },
        {
            "name": "tools",
            "description": "Tool Registry, MCP, adapters, capabilities, and approvals.",
        },
        {
            "name": "evals",
            "description": "Datasets, Eval Runs, contracts, regression gates, and graders.",
        },
        {
            "name": "observability",
            "description": "Cost, traces, alerts, logs, exports, and service health.",
        },
        {
            "name": "auth",
            "description": "Authentication, OAuth entrypoints, and current principal.",
        },
        {"name": "users", "description": "Organization user and role management."},
        {"name": "api-keys", "description": "API key lifecycle for automation clients."},
        {"name": "secrets", "description": "Encrypted business integration secret storage."},
        {"name": "audit", "description": "Organization audit log and export surfaces."},
        {"name": "data-management", "description": "Retention, export, and deletion operations."},
        {"name": "sandboxes", "description": "Sandbox, WarmPool, quota, and runtime isolation."},
        {"name": "teams", "description": "Team Mode rooms, agents, mailbox, tasks, and events."},
        {
            "name": "subagent-specialists",
            "description": "Specialist templates, stats, and calibration.",
        },
        {
            "name": "subagent-marketplace",
            "description": "Signed specialist sharing and installation.",
        },
    ],
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=build_cors_origins(),
    allow_origin_regex=build_cors_origin_regex(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# NOTE (v4 agent-workspace-chat-v4-refine, Req 6.3):
# Do NOT enable GZipMiddleware (or any Content-Encoding middleware) on routes
# matching "*/runs/chat/stream" or "*/runs/plan/stream". Compressing SSE
# bodies breaks incremental delivery and will trigger the frontend's
# `streaming_diagnostic: "possible_buffering"` fallback. If GZip is ever
# required for other routes, skip SSE paths via a `scope["path"]` check.
app.add_middleware(OpenTelemetryTraceMiddleware)
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)
except ImportError:
    # The custom middleware still emits the Harness trace id in minimal installs.
    pass

app.include_router(health_router)
app.include_router(metrics_router)
app.include_router(auth_router, prefix="/api")
app.include_router(saml_router, prefix="/api")
app.include_router(sessions_router, prefix="/api")
app.include_router(api_keys_router, prefix="/api")
app.include_router(secrets_router, prefix="/api")
app.include_router(audit_router, prefix="/api")
app.include_router(data_management_router, prefix="/api")
app.include_router(retention_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(agents_router, prefix="/api")
app.include_router(evals_router, prefix="/api")
app.include_router(demo_router, prefix="/api")
app.include_router(frontend_errors_router, prefix="/api")
app.include_router(onboarding_router, prefix="/api")
app.include_router(agent_templates_router, prefix="/api")
app.include_router(agent_versions_router, prefix="/api")
app.include_router(autofix_router, prefix="/api")
app.include_router(validation_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(teams_router, prefix="/api")
app.include_router(tools_router, prefix="/api")
app.include_router(events_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(subagent_marketplace_router, prefix="/api")
app.include_router(subagent_specialists_router, prefix="/api")
app.include_router(subagents_router, prefix="/api")
app.include_router(sandboxes_router, prefix="/api")
app.include_router(observability_router, prefix="/api")
