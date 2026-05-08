from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    EvalCaseCreateRequest,
    EvalCaseFromRunRequest,
    EvalCasePage,
    EvalCaseResponse,
    EvalDatasetCreateRequest,
    EvalDatasetPage,
    EvalDatasetResponse,
    EvalResultResponse,
    EvalRunCreateRequest,
    EvalRunPage,
    EvalRunResponse,
)
from app.db.models import (
    AdminAuditEvent,
    AgentAssignment,
    EvalCase,
    EvalDataset,
    EvalResult,
    EvalRun,
    ModelCall,
    Task,
    ToolCall,
    utc_now,
)
from app.db.session import get_db_session
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.security.auth import Principal

router = APIRouter(prefix="/evals", tags=["evals"])
DbSession = Annotated[Session, Depends(get_db_session)]


@router.post(
    "/datasets",
    response_model=EvalDatasetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建 Eval Dataset",
    description="创建评测数据集，并写入管理审计事件。",
)
def create_eval_dataset(
    request: EvalDatasetCreateRequest,
    session: DbSession,
    principal: Principal,
) -> EvalDatasetResponse:
    dataset = EvalDataset(
        organization_id=principal.organization_id,
        name=request.name,
        description=request.description,
        status="ACTIVE",
        created_by=principal.user_id,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    session.add(dataset)
    session.flush()
    _audit(
        session,
        principal=principal,
        event_type=EventType.EVAL_DATASET_CREATED,
        resource_type="eval_dataset",
        resource_id=dataset.id,
        action="create",
        payload={"dataset_id": dataset.id, "name": dataset.name},
    )
    session.commit()
    session.refresh(dataset)
    return _dataset_response(dataset, case_count=0)


@router.get(
    "/datasets",
    response_model=EvalDatasetPage,
    summary="查询 Eval Dataset",
    description="返回当前组织的评测数据集及 case 数量。",
)
def list_eval_datasets(
    session: DbSession,
    principal: Principal,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> EvalDatasetPage:
    datasets = list(
        session.execute(
            select(EvalDataset)
            .where(EvalDataset.organization_id == principal.organization_id)
            .order_by(EvalDataset.created_at.desc())
            .limit(limit)
        ).scalars()
    )
    counts = _case_counts(session, [dataset.id for dataset in datasets])
    return EvalDatasetPage(
        items=[
            _dataset_response(dataset, case_count=counts.get(dataset.id, 0))
            for dataset in datasets
        ]
    )


@router.post(
    "/datasets/{dataset_id}/cases",
    response_model=EvalCaseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建 Eval Case",
    description="手动向 Dataset 添加一个评测用例。",
)
def create_eval_case(
    dataset_id: str,
    request: EvalCaseCreateRequest,
    session: DbSession,
    principal: Principal,
) -> EvalCase:
    dataset = _get_dataset(dataset_id, session, principal.organization_id)
    eval_case = EvalCase(
        dataset_id=dataset.id,
        source_task_id=None,
        input_json=request.input_json,
        expected_json=request.expected_json,
        tags_json=request.tags_json,
        created_at=utc_now(),
    )
    session.add(eval_case)
    dataset.updated_at = utc_now()
    session.flush()
    _audit(
        session,
        principal=principal,
        event_type=EventType.EVAL_CASE_CREATED,
        resource_type="eval_case",
        resource_id=eval_case.id,
        action="create",
        payload={"dataset_id": dataset.id, "eval_case_id": eval_case.id},
    )
    session.commit()
    session.refresh(eval_case)
    return eval_case


@router.post(
    "/datasets/{dataset_id}/cases/from-run/{task_id}",
    response_model=EvalCaseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="从 Agent Run 保存 Eval Case",
    description="将一次成功或失败的 Agent Run 固化为 Eval Case，供回归评测使用。",
)
def create_eval_case_from_run(
    dataset_id: str,
    task_id: str,
    request: EvalCaseFromRunRequest,
    session: DbSession,
    principal: Principal,
) -> EvalCase:
    dataset = _get_dataset(dataset_id, session, principal.organization_id)
    task = _get_task(task_id, session, principal.organization_id)
    eval_case = EvalCase(
        dataset_id=dataset.id,
        source_task_id=task.id,
        input_json={
            "task_id": task.id,
            "title": task.title,
            "goal": task.goal,
            "model_provider": task.model_provider,
            "model_name": task.model_name,
            "status": task.status,
        },
        expected_json=request.expected_json or {"status": task.status},
        tags_json=request.tags_json,
        created_at=utc_now(),
    )
    session.add(eval_case)
    dataset.updated_at = utc_now()
    session.flush()
    EventStore(session).append(
        task_id=task.id,
        event_type=EventType.EVAL_CASE_CREATED,
        payload_json={
            "dataset_id": dataset.id,
            "eval_case_id": eval_case.id,
            "source_task_id": task.id,
        },
        actor_type="user",
        actor_id=principal.user_id,
    )
    session.commit()
    session.refresh(eval_case)
    return eval_case


@router.get(
    "/datasets/{dataset_id}/cases",
    response_model=EvalCasePage,
    summary="查询 Eval Case",
    description="返回指定 Dataset 的评测用例。",
)
def list_eval_cases(
    dataset_id: str,
    session: DbSession,
    principal: Principal,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> EvalCasePage:
    dataset = _get_dataset(dataset_id, session, principal.organization_id)
    cases = list(
        session.execute(
            select(EvalCase)
            .where(EvalCase.dataset_id == dataset.id)
            .order_by(EvalCase.created_at.desc())
            .limit(limit)
        ).scalars()
    )
    return EvalCasePage(items=cases)


@router.post(
    "/datasets/{dataset_id}/runs",
    response_model=EvalRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="启动 Eval Run",
    description="对 Dataset 中的 Case 执行确定性 Trace Grader，并生成回归指标。",
)
def create_eval_run(
    dataset_id: str,
    request: EvalRunCreateRequest,
    session: DbSession,
    principal: Principal,
) -> EvalRunResponse:
    dataset = _get_dataset(dataset_id, session, principal.organization_id)
    cases = list(
        session.execute(
            select(EvalCase)
            .where(EvalCase.dataset_id == dataset.id)
            .order_by(EvalCase.created_at.asc())
        ).scalars()
    )
    if not cases:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Dataset 中没有 Eval Case")

    eval_run = EvalRun(
        dataset_id=dataset.id,
        organization_id=principal.organization_id,
        agent_id=request.agent_id,
        status="RUNNING",
        metrics_json={},
        created_by=principal.user_id,
        started_at=utc_now(),
        created_at=utc_now(),
    )
    session.add(eval_run)
    session.flush()
    _audit(
        session,
        principal=principal,
        event_type=EventType.EVAL_RUN_STARTED,
        resource_type="eval_run",
        resource_id=eval_run.id,
        action="start",
        payload={"dataset_id": dataset.id, "eval_run_id": eval_run.id},
    )

    results = [_grade_case(session, eval_run.id, eval_case) for eval_case in cases]
    session.add_all(results)
    session.flush()
    for result in results:
        if result.task_id is None:
            continue
        EventStore(session).append(
            task_id=result.task_id,
            event_type=EventType.EVAL_CASE_GRADED,
            payload_json={
                "dataset_id": dataset.id,
                "eval_run_id": eval_run.id,
                "eval_case_id": result.eval_case_id,
                "eval_result_id": result.id,
                "status": result.status,
                "scores": result.scores_json,
            },
            actor_type="system",
            actor_id="deterministic_trace_grader_v1",
        )
    eval_run.status = "COMPLETED"
    eval_run.completed_at = utc_now()
    eval_run.metrics_json = _aggregate_metrics(results)
    _audit(
        session,
        principal=principal,
        event_type=EventType.EVAL_RUN_COMPLETED,
        resource_type="eval_run",
        resource_id=eval_run.id,
        action="complete",
        payload={
            "dataset_id": dataset.id,
            "eval_run_id": eval_run.id,
            "metrics": eval_run.metrics_json,
        },
    )
    session.commit()
    session.refresh(eval_run)
    return _eval_run_response(eval_run, results)


@router.get(
    "/runs",
    response_model=EvalRunPage,
    summary="查询 Eval Run 列表",
    description="返回当前组织最近的评测运行。",
)
def list_eval_runs(
    session: DbSession,
    principal: Principal,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> EvalRunPage:
    runs = list(
        session.execute(
            select(EvalRun)
            .where(EvalRun.organization_id == principal.organization_id)
            .order_by(EvalRun.created_at.desc())
            .limit(limit)
        ).scalars()
    )
    return EvalRunPage(items=[_eval_run_response(run, []) for run in runs])


@router.get(
    "/runs/{eval_run_id}",
    response_model=EvalRunResponse,
    summary="查询 Eval Run 详情",
    description="返回 Eval Run 聚合指标和 Case 评分明细。",
)
def get_eval_run(eval_run_id: str, session: DbSession, principal: Principal) -> EvalRunResponse:
    eval_run = session.execute(
        select(EvalRun).where(
            EvalRun.id == eval_run_id,
            EvalRun.organization_id == principal.organization_id,
        )
    ).scalar_one_or_none()
    if eval_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eval Run 未找到")
    results = list(
        session.execute(
            select(EvalResult)
            .where(EvalResult.eval_run_id == eval_run.id)
            .order_by(EvalResult.created_at.asc())
        ).scalars()
    )
    return _eval_run_response(eval_run, results)


def _get_dataset(dataset_id: str, session: Session, organization_id: str) -> EvalDataset:
    dataset = session.execute(
        select(EvalDataset).where(
            EvalDataset.id == dataset_id,
            EvalDataset.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eval Dataset 未找到")
    return dataset


def _get_task(task_id: str, session: Session, organization_id: str) -> Task:
    task = session.execute(
        select(Task).where(Task.id == task_id, Task.organization_id == organization_id)
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run 未找到")
    return task


def _dataset_response(dataset: EvalDataset, *, case_count: int) -> EvalDatasetResponse:
    return EvalDatasetResponse(
        id=dataset.id,
        organization_id=dataset.organization_id,
        name=dataset.name,
        description=dataset.description,
        status=dataset.status,
        created_by=dataset.created_by,
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
        case_count=case_count,
    )


def _case_counts(session: Session, dataset_ids: list[str]) -> dict[str, int]:
    if not dataset_ids:
        return {}
    rows = session.execute(
        select(EvalCase.dataset_id, func.count(EvalCase.id))
        .where(EvalCase.dataset_id.in_(dataset_ids))
        .group_by(EvalCase.dataset_id)
    ).all()
    return {dataset_id: count for dataset_id, count in rows}


def _grade_case(session: Session, eval_run_id: str, eval_case: EvalCase) -> EvalResult:
    task = session.get(Task, eval_case.source_task_id) if eval_case.source_task_id else None
    tool_calls = _tool_calls(session, task.id) if task else []
    model_calls = _model_calls(session, task.id) if task else []
    assignments = _assignments(session, task.id) if task else []
    expected_status = eval_case.expected_json.get("status")
    status_match = task is not None and (expected_status is None or task.status == expected_status)
    tool_denials = [call for call in tool_calls if call.status in {"DENIED", "BLOCKED"}]
    failed_tools = [call for call in tool_calls if call.status in {"FAILED", "TIMEOUT"}]
    score = 1.0 if status_match and not failed_tools else 0.0
    tool_selection_accuracy = (
        1.0 if tool_calls and not failed_tools else (1.0 if not tool_calls else 0.0)
    )
    latency_ms = _latency_ms(task)
    result_status = "PASSED" if score >= 1.0 else "FAILED"
    return EvalResult(
        eval_run_id=eval_run_id,
        eval_case_id=eval_case.id,
        task_id=task.id if task else None,
        status=result_status,
        scores_json={
            "task_success": score,
            "tool_selection_accuracy": tool_selection_accuracy,
            "policy_violation": 1.0 if tool_denials else 0.0,
            "retry_count": 0,
            "human_escalation": 0,
        },
        grader_trace_json={
            "grader": "deterministic_trace_grader_v1",
            "expected_status": expected_status,
            "actual_status": task.status if task else None,
            "tool_call_count": len(tool_calls),
            "model_call_count": len(model_calls),
            "assignment_count": len(assignments),
            "failed_tool_count": len(failed_tools),
            "policy_denial_count": len(tool_denials),
        },
        latency_ms=latency_ms,
        cost_usd="0",
        error_message=(
            None
            if result_status == "PASSED"
            else "Trace did not satisfy expected status or tool checks"
        ),
        created_at=utc_now(),
    )


def _aggregate_metrics(results: list[EvalResult]) -> dict:
    total = len(results) or 1
    return {
        "task_success_rate": _avg(results, "task_success"),
        "tool_selection_accuracy": _avg(results, "tool_selection_accuracy"),
        "policy_violation_rate": _avg(results, "policy_violation"),
        "avg_latency_ms": int(sum(result.latency_ms for result in results) / total),
        "avg_cost_usd": 0,
        "retry_rate": _avg(results, "retry_count"),
        "human_escalation_rate": _avg(results, "human_escalation"),
        "case_total": len(results),
        "passed_total": sum(1 for result in results if result.status == "PASSED"),
        "failed_total": sum(1 for result in results if result.status == "FAILED"),
    }


def _avg(results: list[EvalResult], key: str) -> float:
    if not results:
        return 0.0
    return round(sum(float(result.scores_json.get(key, 0)) for result in results) / len(results), 4)


def _latency_ms(task: Task | None) -> int:
    if task is None or task.completed_at is None:
        return 0
    return max(0, int((task.completed_at - task.created_at).total_seconds() * 1000))


def _tool_calls(session: Session, task_id: str) -> list[ToolCall]:
    return list(session.execute(select(ToolCall).where(ToolCall.task_id == task_id)).scalars())


def _model_calls(session: Session, task_id: str) -> list[ModelCall]:
    return list(session.execute(select(ModelCall).where(ModelCall.task_id == task_id)).scalars())


def _assignments(session: Session, task_id: str) -> list[AgentAssignment]:
    return list(
        session.execute(select(AgentAssignment).where(AgentAssignment.run_id == task_id)).scalars()
    )


def _eval_run_response(eval_run: EvalRun, results: list[EvalResult]) -> EvalRunResponse:
    return EvalRunResponse(
        id=eval_run.id,
        dataset_id=eval_run.dataset_id,
        organization_id=eval_run.organization_id,
        agent_id=eval_run.agent_id,
        status=eval_run.status,
        metrics_json=eval_run.metrics_json,
        created_by=eval_run.created_by,
        started_at=eval_run.started_at,
        completed_at=eval_run.completed_at,
        created_at=eval_run.created_at,
        results=[
            EvalResultResponse.model_validate(result, from_attributes=True) for result in results
        ],
    )


def _audit(
    session: Session,
    *,
    principal,
    event_type: EventType,
    resource_type: str,
    resource_id: str,
    action: str,
    payload: dict,
) -> None:
    session.add(
        AdminAuditEvent(
            organization_id=principal.organization_id,
            actor_id=principal.user_id,
            event_type=event_type.value,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            payload_json=payload,
            created_at=utc_now(),
        )
    )
