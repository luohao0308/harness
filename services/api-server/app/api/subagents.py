import json
from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.specialists import (
    SpecialistValidationError,
    SubagentDepthExceededError,
    SubagentSpecialistRegistry,
    ensure_system_specialists,
)
from app.agents.subagent_manager import SubagentLimitExceededError, SubagentManager
from app.agents.subagent_recovery_history import (
    persist_recovery_batch,
    recovery_action_counts,
)
from app.api.schemas import (
    FanoutBatchMemberResponse,
    FanoutBatchPage,
    FanoutBatchResponse,
    SubagentBulkActionItem,
    SubagentBulkActionRequest,
    SubagentBulkActionResponse,
    SubagentCreateRequest,
    SubagentListItemResponse,
    SubagentListPage,
    SubagentOutputCreateRequest,
    SubagentOutputResponse,
    SubagentPage,
    SubagentRecoverRequest,
    SubagentRecoveryBatchPage,
    SubagentRecoveryGlobalSummaryResponse,
    SubagentRecoveryOrganizationSummary,
    SubagentRecoveryResponse,
    SubagentRecoverySummaryResponse,
    SubagentRecoveryTaskSummary,
    SubagentResponse,
    SubagentSpecialistSummary,
)
from app.api.tasks import get_owned_task
from app.db.models import AgentRun, SubagentOutput, SubagentRecoveryBatch, SubagentSpecialist, Task
from app.db.session import get_db_session
from app.security.auth import Principal, require_role

RUN_COMPATIBILITY_DESCRIPTION = (
    "内部兼容接口；产品主入口使用 /api/agents/{agent_id}/runs 和 /api/agents/runs/*。"
)

router = APIRouter(tags=["subagents"])
DbSession = Annotated[Session, Depends(get_db_session)]


@router.get(
    "/tasks/{task_id}/subagents",
    response_model=SubagentPage,
    summary="兼容层：查询 Agent Run 子 Agent",
    description=f"{RUN_COMPATIBILITY_DESCRIPTION} 返回指定 Agent Run 派生出的子 Agent 列表。",
    deprecated=True,
)
def list_task_subagents(task_id: str, session: DbSession, principal: Principal) -> SubagentPage:
    get_owned_task(task_id, session, principal.organization_id)
    statement = (
        select(AgentRun)
        .where(AgentRun.task_id == task_id, AgentRun.agent_type == "subagent")
        .order_by(AgentRun.started_at.asc().nullsfirst(), AgentRun.id.asc())
    )
    return SubagentPage(
        items=[_to_subagent_response(row) for row in session.execute(statement).scalars()]
    )


@router.get(
    "/tasks/{task_id}/fanout-batches",
    response_model=FanoutBatchPage,
    summary="兼容层：查询 Agent Run fanout 批次",
    description=f"{RUN_COMPATIBILITY_DESCRIPTION} 返回指定 Agent Run 的并行专家 fanout 批次聚合。",
    deprecated=True,
)
def list_task_fanout_batches(
    task_id: str,
    session: DbSession,
    principal: Principal,
) -> FanoutBatchPage:
    get_owned_task(task_id, session, principal.organization_id)
    runs = list(
        session.execute(
            select(AgentRun)
            .where(AgentRun.task_id == task_id, AgentRun.agent_type == "subagent")
            .order_by(AgentRun.started_at.asc().nullsfirst(), AgentRun.id.asc())
        ).scalars()
    )
    grouped: dict[str, list[AgentRun]] = {}
    for run in runs:
        batch_id = run.context_json.get("fanout_batch_id")
        if isinstance(batch_id, str) and batch_id:
            grouped.setdefault(batch_id, []).append(run)
    items = [
        _fanout_batch_response(task_id, batch_id, members)
        for batch_id, members in grouped.items()
    ]
    return FanoutBatchPage(items=items, next_cursor=None)


