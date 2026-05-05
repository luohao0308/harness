from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import CountItem, ObservabilitySummaryResponse, WarmPoolResponse
from app.db.models import AgentEvent, AgentRun, ModelCall, SandboxInstance, Task, ToolCall
from app.db.session import get_db_session
from app.sandbox.warm_pool import WarmPoolManager
from app.security.auth import Principal

router = APIRouter(prefix="/observability", tags=["observability"])
DbSession = Annotated[Session, Depends(get_db_session)]


@router.get(
    "/summary",
    response_model=ObservabilitySummaryResponse,
    summary="查询观测聚合摘要",
    description="返回当前组织任务、模型、工具、沙箱、事件和 WarmPool 的聚合状态。",
)
def get_observability_summary(
    session: DbSession,
    principal: Principal,
) -> ObservabilitySummaryResponse:
    task_ids = select(Task.id).where(Task.organization_id == principal.organization_id)
    warm_pool = WarmPoolResponse.model_validate(WarmPoolManager().status(session=session).__dict__)
    return ObservabilitySummaryResponse(
        tasks_by_status=_count_items(
            session,
            select(Task.status, func.count(Task.id)).where(
                Task.organization_id == principal.organization_id
            ),
        ),
        subagents_by_status=_count_items(
            session,
            select(AgentRun.status, func.count(AgentRun.id)).where(AgentRun.task_id.in_(task_ids)),
        ),
        model_calls_by_status=_count_items(
            session,
            select(ModelCall.status, func.count(ModelCall.id)).where(
                ModelCall.task_id.in_(task_ids)
            ),
        ),
        tool_calls_by_status=_count_items(
            session,
            select(ToolCall.status, func.count(ToolCall.id)).where(ToolCall.task_id.in_(task_ids)),
        ),
        sandboxes_by_status=_count_items(
            session,
            select(SandboxInstance.status, func.count(SandboxInstance.id)).where(
                SandboxInstance.task_id.in_(task_ids)
            ),
        ),
        warm_pool=warm_pool,
        event_total=_count_total(
            session,
            select(func.count(AgentEvent.id)).where(AgentEvent.task_id.in_(task_ids)),
        ),
        task_total=_count_total(
            session,
            select(func.count(Task.id)).where(Task.organization_id == principal.organization_id),
        ),
        failed_task_total=_count_total(
            session,
            select(func.count(Task.id)).where(
                Task.organization_id == principal.organization_id,
                Task.status == "FAILED",
            ),
        ),
        model_call_total=_count_total(
            session,
            select(func.count(ModelCall.id)).where(ModelCall.task_id.in_(task_ids)),
        ),
        tool_call_total=_count_total(
            session,
            select(func.count(ToolCall.id)).where(ToolCall.task_id.in_(task_ids)),
        ),
        sandbox_total=_count_total(
            session,
            select(func.count(SandboxInstance.id)).where(SandboxInstance.task_id.in_(task_ids)),
        ),
    )


def _count_items(session: Session, statement) -> list[CountItem]:
    rows = session.execute(statement.group_by(statement.selected_columns[0])).all()
    return [CountItem(name=str(name), count=int(count)) for name, count in rows]


def _count_total(session: Session, statement) -> int:
    return int(session.execute(statement).scalar_one() or 0)
