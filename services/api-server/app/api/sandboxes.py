from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    SandboxPage,
    SandboxQuotaHistoryItem,
    SandboxQuotaHistoryPage,
    SandboxQuotaUsageResponse,
    SandboxResponse,
    WarmPoolResponse,
)
from app.db.models import SandboxInstance, SystemSetting, Task
from app.db.session import get_db_session
from app.sandbox.docker_manager import DockerManager
from app.sandbox.policies import (
    DEFAULT_POLICY_SETTINGS,
    DEFAULT_SANDBOX_CPUS,
    DEFAULT_SANDBOX_MEMORY_MB,
    DEFAULT_WORKSPACE_QUOTA_MB,
    POLICY_SETTINGS_KEY,
)
from app.sandbox.warm_pool import WarmPoolManager
from app.security.auth import Principal

router = APIRouter(tags=["sandboxes"])
DbSession = Annotated[Session, Depends(get_db_session)]

docker_manager = DockerManager()
warm_pool_manager = WarmPoolManager(docker_manager=docker_manager)


@router.get(
    "/sandboxes",
    response_model=SandboxPage,
    summary="查询沙箱列表",
    description="返回当前组织可见的容器沙箱实例列表。",
)
def list_sandboxes(session: DbSession, principal: Principal) -> SandboxPage:
    statement = (
        select(SandboxInstance)
        .join(Task, Task.id == SandboxInstance.task_id)
        .where(Task.organization_id == principal.organization_id)
        .order_by(SandboxInstance.created_at.desc())
    )
    return SandboxPage(items=list(session.execute(statement).scalars()))


@router.get(
    "/sandboxes/quota/usage",
    response_model=SandboxQuotaUsageResponse,
    summary="查询沙箱配额用量",
    description="聚合当前组织沙箱资源配额、运行中用量和策略配置。",
)
def get_sandbox_quota_usage(
    session: DbSession,
    principal: Principal,
) -> SandboxQuotaUsageResponse:
    task_ids = select(Task.id).where(Task.organization_id == principal.organization_id)
    sandboxes = list(
        session.execute(
            select(SandboxInstance).where(SandboxInstance.task_id.in_(task_ids))
        ).scalars()
    )
    running = [sandbox for sandbox in sandboxes if sandbox.status == "RUNNING"]
    policy_settings = _policy_settings_for_org(
        session=session,
        organization_id=principal.organization_id,
    )
    sandbox_settings = policy_settings.get("sandbox", {})
    allowlist = sandbox_settings.get("network_allowlist", [])
    return SandboxQuotaUsageResponse(
        organization_id=principal.organization_id,
        configured_memory_mb=_positive_int(
            sandbox_settings.get("memory_mb"),
            default=DEFAULT_SANDBOX_MEMORY_MB,
        ),
        configured_cpus=_positive_float_string(
            sandbox_settings.get("cpus"),
            default=DEFAULT_SANDBOX_CPUS,
        ),
        configured_workspace_quota_mb=_positive_int(
            sandbox_settings.get("workspace_quota_mb"),
            default=DEFAULT_WORKSPACE_QUOTA_MB,
        ),
        configured_network_enabled=bool(sandbox_settings.get("default_network", False)),
        configured_network_allowlist=[str(item) for item in allowlist if str(item)],
        sandbox_total=len(sandboxes),
        running_total=len(running),
        destroyed_total=sum(1 for sandbox in sandboxes if sandbox.status == "DESTROYED"),
        memory_limit_mb_total=sum(sandbox.memory_limit_mb for sandbox in sandboxes),
        running_memory_limit_mb_total=sum(sandbox.memory_limit_mb for sandbox in running),
        cpu_limit_total=sum(_cpu_limit_value(sandbox.cpu_limit) for sandbox in sandboxes),
        running_cpu_limit_total=sum(_cpu_limit_value(sandbox.cpu_limit) for sandbox in running),
        network_enabled_total=sum(1 for sandbox in sandboxes if sandbox.network_enabled),
        warm_pool_reused_total=sum(1 for sandbox in sandboxes if sandbox.warm_pool_reused),
        latest_created_at=max((sandbox.created_at for sandbox in sandboxes), default=None),
    )


