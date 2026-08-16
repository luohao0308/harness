from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.agents.model_gateway import ModelHealthChecker
from app.core.config import get_settings
from app.db.session import get_db_session
from app.sandbox.capabilities import probe_docker_sandbox

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
    settings = get_settings()
    if getattr(settings, "runtime_profile", "server") == "local":
        return _local_readiness(
            response=response,
            session=session,
            check=check,
            organization_id=organization_id,
        )

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


@router.get(
    "/api/health/capabilities",
    summary="可选运行能力",
    description="探测可选能力；能力缺失不会改变核心应用就绪状态。",
)
def capabilities() -> dict[str, dict[str, object]]:
    return {"docker_sandbox": probe_docker_sandbox()}


def _local_readiness(
    *,
    response: Response,
    session: Session,
    check: str | None,
    organization_id: str,
) -> dict:
    requested = {check} if check else {"db", "llm"}
    payload: dict[str, object] = {
        "profile": "local",
    }
    required_checks: list[dict] = []

    if "db" in requested:
        db_check = _db_readiness(session)
        payload["db"] = db_check
        required_checks.append(db_check)
    if "llm" in requested:
        payload["model"] = _local_model_readiness(
            session=session,
            organization_id=organization_id,
        )
    if "redis" in requested:
        payload["redis"] = {
            "status": "disabled",
            "required": False,
            "reason": "local_runtime_uses_sqlite_jobs",
        }
    if "docker" in requested:
        payload["capabilities"] = {"docker_sandbox": probe_docker_sandbox()}

    runtime_ready = all(item["status"] == "ok" for item in required_checks)
    payload["runtime_ready"] = runtime_ready
    payload["ready"] = runtime_ready
    if not runtime_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return payload


def _db_readiness(session: Session) -> dict:
    try:
        session.execute(text("SELECT 1")).scalar_one()
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
    return {"status": "ok"}


def _redis_readiness() -> dict:
    import redis

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


def _local_model_readiness(*, session: Session, organization_id: str) -> dict:
    settings = get_settings()
    if not settings.ai_provider_api_key.strip():
        return {
            "status": "setup_required",
            "state": "setup_required",
            "configured": False,
        }
    result = _llm_readiness(session=session, organization_id=organization_id)
    if result["status"] == "ok":
        return {**result, "state": "healthy", "configured": True}
    return {**result, "state": "error", "configured": True}
