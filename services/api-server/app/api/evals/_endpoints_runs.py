"""Eval API route handlers."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *
from .aggregations import *
from .graders import *
from .helpers import *
from .regression import *
from app.api.pagination import cursor_paginate


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

    results = [
        _grade_case(session, eval_run.id, eval_case, principal.organization_id)
        for eval_case in cases
    ]
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
    cursor: str | None = None,
) -> EvalRunPage:
    page = cursor_paginate(
        session=session,
        statement=select(EvalRun).where(EvalRun.organization_id == principal.organization_id),
        model=EvalRun,
        cursor=cursor,
        limit=limit,
    )
    return EvalRunPage(
        items=[_eval_run_response(run, []) for run in page.items],
        next_cursor=page.next_cursor,
    )


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
    tool_contract_pass_rate_delta = _metric_delta(
        current_metrics, baseline_metrics, "tool_contract_pass_rate"
    )
    dialogue_contract_pass_rate_delta = _metric_delta(
        current_metrics, baseline_metrics, "dialogue_contract_pass_rate"
    )
    cost_contract_pass_rate_delta = _metric_delta(
        current_metrics, baseline_metrics, "cost_contract_pass_rate"
    )
    refusal_contract_pass_rate_delta = _metric_delta(
        current_metrics, baseline_metrics, "refusal_contract_pass_rate"
    )
    safety_contract_pass_rate_delta = _metric_delta(
        current_metrics, baseline_metrics, "safety_contract_pass_rate"
    )
    persona_contract_pass_rate_delta = _metric_delta(
        current_metrics, baseline_metrics, "persona_contract_pass_rate"
    )
    specialist_contract_pass_rate_delta = _metric_delta(
        current_metrics, baseline_metrics, "specialist_contract_pass_rate"
    )
    overrefusal_rate_delta = _metric_delta(current_metrics, baseline_metrics, "overrefusal_rate")
    safety_violation_total_delta = int(
        current_metrics.get("safety_violation_total", 0)
    ) - int(baseline_metrics.get("safety_violation_total", 0))
    role_drift_total_delta = int(current_metrics.get("role_drift_total", 0)) - int(
        baseline_metrics.get("role_drift_total", 0)
    )
    avg_cost_usd_delta = _cost_metric_delta(current_metrics, baseline_metrics, "avg_cost_usd")
    total_cost_usd_delta = _cost_metric_delta(current_metrics, baseline_metrics, "total_cost_usd")
    total_prompt_tokens_delta = int(current_metrics.get("total_prompt_tokens", 0)) - int(
        baseline_metrics.get("total_prompt_tokens", 0)
    )
    total_completion_tokens_delta = int(current_metrics.get("total_completion_tokens", 0)) - int(
        baseline_metrics.get("total_completion_tokens", 0)
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
        tool_contract_pass_rate_delta=tool_contract_pass_rate_delta,
        dialogue_contract_pass_rate_delta=dialogue_contract_pass_rate_delta,
        cost_contract_pass_rate_delta=cost_contract_pass_rate_delta,
        refusal_contract_pass_rate_delta=refusal_contract_pass_rate_delta,
        safety_contract_pass_rate_delta=safety_contract_pass_rate_delta,
        persona_contract_pass_rate_delta=persona_contract_pass_rate_delta,
        specialist_contract_pass_rate_delta=specialist_contract_pass_rate_delta,
        overrefusal_rate_delta=overrefusal_rate_delta,
        safety_violation_total_delta=safety_violation_total_delta,
        role_drift_total_delta=role_drift_total_delta,
        avg_cost_usd_delta=avg_cost_usd_delta,
        total_cost_usd_delta=total_cost_usd_delta,
        total_prompt_tokens_delta=total_prompt_tokens_delta,
        total_completion_tokens_delta=total_completion_tokens_delta,
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
            or tool_contract_pass_rate_delta < CONTRACT_PASS_RATE_REGRESSION_THRESHOLD
            or cost_contract_pass_rate_delta < CONTRACT_PASS_RATE_REGRESSION_THRESHOLD
            or dialogue_contract_pass_rate_delta < CONTRACT_PASS_RATE_REGRESSION_THRESHOLD
            or refusal_contract_pass_rate_delta < CONTRACT_PASS_RATE_REGRESSION_THRESHOLD
            or safety_contract_pass_rate_delta < SAFETY_PASS_RATE_REGRESSION_THRESHOLD
            or safety_violation_total_delta > 0
            or persona_contract_pass_rate_delta < CONTRACT_PASS_RATE_REGRESSION_THRESHOLD
            or specialist_contract_pass_rate_delta < CONTRACT_PASS_RATE_REGRESSION_THRESHOLD
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


__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
