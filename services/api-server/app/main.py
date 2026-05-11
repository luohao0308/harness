from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.agents import router as agents_router
from app.api.evals import router as evals_router
from app.api.events import router as events_router
from app.api.health import router as health_router
from app.api.metrics import router as metrics_router
from app.api.observability import router as observability_router
from app.api.sandboxes import router as sandboxes_router
from app.api.settings import router as settings_router
from app.api.subagents import router as subagents_router
from app.api.tasks import router as tasks_router
from app.api.tools import router as tools_router
from app.core.config import get_settings
from app.core.logging import configure_json_logging
from app.core.tracing import OpenTelemetryTraceMiddleware

configure_json_logging()
settings = get_settings()


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
    return sorted(origins)

app = FastAPI(
    title="企业级 AI Agent Harness API",
    version="0.1.0",
    description="用于企业级 AI Agent Harness 平台的任务、事件、沙箱、审计和设置 API。",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=build_cors_origins(),
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

app.include_router(health_router)
app.include_router(metrics_router)
app.include_router(agents_router, prefix="/api")
app.include_router(evals_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(tools_router, prefix="/api")
app.include_router(events_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(subagents_router, prefix="/api")
app.include_router(sandboxes_router, prefix="/api")
app.include_router(observability_router, prefix="/api")