@router.get(
    "/subagents",
    response_model=SubagentListPage,
    summary="查询组织子 Agent 列表",
    description="返回当前组织全部子 Agent，支持按状态筛选，用于批量运营视图。",
)
def list_subagents(
    session: DbSession,
    principal: Principal,
    status_filter: str | None = Query(default=None, alias="status", description="子 Agent 状态"),
    limit: int = Query(default=100, ge=1, le=500, description="返回数量"),
) -> SubagentListPage:
    statement = (
        select(AgentRun, Task)
        .join(Task, Task.id == AgentRun.task_id)
        .where(
            Task.organization_id == principal.organization_id,
            AgentRun.agent_type == "subagent",
        )
        .order_by(AgentRun.started_at.desc(), AgentRun.id.desc())
        .limit(limit)
    )
    if status_filter:
        statement = statement.where(AgentRun.status == status_filter)
    rows = session.execute(statement).all()
    return SubagentListPage(
        items=[
            SubagentListItemResponse(
                **_to_subagent_response(agent_run).model_dump(),
                task_title=task.title,
                task_status=task.status,
                step_key=_subagent_step_key(agent_run),
                specialist_slug=_specialist_slug(agent_run),
                output_summary=_output_summary(agent_run.subagent_output),
            )
            for agent_run, task in rows
        ],
        next_cursor=None,
    )


def _subagent_step_key(agent_run: AgentRun) -> str | None:
    step_key = agent_run.context_json.get("step_key")
    return str(step_key) if step_key is not None else None


@router.post(
    "/tasks/{task_id}/subagents",
    response_model=SubagentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="兼容层：创建 Agent Run 子 Agent",
    description=(
        f"{RUN_COMPATIBILITY_DESCRIPTION} 为指定 Agent Run 派生一个子 Agent，"
        "并写入 SUBAGENT_SPAWNED 事件。"
    ),
    deprecated=True,
)
def create_task_subagent(
    task_id: str,
    request: SubagentCreateRequest,
    session: DbSession,
    principal: Principal,
) -> AgentRun:
    task = get_owned_task(task_id, session, principal.organization_id)
    specialist = None
    if request.specialist_slug:
        ensure_system_specialists(session)
        specialist = SubagentSpecialistRegistry(
            session,
            principal.organization_id,
        ).get_by_slug(request.specialist_slug)
        if specialist is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="专家模板未找到")
    try:
        agent_run = SubagentManager(session).spawn(
            task=task,
            assignment=request.assignment,
            parent_agent_id=request.parent_agent_id,
            timeout_seconds=request.timeout_seconds,
            enqueue=request.enqueue,
            specialist=specialist,
        )
    except SubagentLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="子 Agent 并发数量已达到上限",
        ) from exc
    except SubagentDepthExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="子专家嵌套深度超过 3 层",
        ) from exc
    session.commit()
    session.refresh(agent_run)
    return agent_run


@router.post(
    "/tasks/{task_id}/subagents/recover",
    response_model=SubagentRecoveryResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="兼容层：恢复 Agent Run 子 Agent",
    description=(
        f"{RUN_COMPATIBILITY_DESCRIPTION} 基于 Replay 状态恢复超时或卡住的子 Agent，"
        "并按需重新入队。"
    ),
    deprecated=True,
)
def recover_task_subagents(
    task_id: str,
    request: SubagentRecoverRequest,
    session: DbSession,
    principal: Principal,
) -> SubagentRecoveryResponse:
    task = get_owned_task(task_id, session, principal.organization_id)
    replay_sequence, recovered, scanned_count = SubagentManager(session).recover_for_task(
        task=task,
        stale_after_seconds=request.stale_after_seconds,
        enqueue=request.enqueue,
        takeover_owner=f"api:{principal.user_id}",
    )
    response = SubagentRecoveryResponse(
        batch_id=f"manual-{uuid4()}",
        task_id=task.id,
        trigger="manual",
        replay_sequence=replay_sequence,
        stale_after_seconds=request.stale_after_seconds,
        enqueue=request.enqueue,
        scanned_count=scanned_count,
        recovered_count=len(recovered),
        action_counts=recovery_action_counts(recovered),
        recovered=recovered,
        completed_at=datetime.now(UTC),
    )
    persist_recovery_batch(
        session=session,
        organization_id=task.organization_id,
        payload={
            **response.model_dump(mode="json"),
            "lock_acquired": True,
            "task_count": 1,
            "recovered_by_task": [
                {
                    "task_id": task.id,
                    "replay_sequence": replay_sequence,
                    "scanned_count": scanned_count,
                    "recovered_count": len(recovered),
                    "recovered": recovered,
                }
            ]
            if recovered
            else [],
        },
    )
    session.commit()
    return response


