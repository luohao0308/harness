import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.registry import ensure_default_agents
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
    RegressionDelta,
    SetBaselineRequest,
)
from app.db.models import (
    AdminAuditEvent,
    AgentAssignment,
    CitationRecord,
    EvalCase,
    EvalDataset,
    EvalResult,
    EvalRun,
    KnowledgePolicyAudit,
    ModelCall,
    PromptAssemblyManifest,
    RetrievalHit,
    RetrievalSession,
    Task,
    ToolCall,
    WebResearchSource,
    utc_now,
)
from app.db.session import get_db_session
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.security.auth import Principal
from app.tools.capabilities import CapabilityRegistry

router = APIRouter(prefix="/evals", tags=["evals"])
DbSession = Annotated[Session, Depends(get_db_session)]

GROUNDING_TRACE_SCHEMA_VERSION = 1
LOW_GROUNDING_SAMPLE_THRESHOLD = 5
GROUNDING_PASS_RATE_REGRESSION_THRESHOLD = -0.05
TASK_SUCCESS_RATE_REGRESSION_THRESHOLD = -0.10
QUALITY_RATE_REGRESSION_THRESHOLD = 0.05


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
            _dataset_response(dataset, case_count=counts.get(dataset.id, 0)) for dataset in datasets
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
) -> EvalCaseResponse:
    dataset = _get_dataset(dataset_id, session, principal.organization_id)
    eval_case = EvalCase(
        dataset_id=dataset.id,
        source_task_id=None,
        input_json=request.input_json,
        expected_json=request.expected_json,
        capability_snapshot_json={},
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
    return _eval_case_response(eval_case)


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
) -> EvalCaseResponse:
    dataset = _get_dataset(dataset_id, session, principal.organization_id)
    task = _get_task(task_id, session, principal.organization_id)
    if task.status not in ("COMPLETED", "FAILED"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="只能从 COMPLETED 或 FAILED 状态的 Run 保存 Eval Case",
        )
    tool_calls = _tool_calls(session, task.id)
    model_calls = _model_calls(session, task.id)
    assignments = _assignments(session, task.id)
    execution_trace = {
        "tool_calls": [
            {
                "tool_name": tc.tool_name,
                "status": tc.status,
                "risk_level": tc.risk_level,
                "duration_ms": tc.duration_ms,
            }
            for tc in tool_calls
        ],
        "model_call_count": len(model_calls),
        "assignment_count": len(assignments),
        "step_count": len(assignments),
    }
    expected_json = request.expected_json or {"status": task.status}
    grounding_selectors = _grounding_selectors_for_run(session, task)
    if grounding_selectors:
        existing_contract = expected_json.get("grounding_contract")
        expected_json = {
            **expected_json,
            "grounding_contract": _merge_grounding_contract_selectors(
                existing_contract if isinstance(existing_contract, dict) else {},
                grounding_selectors,
            ),
        }
    eval_case = EvalCase(
        dataset_id=dataset.id,
        source_task_id=task.id,
        capability_snapshot_json=task.capability_snapshot_json,
        input_json={
            "task_id": task.id,
            "title": task.title,
            "goal": task.goal,
            "model_provider": task.model_provider,
            "model_name": task.model_name,
            "status": task.status,
        },
        expected_json={**expected_json, "execution_trace": execution_trace},
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
    return _eval_case_response(eval_case)


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
    return EvalCasePage(items=[_eval_case_response(eval_case) for eval_case in cases])


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
        capability_snapshot_json=_eval_run_capability_snapshot(
            session=session,
            organization_id=principal.organization_id,
            agent_id=request.agent_id,
        ),
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


@router.patch(
    "/datasets/{dataset_id}/baseline",
    response_model=EvalDatasetResponse,
    summary="设置基线 Eval Run",
    description="将指定 Eval Run 设为 Dataset 的基线，用于回归对比。",
)
def set_baseline(
    dataset_id: str,
    request: SetBaselineRequest,
    session: DbSession,
    principal: Principal,
) -> EvalDatasetResponse:
    dataset = _get_dataset(dataset_id, session, principal.organization_id)
    eval_run = session.execute(
        select(EvalRun).where(
            EvalRun.id == request.eval_run_id,
            EvalRun.organization_id == principal.organization_id,
        )
    ).scalar_one_or_none()
    if eval_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eval Run 未找到")
    if eval_run.dataset_id != dataset.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Eval Run 不属于该 Dataset",
        )
    dataset.baseline_run_id = eval_run.id
    dataset.updated_at = utc_now()
    _audit(
        session,
        principal=principal,
        event_type=EventType.EVAL_RUN_COMPLETED,
        resource_type="eval_dataset",
        resource_id=dataset.id,
        action="set_baseline",
        payload={"dataset_id": dataset.id, "baseline_run_id": eval_run.id},
    )
    session.commit()
    session.refresh(dataset)
    case_count = _case_counts(session, [dataset.id]).get(dataset.id, 0)
    return _dataset_response(dataset, case_count=case_count)


