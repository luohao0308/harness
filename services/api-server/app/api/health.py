from typing import Annotated

import redis
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.agents.model_gateway import ModelHealthChecker
from app.core.config import get_settings
from app.db.session import get_db_session

router = APIRouter(tags=["health"])
DbSession = Annotated[Session, Depends(get_db_session)]


@router.get("/health", summary="健康检查", description="返回 API 服务健康状态。")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "api-server"}


@router.get(
    "/api/health/liveness",
    summary="进程存活探针",
    description="只证明 API 进程仍在响应；不要把外部依赖抖动用于重启进程。",
)
def liveness() -> dict[str, str]:
    return {"status": "ok", "service": "api-server"}


@router.get(
    "/api/health/readiness",
    summary="服务就绪探针",
    description="检查数据库、Redis 和至少一个模型供应商是否可用。",
)
def readiness(
    response: Response,
    session: DbSession,
    check: Annotated[
        str | None,
        Query(description="可选单项检查：db、redis、llm"),
    ] = None,
    organization_id: Annotated[str, Query(description="模型设置所属组织")] = "dev-org",
) -> dict:
    checks: dict[str, dict] = {}
    requested = {check} if check else {"db", "redis", "llm"}
    if "db" in requested:
        checks["db"] = _db_readiness(session)
    if "redis" in requested:
        checks["redis"] = _redis_readiness()
    if "llm" in requested:
        checks["llm"] = _llm_readiness(session=session, organization_id=organization_id)
    ready = all(item["status"] == "ok" for item in checks.values())
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"ready": ready, **checks}


def _db_readiness(session: Session) -> dict:
    try:
        session.execute(text("SELECT 1")).scalar_one()
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
    return {"status": "ok"}


def _redis_readiness() -> dict:
    settings = get_settings()
    try:
        client = redis.Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        client.ping()
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
    return {"status": "ok"}


def _llm_readiness(*, session: Session, organization_id: str) -> dict:
    try:
        results = ModelHealthChecker(session).check(organization_id=organization_id)
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
    healthy = [item for item in results if item.get("status") == "healthy"]
    return {
        "status": "ok" if healthy else "error",
        "healthy_provider_count": len(healthy),
        "provider_count": len(results),
        "providers": results,
    }
