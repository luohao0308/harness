from fastapi import APIRouter
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import Response

from app.db.models import SandboxInstance
from app.db.session import SessionLocal
from app.observability import metrics as _metrics

router = APIRouter(tags=["metrics"])


@router.get("/metrics", include_in_schema=False)
def get_metrics() -> Response:
    _metrics.agent_tasks_running.set(0)
    _refresh_sandbox_quota_metrics()
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def _refresh_sandbox_quota_metrics() -> None:
    try:
        with SessionLocal() as session:
            sandboxes = list(session.execute(select(SandboxInstance)).scalars())
    except SQLAlchemyError:
        sandboxes = []
    running = [sandbox for sandbox in sandboxes if sandbox.status == "RUNNING"]
    _metrics.sandbox_memory_limit_mb_total.set(
        sum(sandbox.memory_limit_mb for sandbox in sandboxes)
    )
    _metrics.sandbox_running_memory_limit_mb_total.set(
        sum(sandbox.memory_limit_mb for sandbox in running)
    )
    _metrics.sandbox_cpu_limit_total.set(
        sum(_cpu_limit_value(sandbox.cpu_limit) for sandbox in sandboxes)
    )
    _metrics.sandbox_running_cpu_limit_total.set(
        sum(_cpu_limit_value(sandbox.cpu_limit) for sandbox in running)
    )
    _metrics.sandbox_network_enabled_total.set(
        sum(1 for sandbox in sandboxes if sandbox.network_enabled)
    )
    _metrics.sandbox_warm_pool_reused_total.set(
        sum(1 for sandbox in sandboxes if sandbox.warm_pool_reused)
    )


def _cpu_limit_value(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