@router.get(
    "/runs/{eval_run_id}/regression",
    response_model=RegressionDelta | None,
    summary="查询回归 Delta",
    description="对比当前 Eval Run 与基线 Run 的指标差异，返回回归信息。",
)
def get_regression_delta(
    eval_run_id: str,
    session: DbSession,
    principal: Principal,
) -> RegressionDelta | None:
    eval_run = session.execute(
        select(EvalRun).where(
            EvalRun.id == eval_run_id,
            EvalRun.organization_id == principal.organization_id,
        )
    ).scalar_one_or_none()
    if eval_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eval Run 未找到")
    dataset = session.get(EvalDataset, eval_run.dataset_id)
    if dataset is None or dataset.baseline_run_id is None:
        return None
    if dataset.baseline_run_id == eval_run.id:
        return None
    baseline_run = session.get(EvalRun, dataset.baseline_run_id)
    if baseline_run is None:
        return None
    baseline_results = list(
        session.execute(
            select(EvalResult).where(EvalResult.eval_run_id == baseline_run.id)
        ).scalars()
    )
    current_results = list(
        session.execute(select(EvalResult).where(EvalResult.eval_run_id == eval_run.id)).scalars()
    )
    baseline_metrics = _aggregate_metrics(baseline_results)
    current_metrics = _aggregate_metrics(current_results)
    baseline_case_status = {r.eval_case_id: r.status for r in baseline_results}
    current_case_status = {r.eval_case_id: r.status for r in current_results}
    baseline_grounding_pass = {
        r.eval_case_id: bool(_normalize_grounding_trace(r.grader_trace_json).get("passed"))
        for r in baseline_results
    }
    current_grounding_pass = {
        r.eval_case_id: bool(_normalize_grounding_trace(r.grader_trace_json).get("passed"))
        for r in current_results
    }
    baseline_forbidden_leak = {
        r.eval_case_id: bool(
            _normalize_grounding_trace(r.grader_trace_json).get("forbidden_evidence_leaked")
        )
        for r in baseline_results
    }
    current_forbidden_leak = {
        r.eval_case_id: bool(
            _normalize_grounding_trace(r.grader_trace_json).get("forbidden_evidence_leaked")
        )
        for r in current_results
    }
    newly_failing = [
        case_id
        for case_id, cur_status in current_case_status.items()
        if cur_status == "FAILED" and baseline_case_status.get(case_id) == "PASSED"
    ]
    newly_passing = [
        case_id
        for case_id, cur_status in current_case_status.items()
        if cur_status == "PASSED" and baseline_case_status.get(case_id) == "FAILED"
    ]
    newly_grounding_failing = [
        case_id
        for case_id, cur_passed in current_grounding_pass.items()
        if not cur_passed and baseline_grounding_pass.get(case_id) is True
    ]
    newly_forbidden_leak = [
        case_id
        for case_id, cur_leaked in current_forbidden_leak.items()
        if cur_leaked and baseline_forbidden_leak.get(case_id) is not True
    ]
    task_success_rate_delta = round(
        current_metrics.get("task_success_rate", 0) - baseline_metrics.get("task_success_rate", 0),
        4,
    )
    tool_selection_accuracy_delta = round(
        current_metrics.get("tool_selection_accuracy", 0)
        - baseline_metrics.get("tool_selection_accuracy", 0),
        4,
    )
    avg_latency_ms_delta = int(
        current_metrics.get("avg_latency_ms", 0) - baseline_metrics.get("avg_latency_ms", 0)
    )
    grounding_pass_rate_delta = _metric_delta(
        current_metrics, baseline_metrics, "grounding_pass_rate"
    )
    citation_coverage_rate_delta = _metric_delta(
        current_metrics, baseline_metrics, "citation_coverage_rate"
    )
    unsupported_marker_rate_delta = _metric_delta(
        current_metrics, baseline_metrics, "unsupported_marker_rate"
    )
    fallback_mismatch_rate_delta = _metric_delta(
        current_metrics, baseline_metrics, "fallback_mismatch_rate"
    )
    forbidden_evidence_leak_rate_delta = _metric_delta(
        current_metrics, baseline_metrics, "forbidden_evidence_leak_rate"
    )
    required_evidence_miss_rate_delta = _metric_delta(
        current_metrics, baseline_metrics, "required_evidence_miss_rate"
    )
    forbidden_evidence_leak_rate = float(current_metrics.get("forbidden_evidence_leak_rate", 0))
    passed_cases = sum(1 for r in current_results if r.status == "PASSED")
    failed_cases = sum(1 for r in current_results if r.status == "FAILED")
    low_sample_count = len(current_results) < LOW_GROUNDING_SAMPLE_THRESHOLD
    return RegressionDelta(
        baseline_run_id=baseline_run.id,
        current_run_id=eval_run.id,
        task_success_rate_delta=task_success_rate_delta,
        tool_selection_accuracy_delta=tool_selection_accuracy_delta,
        avg_latency_ms_delta=avg_latency_ms_delta,
        grounding_pass_rate_delta=grounding_pass_rate_delta,
        citation_coverage_rate_delta=citation_coverage_rate_delta,
        unsupported_marker_rate_delta=unsupported_marker_rate_delta,
        fallback_mismatch_rate_delta=fallback_mismatch_rate_delta,
        forbidden_evidence_leak_rate_delta=forbidden_evidence_leak_rate_delta,
        required_evidence_miss_rate_delta=required_evidence_miss_rate_delta,
        newly_failing_case_ids=newly_failing,
        newly_passing_case_ids=newly_passing,
        newly_grounding_failing_case_ids=newly_grounding_failing,
        newly_forbidden_leak_case_ids=newly_forbidden_leak,
        is_regression=(
            task_success_rate_delta < TASK_SUCCESS_RATE_REGRESSION_THRESHOLD
            or grounding_pass_rate_delta < GROUNDING_PASS_RATE_REGRESSION_THRESHOLD
            or forbidden_evidence_leak_rate > 0
            or bool(newly_forbidden_leak)
            or unsupported_marker_rate_delta > QUALITY_RATE_REGRESSION_THRESHOLD
            or fallback_mismatch_rate_delta > QUALITY_RATE_REGRESSION_THRESHOLD
        ),
        total_cases=len(current_results),
        passed_cases=passed_cases,
        failed_cases=failed_cases,
        grounding_sample_count=len(current_results),
        low_sample_count=low_sample_count,
        low_sample_caveat=(
            "Grounding trend confidence is low for fewer than "
            f"{LOW_GROUNDING_SAMPLE_THRESHOLD} cases."
            if low_sample_count
            else None
        ),
    )


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
        baseline_run_id=dataset.baseline_run_id,
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
    grounding_trace = _grade_grounding_contract(session, task, eval_case.expected_json)
    score = 1.0 if status_match and not failed_tools and grounding_trace["passed"] else 0.0
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
            **grounding_trace,
        },
        latency_ms=latency_ms,
        cost_usd="0",
        error_message=(
            None
            if result_status == "PASSED"
            else "Trace did not satisfy expected status, tool, or grounding checks"
        ),
        created_at=utc_now(),
    )