@router.post(
    "/subagents/bulk",
    response_model=SubagentBulkActionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="批量操作子 Agent",
    description="对当前组织内选中的子 Agent 执行批量取消动作，并返回逐条结果。",
)
def bulk_action_subagents(
    request: SubagentBulkActionRequest,
    session: DbSession,
    principal: Principal,
) -> SubagentBulkActionResponse:
    statement = (
        select(AgentRun)
        .join(Task, Task.id == AgentRun.task_id)
        .where(
            AgentRun.id.in_(request.subagent_ids),
            AgentRun.agent_type == "subagent",
            Task.organization_id == principal.organization_id,
        )
    )
    owned = {agent_run.id: agent_run for agent_run in session.execute(statement).scalars()}
    manager = SubagentManager(session)
    items: list[SubagentBulkActionItem] = []
    for subagent_id in request.subagent_ids:
        agent_run = owned.get(subagent_id)
        if agent_run is None:
            items.append(
                SubagentBulkActionItem(
                    id=subagent_id,
                    action="not_found",
                    success=False,
                    error_message="子 Agent 未找到或无权限",
                )
            )
            continue
        previous_status = agent_run.status
        cancelled = manager.cancel(agent_run)
        actual_action = "cancelled" if cancelled.status != previous_status else "skipped_terminal"
        items.append(
            SubagentBulkActionItem(
                id=subagent_id,
                previous_status=previous_status,
                status=cancelled.status,
                action=actual_action,
                success=True,
            )
        )
    session.commit()
    return SubagentBulkActionResponse(
        action=request.action,
        requested_count=len(request.subagent_ids),
        succeeded_count=sum(1 for item in items if item.success),
        failed_count=sum(1 for item in items if not item.success),
        items=items,
    )


@router.get(
    "/tasks/{task_id}/subagents/recovery-batches",
    response_model=SubagentRecoveryBatchPage,
    summary="兼容层：查询 Agent Run 子 Agent 恢复批次",
    description=f"{RUN_COMPATIBILITY_DESCRIPTION} 返回指定 Agent Run 最近的子 Agent 恢复批次历史。",
    deprecated=True,
)
def list_task_subagent_recovery_batches(
    task_id: str,
    session: DbSession,
    principal: Principal,
    limit: int = 20,
) -> SubagentRecoveryBatchPage:
    task = get_owned_task(task_id, session, principal.organization_id)
    capped_limit = max(1, min(limit, 100))
    statement = (
        select(SubagentRecoveryBatch)
        .where(
            SubagentRecoveryBatch.organization_id == principal.organization_id,
            SubagentRecoveryBatch.task_id == task.id,
        )
        .order_by(SubagentRecoveryBatch.completed_at.desc(), SubagentRecoveryBatch.id.desc())
        .limit(capped_limit)
    )
    return SubagentRecoveryBatchPage(items=list(session.execute(statement).scalars()))


@router.get(
    "/subagents/recovery/summary",
    response_model=SubagentRecoverySummaryResponse,
    summary="查询子 Agent 恢复运营摘要",
    description="按当前组织聚合最近的子 Agent 自动恢复与手动恢复批次，用于运营视图。",
)
def get_subagent_recovery_summary(
    session: DbSession,
    principal: Principal,
    limit: int = 20,
) -> SubagentRecoverySummaryResponse:
    capped_limit = max(1, min(limit, 100))
    statement = (
        select(SubagentRecoveryBatch)
        .where(SubagentRecoveryBatch.organization_id == principal.organization_id)
        .order_by(SubagentRecoveryBatch.completed_at.desc(), SubagentRecoveryBatch.id.desc())
        .limit(capped_limit)
    )
    batches = list(session.execute(statement).scalars())
    task_summaries = _recovery_task_summaries(batches)
    totals = _recovery_batch_totals(batches)
    return SubagentRecoverySummaryResponse(
        organization_id=principal.organization_id,
        batch_total=totals["batch_total"],
        task_total=totals["task_total"],
        scanned_total=totals["scanned_total"],
        recovered_total=totals["recovered_total"],
        lock_skipped_total=totals["lock_skipped_total"],
        action_counts=totals["action_counts"],
        latest_completed_at=totals["latest_completed_at"],
        tasks=task_summaries,
        recent_batches=batches,
    )


