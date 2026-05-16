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
        expected_json={
            **(request.expected_json or {"status": task.status}),
            "execution_trace": execution_trace,
        },
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
        session.execute(
            select(EvalResult).where(EvalResult.eval_run_id == eval_run.id)
        ).scalars()
    )
    baseline_metrics = _aggregate_metrics(baseline_results)
    current_metrics = _aggregate_metrics(current_results)
    baseline_case_status = {r.eval_case_id: r.status for r in baseline_results}
    current_case_status = {r.eval_case_id: r.status for r in current_results}
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
    passed_cases = sum(1 for r in current_results if r.status == "PASSED")
    failed_cases = sum(1 for r in current_results if r.status == "FAILED")
    return RegressionDelta(
        baseline_run_id=baseline_run.id,
        current_run_id=eval_run.id,
        task_success_rate_delta=task_success_rate_delta,
        tool_selection_accuracy_delta=tool_selection_accuracy_delta,
        avg_latency_ms_delta=avg_latency_ms_delta,
        newly_failing_case_ids=newly_failing,
        newly_passing_case_ids=newly_passing,
        is_regression=task_success_rate_delta < -0.10,
        total_cases=len(current_results),
        passed_cases=passed_cases,
        failed_cases=failed_cases,
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
        return {"grader": "deterministic_trace_grader_v1", "passed": True}
    if task is None:
        return {
            "grader": "deterministic_grounding_grader_v1",
            "passed": False,
            "grounding_failures": ["missing_task"],
        }

    retrieval_session = session.execute(
        select(RetrievalSession)
        .where(RetrievalSession.run_id == task.id)
        .order_by(RetrievalSession.created_at.desc(), RetrievalSession.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    failures: list[str] = []
    if retrieval_session is None:
        return {
            "grader": "deterministic_grounding_grader_v1",
            "passed": False,
            "grounding_failures": ["missing_retrieval_session"],
        }

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

    if contract.get("require_grounded"):
        if retrieval_session.local_status != "sufficient" or not hits or not citations:
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
    forbidden_text = str(contract.get("forbid_text") or "")
    if forbidden_text:
        manifest_payload = (
            str(prompt_manifest.omitted_candidates_json)
            + str(prompt_manifest.source_snapshots_json)
            + str(prompt_manifest.prompt_sections_json)
            if prompt_manifest is not None
            else ""
        )
        citation_payload = "".join(str(citation.quoted_text or "") for citation in citations)
        audit_payload = "".join(str(audit.safe_metadata_json) for audit in policy_audits)
        leaked = (
            forbidden_text in manifest_payload
            or forbidden_text in citation_payload
            or forbidden_text in audit_payload
        )
        if leaked:
            failures.append("forbidden_text_leaked")

    return {
        "grader": "deterministic_grounding_grader_v1",
        "passed": not failures,
        "grounding_failures": failures,
        "retrieval_session_id": retrieval_session.id,
        "prompt_manifest_id": prompt_manifest.id if prompt_manifest else None,
        "policy_audit_ids": [audit.id for audit in policy_audits],
    }


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
