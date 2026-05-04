from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.logging import configure_json_logging

configure_json_logging()

app = FastAPI(
    title="Enterprise AI Agent Harness API",
    version="0.1.0",
    description="API server for the Enterprise AI Agent Harness Platform.",
)

app.include_router(health_router)