@router.get(
    "/subagents/recovery/global-summary",
    response_model=SubagentRecoveryGlobalSummaryResponse,
    summary="查询全局子 Agent 恢复运营摘要",
    description="仅 admin 可访问。跨组织聚合最近的子 Agent 自动恢复与手动恢复批次。",
)
def get_subagent_recovery_global_summary(
    session: DbSession,
    principal: Principal,
    limit: int = Query(default=100, ge=1, le=500, description="返回批次数量"),
) -> SubagentRecoveryGlobalSummaryResponse:
    require_role(principal, {"admin"})
    return _subagent_recovery_global_summary(session=session, limit=limit)


@router.get(
    "/subagents/recovery/global-summary/export",
    response_class=Response,
    summary="导出全局子 Agent 恢复运营摘要",
    description="仅 admin 可访问。导出跨组织子 Agent 恢复运营摘要 JSON。",
    responses={
        200: {
            "description": "JSON 导出文件",
            "content": {"application/json": {}},
        }
    },
)
def export_subagent_recovery_global_summary(
    session: DbSession,
    principal: Principal,
    limit: int = Query(default=100, ge=1, le=500, description="返回批次数量"),
) -> Response:
    require_role(principal, {"admin"})
    payload = _subagent_recovery_global_summary(session=session, limit=limit)
    body = json.dumps(payload.model_dump(mode="json"), ensure_ascii=False, indent=2).encode("utf-8")
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="subagent-recovery-global-summary.json"',
            "X-Harness-Export-Count": str(payload.batch_total),
            "X-Harness-Export-Source": "subagent_recovery",
        },
    )


def _subagent_recovery_global_summary(
    *,
    session: Session,
    limit: int,
) -> SubagentRecoveryGlobalSummaryResponse:
    capped_limit = max(1, min(limit, 500))
    batches = list(
        session.execute(
            select(SubagentRecoveryBatch)
            .order_by(SubagentRecoveryBatch.completed_at.desc(), SubagentRecoveryBatch.id.desc())
            .limit(capped_limit)
        ).scalars()
    )
    totals = _recovery_batch_totals(batches)
    organization_batches: dict[str | None, list[SubagentRecoveryBatch]] = {}
    for batch in batches:
        organization_batches.setdefault(batch.organization_id, []).append(batch)
    organization_summaries = [
        _recovery_organization_summary(organization_id, grouped_batches)
        for organization_id, grouped_batches in organization_batches.items()
    ]
    organization_summaries.sort(
        key=lambda item: (item.recovered_total, item.scanned_total, item.organization_id or ""),
        reverse=True,
    )
    return SubagentRecoveryGlobalSummaryResponse(
        organization_count=len(
            {batch.organization_id for batch in batches if batch.organization_id is not None}
        ),
        batch_total=totals["batch_total"],
        task_total=totals["task_total"],
        scanned_total=totals["scanned_total"],
        recovered_total=totals["recovered_total"],
        lock_skipped_total=totals["lock_skipped_total"],
        action_counts=totals["action_counts"],
        latest_completed_at=totals["latest_completed_at"],
        organizations=organization_summaries,
        recent_batches=batches,
    )


