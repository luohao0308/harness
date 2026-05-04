from fastapi import APIRouter
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from app.observability import metrics as _metrics

router = APIRouter(tags=["metrics"])


@router.get("/metrics", include_in_schema=False)
def get_metrics() -> Response:
    _metrics.agent_tasks_running.set(0)
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