@router.get(
    "/sandboxes/quota/history",
    response_model=SandboxQuotaHistoryPage,
    summary="查询沙箱配额历史",
    description="返回当前组织最近的沙箱资源配额审计记录。",
)
def list_sandbox_quota_history(
    session: DbSession,
    principal: Principal,
    limit: int = 100,
) -> SandboxQuotaHistoryPage:
    capped_limit = max(1, min(limit, 500))
    statement = (
        select(SandboxInstance)
        .join(Task, Task.id == SandboxInstance.task_id)
        .where(Task.organization_id == principal.organization_id)
        .order_by(SandboxInstance.created_at.desc(), SandboxInstance.id.desc())
        .limit(capped_limit)
    )
    return SandboxQuotaHistoryPage(
        items=[_quota_history_item(sandbox) for sandbox in session.execute(statement).scalars()],
        next_cursor=None,
    )


@router.get(
    "/sandboxes/warm-pool",
    response_model=WarmPoolResponse,
    summary="查询 WarmPool 状态",
    description="返回预热池容量、命中与失败统计。",
)
def get_warm_pool(session: DbSession, principal: Principal) -> WarmPoolResponse:
    _ = principal
    return WarmPoolResponse.model_validate(warm_pool_manager.status(session=session).__dict__)


def get_owned_sandbox(sandbox_id: str, session: Session, principal: Principal) -> SandboxInstance:
    statement = (
        select(SandboxInstance)
        .join(Task, Task.id == SandboxInstance.task_id)
        .where(
            SandboxInstance.id == sandbox_id,
            Task.organization_id == principal.organization_id,
        )
    )
    sandbox = session.execute(statement).scalar_one_or_none()
    if sandbox is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="沙箱未找到")
    return sandbox


@router.get(
    "/sandboxes/{sandbox_id}",
    response_model=SandboxResponse,
    summary="查询沙箱详情",
    description="返回单个沙箱实例的运行状态。",
)
def get_sandbox(sandbox_id: str, session: DbSession, principal: Principal) -> SandboxInstance:
    return get_owned_sandbox(sandbox_id, session, principal)


@router.post(
    "/sandboxes/{sandbox_id}/terminate",
    response_model=SandboxResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="终止沙箱",
    description="销毁指定沙箱实例。",
)
def terminate_sandbox(sandbox_id: str, session: DbSession, principal: Principal) -> SandboxInstance:
    sandbox = get_owned_sandbox(sandbox_id, session, principal)
    terminated = docker_manager.destroy_sandbox(session=session, sandbox=sandbox)
    session.commit()
    session.refresh(terminated)
    return terminated


def _quota_history_item(sandbox: SandboxInstance) -> SandboxQuotaHistoryItem:
    lifetime_seconds = None
    if sandbox.destroyed_at is not None:
        lifetime_seconds = max(0, int((sandbox.destroyed_at - sandbox.created_at).total_seconds()))
    return SandboxQuotaHistoryItem(
        id=sandbox.id,
        task_id=sandbox.task_id,
        container_id=sandbox.container_id,
        status=sandbox.status,
        cpu_limit=sandbox.cpu_limit,
        cpu_limit_value=_cpu_limit_value(sandbox.cpu_limit),
        memory_limit_mb=sandbox.memory_limit_mb,
        network_enabled=sandbox.network_enabled,
        warm_pool_reused=sandbox.warm_pool_reused,
        lifetime_seconds=lifetime_seconds,
        created_at=sandbox.created_at,
        destroyed_at=sandbox.destroyed_at,
    )


def _policy_settings_for_org(*, session: Session, organization_id: str | None) -> dict:
    if organization_id is None:
        return DEFAULT_POLICY_SETTINGS
    setting = session.execute(
        select(SystemSetting).where(
            SystemSetting.organization_id == organization_id,
            SystemSetting.key == POLICY_SETTINGS_KEY,
        )
    ).scalar_one_or_none()
    if setting is None:
        return DEFAULT_POLICY_SETTINGS
    return setting.value_json


def _cpu_limit_value(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _positive_int(value: object, *, default: int) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _positive_float_string(value: object, *, default: str) -> str:
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    if parsed.is_integer():
        return f"{parsed:.1f}"
    return f"{parsed:.3f}".rstrip("0").rstrip(".")