def _grade_grounding_contract(session: Session, task: Task | None, expected_json: dict) -> dict:
    contract = expected_json.get("grounding_contract")
    if not isinstance(contract, dict):
        return _grounding_trace_v1(
            grader="deterministic_trace_grader_v1",
            passed=True,
        )
    if task is None:
        return _grounding_trace_v1(
            grader="deterministic_grounding_grader_v1",
            passed=False,
            grounding_failures=["missing_task"],
        )

    requested_prompt_manifest_id = contract.get("prompt_manifest_id")
    requested_retrieval_session_id = contract.get("retrieval_session_id")
    inferred_fallback = False
    fallback_reason = None
    prompt_manifest: PromptAssemblyManifest | None = None
    if requested_prompt_manifest_id:
        prompt_manifest = session.get(PromptAssemblyManifest, str(requested_prompt_manifest_id))
        if prompt_manifest is None or prompt_manifest.run_id != task.id:
            return _grounding_trace_v1(
                grader="deterministic_grounding_grader_v1",
                passed=False,
                grounding_failures=["missing_prompt_manifest"],
                inferred_fallback=False,
                prompt_manifest_id=str(requested_prompt_manifest_id),
            )
        if requested_retrieval_session_id and prompt_manifest.retrieval_session_id != str(
            requested_retrieval_session_id
        ):
            return _grounding_trace_v1(
                grader="deterministic_grounding_grader_v1",
                passed=False,
                grounding_failures=["selector_conflict"],
                inferred_fallback=False,
                retrieval_session_id=str(requested_retrieval_session_id),
                prompt_manifest_id=prompt_manifest.id,
            )
        retrieval_session = session.get(RetrievalSession, prompt_manifest.retrieval_session_id)
    elif requested_retrieval_session_id:
        retrieval_session = session.get(RetrievalSession, str(requested_retrieval_session_id))
        if retrieval_session is not None and retrieval_session.run_id != task.id:
            retrieval_session = None
    else:
        inferred_fallback = True
        fallback_reason = "latest_run_retrieval_session"
        retrieval_session = session.execute(
            select(RetrievalSession)
            .where(RetrievalSession.run_id == task.id)
            .order_by(RetrievalSession.created_at.desc(), RetrievalSession.id.desc())
            .limit(1)
        ).scalar_one_or_none()
    failures: list[str] = []
    if retrieval_session is None:
        return _grounding_trace_v1(
            grader="deterministic_grounding_grader_v1",
            passed=False,
            grounding_failures=["missing_retrieval_session"],
            inferred_fallback=inferred_fallback,
            fallback_reason=fallback_reason,
        )

    hits = list(
        session.execute(
            select(RetrievalHit).where(RetrievalHit.retrieval_session_id == retrieval_session.id)
        ).scalars()
    )
    citations = list(
        session.execute(
            select(CitationRecord).where(
                CitationRecord.retrieval_session_id == retrieval_session.id
            )
        ).scalars()
    )
    web_sources = list(
        session.execute(
            select(WebResearchSource).where(
                WebResearchSource.retrieval_session_id == retrieval_session.id
            )
        ).scalars()
    )
    if prompt_manifest is None:
        prompt_manifest = session.execute(
            select(PromptAssemblyManifest)
            .where(PromptAssemblyManifest.retrieval_session_id == retrieval_session.id)
            .limit(1)
        ).scalar_one_or_none()
    policy_audits = list(
        session.execute(
            select(KnowledgePolicyAudit).where(
                KnowledgePolicyAudit.retrieval_session_id == retrieval_session.id
            )
        ).scalars()
    )
    model_calls = list(
        session.execute(select(ModelCall).where(ModelCall.task_id == task.id)).scalars()
    )
    outcome_source = (
        prompt_manifest.metadata_json
        if prompt_manifest is not None and isinstance(prompt_manifest.metadata_json, dict)
        else retrieval_session.metadata_json
        if isinstance(retrieval_session.metadata_json, dict)
        else {}
    )
    grounding_provider = str(outcome_source.get("grounding_provider") or "none")
    fixture_grounded = bool(outcome_source.get("fixture_grounded") or False)
    verified_grounded = bool(outcome_source.get("verified_grounded") or False)
    grounding_verification_reason = str(
        outcome_source.get("grounding_verification_reason") or "no_verified_evidence"
    )

    if contract.get("require_grounded"):
        allow_fixture_grounding = bool(contract.get("allow_fixture_grounding") or False)
        grounded = bool(citations) and (
            verified_grounded or (allow_fixture_grounding and fixture_grounded)
        )
        if not grounded or not hits:
            failures.append("missing_grounded_hits_or_citations")
        elif prompt_manifest is not None:
            included_hit_ids = set(prompt_manifest.included_retrieval_hit_ids_json)
            citation_hit_ids = {citation.retrieval_hit_id for citation in citations}
            if not citation_hit_ids <= included_hit_ids:
                failures.append("citation_hits_not_in_prompt_manifest")
    if contract.get("require_insufficient") and retrieval_session.local_status != "insufficient":
        failures.append("missing_insufficient_status")
    if contract.get("require_prompt_manifest") and prompt_manifest is None:
        failures.append("missing_prompt_manifest")
    required_decisions = set(contract.get("require_policy_decisions") or [])
    actual_decisions = {audit.decision for audit in policy_audits}
    if not required_decisions <= actual_decisions:
        failures.append("missing_policy_decisions")

    actual_hit_ids = [hit.id for hit in hits]
    actual_citation_keys = [citation.citation_key for citation in citations]
    actual_citation_hit_ids = [citation.retrieval_hit_id for citation in citations]
    expected_hit_ids = _as_string_list(contract.get("hit_ids"))
    expected_citation_keys = _as_string_list(contract.get("citation_keys"))
    expected_hit_id_set = set(expected_hit_ids)
    if expected_hit_id_set and not expected_hit_id_set <= set(actual_hit_ids):
        failures.append("missing_required_evidence")
    if expected_citation_keys and not set(expected_citation_keys) <= set(actual_citation_keys):
        failures.append("citation_hit_mismatch")
    expected_citation_hit_ids = _as_string_list(contract.get("citation_hit_ids"))
    if expected_citation_hit_ids and not set(expected_citation_hit_ids) <= set(
        actual_citation_hit_ids
    ):
        failures.append("citation_hit_mismatch")
    if expected_hit_id_set:
        required_citation_hit_ids = {
            citation.retrieval_hit_id
            for citation in citations
            if not expected_citation_keys or citation.citation_key in expected_citation_keys
        }
        if not required_citation_hit_ids or not required_citation_hit_ids <= expected_hit_id_set:
            failures.append("citation_hit_mismatch")

    evidence_inputs = _grounding_evidence_inputs(
        hits=hits,
        prompt_manifest=prompt_manifest,
        citations=citations,
        policy_audits=policy_audits,
        model_calls=model_calls,
    )
    required_evidence_snippets = _as_string_list(contract.get("required_evidence_snippets"))
    missing_required_snippets = [
        snippet
        for snippet in required_evidence_snippets
        if not _snippet_in_inputs(snippet, evidence_inputs)
    ]
    if missing_required_snippets:
        failures.append("missing_required_evidence")

    forbidden_evidence_snippets = _as_string_list(contract.get("forbidden_evidence_snippets"))
    legacy_forbidden = _normalize_text(contract.get("forbid_text") or "")
    if legacy_forbidden:
        forbidden_evidence_snippets.append(legacy_forbidden)
    forbidden_leak_sources = _matched_input_sources(forbidden_evidence_snippets, evidence_inputs)
    forbidden_evidence_leaked = bool(forbidden_leak_sources)
    if forbidden_evidence_leaked:
        failures.append("forbidden_evidence_leaked")

    unsupported_markers = _as_string_list(contract.get("unsupported_markers"))
    unsupported_marker_sources = _matched_input_sources(
        unsupported_markers,
        {
            "citations": evidence_inputs.get("citations", ""),
            "prompt_manifest": evidence_inputs.get("prompt_manifest", ""),
            "policy_audits": evidence_inputs.get("policy_audits", ""),
        },
    )
    if unsupported_marker_sources:
        failures.append("unsupported_marker_present")

    fallback_expected = bool(contract.get("fallback_expected") or False)
    fallback_observed = _fallback_observed(retrieval_session, web_sources, outcome_source)
    if fallback_expected and not fallback_observed:
        failures.append("fallback_expected_but_not_observed")
    if fallback_observed and not fallback_expected and "fallback_expected" in contract:
        failures.append("fallback_observed_but_not_expected")

    return _grounding_trace_v1(
        grader="deterministic_grounding_grader_v1",
        passed=not failures,
        grounding_failures=_dedupe(failures),
        retrieval_session_id=retrieval_session.id,
        prompt_manifest_id=prompt_manifest.id if prompt_manifest else None,
        policy_audit_ids=[audit.id for audit in policy_audits],
        hit_ids=actual_hit_ids,
        citation_keys=actual_citation_keys,
        citation_hit_ids=actual_citation_hit_ids,
        required_evidence_snippets=required_evidence_snippets,
        forbidden_evidence_snippets=forbidden_evidence_snippets,
        forbidden_evidence_leaked=forbidden_evidence_leaked,
        forbidden_leak_sources=forbidden_leak_sources,
        fallback_expected=fallback_expected,
        fallback_observed=fallback_observed,
        fallback_reason=fallback_reason,
        unsupported_markers=unsupported_markers,
        inferred_fallback=inferred_fallback,
        grounding_provider=grounding_provider,
        fixture_grounded=fixture_grounded,
        verified_grounded=verified_grounded,
        grounding_verification_reason=grounding_verification_reason,
        hit_count=len(hits),
        citation_count=len(citations),
        web_source_count=len(web_sources),
    )