def _recovery_organization_summary(
    organization_id: str | None,
    batches: list[SubagentRecoveryBatch],
) -> SubagentRecoveryOrganizationSummary:
    totals = _recovery_batch_totals(batches)
    return SubagentRecoveryOrganizationSummary(
        organization_id=organization_id,
        batch_total=totals["batch_total"],
        task_total=totals["task_total"],
        scanned_total=totals["scanned_total"],
        recovered_total=totals["recovered_total"],
        lock_skipped_total=totals["lock_skipped_total"],
        action_counts=totals["action_counts"],
        latest_completed_at=totals["latest_completed_at"],
    )


def _recovery_batch_totals(batches: list[SubagentRecoveryBatch]) -> dict:
    action_counts: dict[str, int] = {}
    for batch in batches:
        recovered_actions = recovery_action_counts(list(batch.recovered or []))
        source_counts = recovered_actions or dict(batch.action_counts or {})
        for action, count in source_counts.items():
            action_counts[str(action)] = action_counts.get(str(action), 0) + int(count)
    return {
        "batch_total": len({batch.batch_id for batch in batches}),
        "task_total": len({batch.task_id for batch in batches if batch.task_id}),
        "scanned_total": sum(batch.scanned_count for batch in batches),
        "recovered_total": sum(batch.recovered_count for batch in batches),
        "lock_skipped_total": sum(1 for batch in batches if not batch.lock_acquired),
        "action_counts": action_counts,
        "latest_completed_at": max((batch.completed_at for batch in batches), default=None),
    }


def _recovery_task_summaries(
    batches: list[SubagentRecoveryBatch],
) -> list[SubagentRecoveryTaskSummary]:
    summaries: dict[str, dict] = {}
    for batch in batches:
        if not batch.task_id:
            continue
        summary = summaries.setdefault(
            batch.task_id,
            {
                "task_id": batch.task_id,
                "scanned_count": 0,
                "recovered_count": 0,
                "latest_batch_id": batch.batch_id,
                "latest_completed_at": batch.completed_at,
                "latest_replay_sequence": batch.replay_sequence,
            },
        )
        summary["scanned_count"] += batch.scanned_count
        summary["recovered_count"] += batch.recovered_count
        if batch.completed_at > summary["latest_completed_at"]:
            summary["latest_batch_id"] = batch.batch_id
            summary["latest_completed_at"] = batch.completed_at
            summary["latest_replay_sequence"] = batch.replay_sequence
    return [
        SubagentRecoveryTaskSummary(**summary)
        for summary in sorted(
            summaries.values(),
            key=lambda item: (item["recovered_count"], item["latest_completed_at"]),
            reverse=True,
        )
    ]


def get_owned_subagent(subagent_id: str, session: Session, principal: Principal) -> AgentRun:
    statement = (
        select(AgentRun)
        .join(Task, Task.id == AgentRun.task_id)
        .where(
            AgentRun.id == subagent_id,
            AgentRun.agent_type == "subagent",
            Task.organization_id == principal.organization_id,
        )
    )
    agent_run = session.execute(statement).scalar_one_or_none()
    if agent_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="子 Agent 未找到")
    return agent_run


@router.get(
    "/subagents/{subagent_id}",
    response_model=SubagentResponse,
    summary="查询子 Agent 详情",
    description="返回单个子 Agent 的状态与上下文。",
)
def get_subagent(subagent_id: str, session: DbSession, principal: Principal) -> AgentRun:
    return _to_subagent_response(get_owned_subagent(subagent_id, session, principal))


@router.post(
    "/subagents/{subagent_id}/output",
    response_model=SubagentOutputResponse,
    status_code=status.HTTP_201_CREATED,
    summary="写入子 Agent 结构化输出",
    description="用于测试和恢复路径。输出写一次且必须通过专家 schema 校验。",
)
def write_subagent_output(
    subagent_id: str,
    request: SubagentOutputCreateRequest,
    session: DbSession,
    principal: Principal,
) -> SubagentOutputResponse:
    agent_run = get_owned_subagent(subagent_id, session, principal)
    if agent_run.subagent_output is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="子 Agent 输出已存在")
    try:
        output = SubagentManager(session).finalize_with_output(
            agent_run=agent_run,
            raw_output_dict=request.output_json,
            budget_consumed=request.budget_consumed_json,
            budget_exceeded=request.budget_exceeded_json,
        )
    except SpecialistValidationError as exc:
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    session.commit()
    session.refresh(output)
    return SubagentOutputResponse.model_validate(output)


