from fastapi import FastAPI

from app.api.events import router as events_router
from app.api.health import router as health_router
from app.api.sandboxes import router as sandboxes_router
from app.api.subagents import router as subagents_router
from app.api.tasks import router as tasks_router
from app.core.logging import configure_json_logging

configure_json_logging()

app = FastAPI(
    title="Enterprise AI Agent Harness API",
    version="0.1.0",
    description="API server for the Enterprise AI Agent Harness Platform.",
)

app.include_router(health_router)
app.include_router(tasks_router, prefix="/api")
app.include_router(events_router, prefix="/api")
app.include_router(subagents_router, prefix="/api")
app.include_router(sandboxes_router, prefix="/api")