def _grounding_selectors_for_run(session: Session, task: Task) -> dict:
    prompt_manifest = session.execute(
        select(PromptAssemblyManifest)
        .where(PromptAssemblyManifest.run_id == task.id)
        .order_by(PromptAssemblyManifest.created_at.desc(), PromptAssemblyManifest.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    retrieval_session = None
    if prompt_manifest is not None:
        retrieval_session = session.get(RetrievalSession, prompt_manifest.retrieval_session_id)
    if retrieval_session is None:
        retrieval_session = session.execute(
            select(RetrievalSession)
            .where(RetrievalSession.run_id == task.id)
            .order_by(RetrievalSession.created_at.desc(), RetrievalSession.id.desc())
            .limit(1)
        ).scalar_one_or_none()
    if retrieval_session is None:
        return {}
    if prompt_manifest is None:
        prompt_manifest = session.execute(
            select(PromptAssemblyManifest)
            .where(PromptAssemblyManifest.retrieval_session_id == retrieval_session.id)
            .order_by(PromptAssemblyManifest.created_at.desc(), PromptAssemblyManifest.id.desc())
            .limit(1)
        ).scalar_one_or_none()

    hits = list(
        session.execute(
            select(RetrievalHit)
            .where(RetrievalHit.retrieval_session_id == retrieval_session.id)
            .order_by(RetrievalHit.rank.asc(), RetrievalHit.id.asc())
        ).scalars()
    )
    citations = list(
        session.execute(
            select(CitationRecord)
            .where(CitationRecord.retrieval_session_id == retrieval_session.id)
            .order_by(CitationRecord.created_at.asc(), CitationRecord.id.asc())
        ).scalars()
    )
    policy_audits = list(
        session.execute(
            select(KnowledgePolicyAudit).where(
                KnowledgePolicyAudit.retrieval_session_id == retrieval_session.id
            )
        ).scalars()
    )
    web_sources = list(
        session.execute(
            select(WebResearchSource).where(
                WebResearchSource.retrieval_session_id == retrieval_session.id
            )
        ).scalars()
    )
    outcome_source = (
        prompt_manifest.metadata_json
        if prompt_manifest is not None and isinstance(prompt_manifest.metadata_json, dict)
        else retrieval_session.metadata_json
        if isinstance(retrieval_session.metadata_json, dict)
        else {}
    )
    citation_keys = _dedupe([citation.citation_key for citation in citations])
    citation_hit_ids = _dedupe([citation.retrieval_hit_id for citation in citations])
    retrieval_hit_ids = _dedupe([hit.id for hit in hits])
    selectors: dict[str, object] = {
        "retrieval_session_id": retrieval_session.id,
        "hit_ids": citation_hit_ids or retrieval_hit_ids,
        "citation_keys": citation_keys,
        "citation_hit_ids": citation_hit_ids,
        "fallback_expected": _fallback_observed(retrieval_session, web_sources, outcome_source),
        "require_grounded": bool(citations),
        "require_insufficient": retrieval_session.local_status != "sufficient",
        "allow_fixture_grounding": False,
    }
    if prompt_manifest is not None:
        selectors["prompt_manifest_id"] = prompt_manifest.id
        selectors["require_prompt_manifest"] = True
    policy_decisions = _dedupe([audit.decision for audit in policy_audits])
    if policy_decisions:
        selectors["require_policy_decisions"] = policy_decisions
    return selectors


def _merge_grounding_contract_selectors(existing: dict, selectors: dict) -> dict:
    merged = {**selectors, **existing}
    for key in ("hit_ids", "citation_keys", "citation_hit_ids", "require_policy_decisions"):
        if not _as_string_list(merged.get(key)) and _as_string_list(selectors.get(key)):
            merged[key] = selectors[key]
    for key in ("retrieval_session_id", "prompt_manifest_id"):
        if not merged.get(key) and selectors.get(key):
            merged[key] = selectors[key]
    for key in (
        "fallback_expected",
        "require_grounded",
        "require_prompt_manifest",
        "require_insufficient",
        "allow_fixture_grounding",
    ):
        if key not in existing and key in selectors:
            merged[key] = selectors[key]
    return merged


def _grounding_trace_v1(
    *,
    grader: str,
    passed: bool,
    grounding_failures: list[str] | None = None,
    retrieval_session_id: str | None = None,
    prompt_manifest_id: str | None = None,
    policy_audit_ids: list[str] | None = None,
    hit_ids: list[str] | None = None,
    citation_keys: list[str] | None = None,
    citation_hit_ids: list[str] | None = None,
    required_evidence_snippets: list[str] | None = None,
    forbidden_evidence_snippets: list[str] | None = None,
    forbidden_evidence_leaked: bool = False,
    forbidden_leak_sources: list[str] | None = None,
    fallback_expected: bool = False,
    fallback_observed: bool = False,
    fallback_reason: str | None = None,
    unsupported_markers: list[str] | None = None,
    claim_checks: list[dict] | None = None,
    **extra: object,
) -> dict:
    trace = {
        "grader_trace_schema_version": GROUNDING_TRACE_SCHEMA_VERSION,
        "grader": grader,
        "passed": passed,
        "grounding_failures": _dedupe(grounding_failures or []),
        "retrieval_session_id": retrieval_session_id,
        "prompt_manifest_id": prompt_manifest_id,
        "policy_audit_ids": policy_audit_ids or [],
        "hit_ids": hit_ids or [],
        "citation_keys": citation_keys or [],
        "citation_hit_ids": citation_hit_ids or [],
        "required_evidence_snippets": required_evidence_snippets or [],
        "forbidden_evidence_snippets": forbidden_evidence_snippets or [],
        "forbidden_evidence_leaked": forbidden_evidence_leaked,
        "forbidden_leak_sources": forbidden_leak_sources or [],
        "fallback_expected": fallback_expected,
        "fallback_observed": fallback_observed,
        "fallback_reason": fallback_reason,
        "unsupported_markers": unsupported_markers or [],
        "claim_checks": claim_checks or [],
    }
    trace.update(extra)
    return _normalize_grounding_trace(trace)


def _normalize_grounding_trace(trace: dict | None) -> dict:
    raw = trace if isinstance(trace, dict) else {}
    failures = _as_string_list(raw.get("grounding_failures"))
    forbidden_leak_sources = _as_string_list(raw.get("forbidden_leak_sources"))
    forbidden_evidence_leaked = bool(raw.get("forbidden_evidence_leaked")) or bool(
        forbidden_leak_sources
    )
    fallback_expected = bool(raw.get("fallback_expected") or False)
    fallback_observed = bool(raw.get("fallback_observed") or False)
    normalized = {
        **raw,
        "grader_trace_schema_version": int(raw.get("grader_trace_schema_version") or 0),
        "grader": str(raw.get("grader") or "deterministic_trace_grader_v1"),
        "passed": bool(raw.get("passed", True)),
        "grounding_failures": failures,
        "retrieval_session_id": _nullable_str(raw.get("retrieval_session_id")),
        "prompt_manifest_id": _nullable_str(raw.get("prompt_manifest_id")),
        "policy_audit_ids": _as_string_list(raw.get("policy_audit_ids")),
        "hit_ids": _as_string_list(raw.get("hit_ids")),
        "citation_keys": _as_string_list(raw.get("citation_keys")),
        "citation_hit_ids": _as_string_list(raw.get("citation_hit_ids")),
        "required_evidence_snippets": _as_string_list(raw.get("required_evidence_snippets")),
        "forbidden_evidence_snippets": _as_string_list(raw.get("forbidden_evidence_snippets")),
        "forbidden_evidence_leaked": forbidden_evidence_leaked,
        "forbidden_leak_sources": forbidden_leak_sources,
        "fallback_expected": fallback_expected,
        "fallback_observed": fallback_observed,
        "fallback_reason": _nullable_str(raw.get("fallback_reason")),
        "unsupported_markers": _as_string_list(raw.get("unsupported_markers")),
        "claim_checks": (
            raw.get("claim_checks") if isinstance(raw.get("claim_checks"), list) else []
        ),
    }
    if forbidden_evidence_leaked and "forbidden_evidence_leaked" not in failures:
        normalized["grounding_failures"] = [*failures, "forbidden_evidence_leaked"]
        normalized["passed"] = False
    return normalized


def _grounding_evidence_inputs(
    *,
    hits: list[RetrievalHit],
    prompt_manifest: PromptAssemblyManifest | None,
    citations: list[CitationRecord],
    policy_audits: list[KnowledgePolicyAudit],
    model_calls: list[ModelCall],
) -> dict[str, str]:
    prompt_payload = ""
    if prompt_manifest is not None:
        prompt_payload = _json_text(
            {
                "included_retrieval_hit_ids": prompt_manifest.included_retrieval_hit_ids_json,
                "omitted_candidates": prompt_manifest.omitted_candidates_json,
                "source_snapshots": prompt_manifest.source_snapshots_json,
                "prompt_sections": prompt_manifest.prompt_sections_json,
                "evidence_text_sha256": prompt_manifest.evidence_text_sha256,
                "metadata": prompt_manifest.metadata_json,
            }
        )
    return {
        "retrieval_hits": _json_text(
            [
                {
                    "id": hit.id,
                    "chunk_id": hit.chunk_id,
                    "web_source_id": hit.web_source_id,
                    "source_kind": hit.source_kind,
                    "snippet": hit.snippet,
                    "metadata": hit.metadata_json,
                }
                for hit in hits
            ]
        ),
        "prompt_manifest": prompt_payload,
        "citations": _json_text(
            [
                {
                    "id": citation.id,
                    "retrieval_hit_id": citation.retrieval_hit_id,
                    "citation_key": citation.citation_key,
                    "claim_text": citation.claim_text,
                    "quoted_text": citation.quoted_text,
                    "metadata": citation.metadata_json,
                }
                for citation in citations
            ]
        ),
        "policy_audits": _json_text(
            [
                {
                    "id": audit.id,
                    "decision": audit.decision,
                    "reason": audit.reason,
                    "source_kind": audit.source_kind,
                    "source_ref_id": audit.source_ref_id,
                    "safe_metadata": audit.safe_metadata_json,
                }
                for audit in policy_audits
            ]
        ),
        "model_call_binding_metadata": _json_text(
            [
                {
                    "id": model_call.id,
                    "prompt_manifest_id": model_call.prompt_manifest_id,
                    "context_manifest_id": model_call.context_manifest_id,
                    "grounding_correlation_id": model_call.grounding_correlation_id,
                    "model_request_sha256": model_call.model_request_sha256,
                    "request_message_hashes_json": model_call.request_message_hashes_json,
                    "request_message_hashes_sha256": model_call.request_message_hashes_sha256,
                    "hash_recomputability_status": model_call.hash_recomputability_status,
                }
                for model_call in model_calls
            ]
        ),
    }


def _fallback_observed(
    retrieval_session: RetrievalSession,
    web_sources: list[WebResearchSource],
    outcome_source: dict,
) -> bool:
    if retrieval_session.mode in {"web", "web_fallback", "fallback"}:
        return True
    if web_sources:
        return True
    if bool(outcome_source.get("web_fallback_observed") or outcome_source.get("fallback_observed")):
        return True
    return str(outcome_source.get("grounding_provider") or "").endswith("_web_fixture")


def _matched_input_sources(snippets: list[str], inputs: dict[str, str]) -> list[str]:
    sources: list[str] = []
    for source, payload in inputs.items():
        if any(_contains_snippet(payload, snippet) for snippet in snippets):
            sources.append(source)
    return sources


def _snippet_in_inputs(snippet: str, inputs: dict[str, str]) -> bool:
    return any(_contains_snippet(payload, snippet) for payload in inputs.values())


def _contains_snippet(payload: object, snippet: str) -> bool:
    normalized_snippet = _normalize_text(snippet)
    if not normalized_snippet:
        return False
    return normalized_snippet in _normalize_text(payload)


def _as_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [item for item in (_normalize_text(item) for item in value) if item]
    normalized = _normalize_text(value)
    return [normalized] if normalized else []


def _normalize_text(value: object) -> str:
    return str(value).replace("\r\n", "\n").replace("\r", "\n").strip()


def _nullable_str(value: object) -> str | None:
    normalized = _normalize_text(value or "")
    return normalized or None


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _metric_delta(current_metrics: dict, baseline_metrics: dict, key: str) -> float:
    return round(float(current_metrics.get(key, 0)) - float(baseline_metrics.get(key, 0)), 4)


def _aggregate_metrics(results: list[EvalResult]) -> dict:
    total = len(results) or 1
    traces = [_normalize_grounding_trace(result.grader_trace_json) for result in results]
    grounding_failures = [
        failure for trace in traces for failure in trace.get("grounding_failures", [])
    ]
    fallback_mismatches = [
        trace
        for trace in traces
        if bool(trace.get("fallback_expected")) != bool(trace.get("fallback_observed"))
    ]
    low_cost_guard_failures = [
        trace
        for trace in traces
        if trace.get("low_cost_route_used")
        and trace.get("passed")
        and not trace.get("low_cost_quality_guard_passed")
    ]
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
        "grounding_pass_rate": round(
            sum(1 for trace in traces if bool(trace.get("passed"))) / total,
            4,
        ),
        "citation_coverage_rate": round(
            sum(1 for trace in traces if "citation_hit_mismatch" not in trace["grounding_failures"])
            / total,
            4,
        ),
        "unsupported_marker_rate": round(
            sum(
                1
                for trace in traces
                if "unsupported_marker_present" in trace["grounding_failures"]
            )
            / total,
            4,
        ),
        "fallback_mismatch_rate": round(len(fallback_mismatches) / total, 4),
        "forbidden_evidence_leak_rate": round(
            sum(1 for trace in traces if bool(trace.get("forbidden_evidence_leaked"))) / total,
            4,
        ),
        "required_evidence_miss_rate": round(
            sum(1 for trace in traces if "missing_required_evidence" in trace["grounding_failures"])
            / total,
            4,
        ),
        "low_cost_route_guard_failure_rate": round(len(low_cost_guard_failures) / total, 4),
        "low_cost_route_guard_failure_total": len(low_cost_guard_failures),
        "grounding_failure_total": len(grounding_failures),
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
        capability_snapshot_json=eval_run.capability_snapshot_json,
        metrics_json=eval_run.metrics_json,
        created_by=eval_run.created_by,
        started_at=eval_run.started_at,
        completed_at=eval_run.completed_at,
        created_at=eval_run.created_at,
        results=[_eval_result_response(result) for result in results],
    )


def _eval_case_response(eval_case: EvalCase) -> EvalCaseResponse:
    return EvalCaseResponse(
        id=eval_case.id,
        dataset_id=eval_case.dataset_id,
        source_task_id=eval_case.source_task_id,
        input_json=_scrub_forbidden_evidence_snippets(eval_case.input_json),
        expected_json=_scrub_forbidden_evidence_snippets(eval_case.expected_json),
        capability_snapshot_json=_scrub_forbidden_evidence_snippets(
            eval_case.capability_snapshot_json
        ),
        tags_json=eval_case.tags_json,
        created_at=eval_case.created_at,
    )


def _eval_result_response(result: EvalResult) -> EvalResultResponse:
    return EvalResultResponse(
        id=result.id,
        eval_run_id=result.eval_run_id,
        eval_case_id=result.eval_case_id,
        task_id=result.task_id,
        status=result.status,
        scores_json=result.scores_json,
        grader_trace_json=_scrub_forbidden_evidence_snippets(result.grader_trace_json),
        latency_ms=result.latency_ms,
        cost_usd=result.cost_usd,
        error_message=result.error_message,
        created_at=result.created_at,
    )


def _scrub_forbidden_evidence_snippets(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _scrub_forbidden_evidence_snippets(item)
            for key, item in value.items()
            if key not in {"forbidden_evidence_snippet", "forbidden_evidence_snippets"}
        }
    if isinstance(value, list):
        return [_scrub_forbidden_evidence_snippets(item) for item in value]
    return value


def _eval_run_capability_snapshot(
    *,
    session: Session,
    organization_id: str,
    agent_id: str | None,
) -> dict:
    if agent_id is None:
        return {}
    ensure_default_agents(session, organization_id)
    _registry, snapshot = CapabilityRegistry(session, organization_id).tool_registry_for_agent(
        agent_id
    )
    return snapshot


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