@router.post(
    "/subagents/{subagent_id}/cancel",
    response_model=SubagentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="取消子 Agent",
    description="取消仍在运行或等待中的子 Agent。",
)
def cancel_subagent(subagent_id: str, session: DbSession, principal: Principal) -> AgentRun:
    agent_run = get_owned_subagent(subagent_id, session, principal)
    cancelled = SubagentManager(session).cancel(agent_run)
    session.commit()
    session.refresh(cancelled)
    return _to_subagent_response(cancelled)


def _to_subagent_response(agent_run: AgentRun) -> SubagentResponse:
    return SubagentResponse(
        id=agent_run.id,
        task_id=agent_run.task_id,
        parent_agent_id=agent_run.parent_agent_id,
        agent_type=agent_run.agent_type,
        status=agent_run.status,
        specialist_id=agent_run.specialist_id,
        fanout_batch_id=_optional_context_string(agent_run, "fanout_batch_id"),
        fanout_index=_optional_context_int(agent_run, "fanout_index"),
        fanout_total=_optional_context_int(agent_run, "fanout_total"),
        context_json=agent_run.context_json,
        started_at=agent_run.started_at,
        completed_at=agent_run.completed_at,
        timeout_at=agent_run.timeout_at,
        specialist=_to_specialist_summary(agent_run.specialist),
        output=SubagentOutputResponse.model_validate(agent_run.subagent_output)
        if agent_run.subagent_output is not None
        else None,
    )


def _fanout_batch_response(
    task_id: str,
    batch_id: str,
    members: list[AgentRun],
) -> FanoutBatchResponse:
    ordered = sorted(
        members,
        key=lambda run: (
            _optional_context_int(run, "fanout_index")
            if _optional_context_int(run, "fanout_index") is not None
            else 9999,
            run.id,
        ),
    )
    statuses: dict[str, int] = {}
    for run in ordered:
        statuses[run.status] = statuses.get(run.status, 0) + 1
    first = ordered[0]
    return FanoutBatchResponse(
        fanout_batch_id=batch_id,
        task_id=task_id,
        step_key=_subagent_step_key(first),
        fanout_total=_optional_context_int(first, "fanout_total") or len(ordered),
        aggregation=str(first.context_json.get("fanout_aggregation") or "synthesizer_chain"),
        statuses=statuses,
        members=[
            FanoutBatchMemberResponse(
                id=run.id,
                status=run.status,
                specialist_id=run.specialist_id,
                specialist_slug=_specialist_slug(run),
                fanout_index=_optional_context_int(run, "fanout_index"),
                output_id=run.subagent_output.id if run.subagent_output is not None else None,
            )
            for run in ordered
        ],
    )


def _optional_context_string(agent_run: AgentRun, key: str) -> str | None:
    value = agent_run.context_json.get(key)
    return str(value) if isinstance(value, str) and value else None


def _optional_context_int(agent_run: AgentRun, key: str) -> int | None:
    value = agent_run.context_json.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _to_specialist_summary(
    specialist: SubagentSpecialist | None,
) -> SubagentSpecialistSummary | None:
    if specialist is None:
        return None
    return SubagentSpecialistSummary.model_validate(specialist)


def _specialist_slug(agent_run: AgentRun) -> str | None:
    if agent_run.specialist is not None:
        return agent_run.specialist.slug
    value = agent_run.context_json.get("specialist_slug")
    return str(value) if value is not None else None


def _output_summary(output: SubagentOutput | None) -> str | None:
    if output is None:
        return None
    data = output.output_json
    if not isinstance(data, dict):
        return None
    for key in ("summary", "answer"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value[:240]
    issues = data.get("issues")
    if isinstance(issues, list):
        return f"{len(issues)} issue(s)"
    violations = data.get("violations")
    if isinstance(violations, list):
        return f"{len(violations)} violation(s)"
    return None
