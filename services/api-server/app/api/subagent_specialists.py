from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agents.specialists import (
    SpecialistValidationError,
    SubagentSpecialistRegistry,
    compute_specialist_stats,
    ensure_system_specialists,
    normalize_budget,
    output_schema_sha256,
    validate_output_schema,
)
from app.api.schemas import (
    SpecialistCalibrationBucket,
    SpecialistCalibrationReport,
    SubagentSpecialistCreateRequest,
    SubagentSpecialistPage,
    SubagentSpecialistPreflightRequest,
    SubagentSpecialistPreflightResponse,
    SubagentSpecialistResponse,
    SubagentSpecialistStats,
    SubagentSpecialistUpdateRequest,
)
from app.db.models import AgentRun, SpecialistSelectionDecision, SubagentSpecialist, utc_now
from app.db.session import get_db_session
from app.security.auth import Principal, require_role

router = APIRouter(prefix="/subagent-specialists", tags=["subagent-specialists"])
DbSession = Annotated[Session, Depends(get_db_session)]


@router.get("", response_model=SubagentSpecialistPage, summary="查询子 Agent 专家模板")
def list_subagent_specialists(
    session: DbSession,
    principal: Principal,
    include_archived: bool = Query(default=False, description="是否包含归档专家"),
) -> SubagentSpecialistPage:
    ensure_system_specialists(session)
    specialists = SubagentSpecialistRegistry(session, principal.organization_id).list(
        include_archived=include_archived
    )
    return SubagentSpecialistPage(
        items=[_to_specialist_response(specialist) for specialist in specialists],
        next_cursor=None,
    )


@router.post(
    "",
    response_model=SubagentSpecialistResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建组织子 Agent 专家模板",
)
def create_subagent_specialist(
    request: SubagentSpecialistCreateRequest,
    session: DbSession,
    principal: Principal,
) -> SubagentSpecialistResponse:
    require_role(principal, {"admin", "engineer"})
    _validate_specialist_contract(
        output_schema=request.output_schema_json,
        budget=request.budget_json,
    )
    specialist = SubagentSpecialist(
        organization_id=principal.organization_id,
        slug=request.slug,
        display_name=request.display_name,
        description=request.description,
        role=request.role,
        system_prompt=request.system_prompt,
        capability_slugs_json=_string_list(request.capability_slugs_json),
        output_schema_json=request.output_schema_json,
        budget_json=normalize_budget(request.budget_json),
        trigger_keywords_json=_string_list(request.trigger_keywords_json),
        visibility=request.visibility,
        status="ACTIVE",
        created_by=principal.user_id,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    session.add(specialist)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="专家 slug 已存在",
        ) from exc
    session.refresh(specialist)
    return _to_specialist_response(specialist)


@router.get(
    "/calibration",
    response_model=SpecialistCalibrationReport,
    summary="查询专家选择校准报告",
)
def get_specialist_calibration(
    session: DbSession,
    principal: Principal,
    window: str = Query(default="30d", pattern=r"^(7d|30d|all)$"),
) -> SpecialistCalibrationReport:
    since = _window_since(window)
    statement = select(SpecialistSelectionDecision).where(
        SpecialistSelectionDecision.organization_id == principal.organization_id,
    )
    if since is not None:
        statement = statement.where(SpecialistSelectionDecision.created_at >= since)
    decisions = list(session.execute(statement).scalars())
    buckets = _calibration_buckets(session, decisions)
    decision_count = len(decisions)
    low_sample = decision_count < 20
    ece = None
    if not low_sample and decision_count > 0:
        ece = round(
            sum(
                bucket.ece_contribution or 0
                for bucket in buckets
                if bucket.ece_contribution is not None
            ),
            4,
        )
    return SpecialistCalibrationReport(
        organization_id=principal.organization_id,
        window=window,  # type: ignore[arg-type]
        decision_count=decision_count,
        low_sample=low_sample,
        ece=ece,
        buckets=buckets,
    )


@router.get(
    "/{specialist_id}",
    response_model=SubagentSpecialistResponse,
    summary="查询子 Agent 专家模板详情",
)
def get_subagent_specialist(
    specialist_id: str,
    session: DbSession,
    principal: Principal,
) -> SubagentSpecialistResponse:
    ensure_system_specialists(session)
    specialist = _get_visible_specialist(specialist_id, session, principal.organization_id)
    return _to_specialist_response(specialist)


@router.get(
    "/{specialist_id}/stats",
    response_model=SubagentSpecialistStats,
    summary="查询子 Agent 专家历史表现",
)
def get_subagent_specialist_stats(
    specialist_id: str,
    session: DbSession,
    principal: Principal,
    window: str = Query(default="30d", pattern=r"^(7d|30d|all)$"),
) -> SubagentSpecialistStats:
    ensure_system_specialists(session)
    _get_visible_specialist(specialist_id, session, principal.organization_id)
    try:
        stats = compute_specialist_stats(session, specialist_id, window)
    except SpecialistValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return SubagentSpecialistStats(
        specialist_id=stats.specialist_id,
        slug=stats.slug,
        window=stats.window,  # type: ignore[arg-type]
        total_invocations=stats.total_invocations,
        success_count=stats.success_count,
        failed_count=stats.failed_count,
        budget_exceeded_count=stats.budget_exceeded_count,
        depth_rejected_count=stats.depth_rejected_count,
        success_rate=stats.success_rate,
        avg_runtime_ms=stats.avg_runtime_ms,
        p95_runtime_ms=stats.p95_runtime_ms,
        avg_cost_usd=stats.avg_cost_usd,
        total_cost_usd=stats.total_cost_usd,
        avg_tool_calls=stats.avg_tool_calls,
        avg_output_size_bytes=stats.avg_output_size_bytes,
        recent_failure_reasons=stats.recent_failure_reasons,
    )


@router.patch(
    "/{specialist_id}",
    response_model=SubagentSpecialistResponse,
    summary="更新组织子 Agent 专家模板",
)
def update_subagent_specialist(
    specialist_id: str,
    request: SubagentSpecialistUpdateRequest,
    session: DbSession,
    principal: Principal,
) -> SubagentSpecialistResponse:
    require_role(principal, {"admin", "engineer"})
    specialist = _get_visible_specialist(specialist_id, session, principal.organization_id)
    if specialist.visibility == "system":
        if request.system_prompt is not None or request.output_schema_json is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="system 专家的 system_prompt 和 output_schema 不可直接修改",
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="system 专家不可直接修改，请 fork 为组织模板",
        )
    if specialist.organization_id != principal.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="专家模板未找到")

    if request.output_schema_json is not None or request.budget_json is not None:
        _validate_specialist_contract(
            output_schema=request.output_schema_json or specialist.output_schema_json,
            budget=request.budget_json or specialist.budget_json,
        )
    updates = request.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if value is None:
            continue
        if key in {"capability_slugs_json", "trigger_keywords_json"}:
            value = _string_list(value)
        if key == "budget_json":
            value = normalize_budget(value)
        setattr(specialist, key, value)
    specialist.updated_at = utc_now()
    session.commit()
    session.refresh(specialist)
    return _to_specialist_response(specialist)


@router.delete(
    "/{specialist_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="归档组织子 Agent 专家模板",
)
def archive_subagent_specialist(
    specialist_id: str,
    session: DbSession,
    principal: Principal,
) -> None:
    require_role(principal, {"admin", "engineer"})
    specialist = _get_visible_specialist(specialist_id, session, principal.organization_id)
    if specialist.visibility == "system":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="system 专家不可删除")
    if specialist.organization_id != principal.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="专家模板未找到")
    specialist.status = "ARCHIVED"
    specialist.updated_at = utc_now()
    session.commit()


@router.post(
    "/{specialist_id}/preflight",
    response_model=SubagentSpecialistPreflightResponse,
    summary="预检专家输出契约和预算",
)
def preflight_subagent_specialist(
    specialist_id: str,
    request: SubagentSpecialistPreflightRequest,
    session: DbSession,
    principal: Principal,
) -> SubagentSpecialistPreflightResponse:
    ensure_system_specialists(session)
    specialist = _get_visible_specialist(specialist_id, session, principal.organization_id)
    errors: list[str] = []
    try:
        registry = SubagentSpecialistRegistry(session, principal.organization_id)
        registry.validate_output(specialist, request.sample_output)
    except SpecialistValidationError as exc:
        errors.append(str(exc))
    try:
        budget = normalize_budget(specialist.budget_json)
    except SpecialistValidationError as exc:
        budget = {}
        errors.append(str(exc))
    return SubagentSpecialistPreflightResponse(
        status="failed" if errors else "passed",
        output_schema_sha256=output_schema_sha256(specialist.output_schema_json),
        budget_json=budget,
        errors=errors,
    )


def _get_visible_specialist(
    specialist_id: str,
    session: Session,
    organization_id: str,
) -> SubagentSpecialist:
    specialist = SubagentSpecialistRegistry(session, organization_id).get(specialist_id)
    if specialist is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="专家模板未找到")
    return specialist


def _validate_specialist_contract(*, output_schema: dict, budget: dict) -> None:
    try:
        validate_output_schema(output_schema)
        normalize_budget(budget)
    except SpecialistValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


def _to_specialist_response(specialist: SubagentSpecialist) -> SubagentSpecialistResponse:
    return SubagentSpecialistResponse(
        id=specialist.id,
        organization_id=specialist.organization_id,
        slug=specialist.slug,
        display_name=specialist.display_name,
        description=specialist.description,
        role=specialist.role,
        system_prompt=specialist.system_prompt,
        capability_slugs_json=_string_list(specialist.capability_slugs_json),
        output_schema_json=specialist.output_schema_json,
        output_schema_sha256=output_schema_sha256(specialist.output_schema_json),
        budget_json=normalize_budget(specialist.budget_json),
        trigger_keywords_json=_string_list(specialist.trigger_keywords_json),
        visibility=specialist.visibility,
        status=specialist.status,
        created_by=specialist.created_by,
        created_at=specialist.created_at,
        updated_at=specialist.updated_at,
    )


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def _window_since(window: str):
    now = utc_now()
    if window == "7d":
        return now - timedelta(days=7)
    if window == "30d":
        return now - timedelta(days=30)
    return None


def _calibration_buckets(
    session: Session,
    decisions: list[SpecialistSelectionDecision],
) -> list[SpecialistCalibrationBucket]:
    total = len(decisions)
    runs_by_decision_id = _runs_by_decision_id(session, decisions)
    buckets: list[SpecialistCalibrationBucket] = []
    for index in range(5):
        low = index / 5
        high = (index + 1) / 5
        bucket_decisions = [
            decision
            for decision in decisions
            if low <= float(decision.confidence or 0) < high
            or (index == 4 and float(decision.confidence or 0) == 1.0)
        ]
        success_count = 0
        scored_count = 0
        confidence_sum = 0.0
        for decision in bucket_decisions:
            confidence_sum += float(decision.confidence or 0)
            run = runs_by_decision_id.get(decision.id)
            if run is None:
                continue
            scored_count += 1
            if run.status == "SUCCESS" and run.subagent_output is not None:
                success_count += 1
        success_rate = round(success_count / scored_count, 3) if scored_count else None
        avg_confidence = (
            round(confidence_sum / len(bucket_decisions), 3) if bucket_decisions else None
        )
        ece_contribution = None
        if total and success_rate is not None and avg_confidence is not None:
            ece_contribution = round(
                (len(bucket_decisions) / total) * abs(success_rate - avg_confidence),
                4,
            )
        buckets.append(
            SpecialistCalibrationBucket(
                bucket=f"[{low:.1f}-{high:.1f}{']' if index == 4 else ')'}",
                min_confidence=low,
                max_confidence=high,
                decision_count=len(bucket_decisions),
                success_count=success_count,
                success_rate=success_rate,
                avg_confidence=avg_confidence,
                ece_contribution=ece_contribution,
            )
        )
    return buckets


def _runs_by_decision_id(
    session: Session,
    decisions: list[SpecialistSelectionDecision],
) -> dict[str, AgentRun]:
    decision_ids = {decision.id for decision in decisions}
    if not decision_ids:
        return {}
    task_ids = {decision.task_id for decision in decisions}
    runs = list(
        session.execute(
            select(AgentRun).where(
                AgentRun.agent_type == "subagent",
                AgentRun.task_id.in_(task_ids),
            )
        ).scalars()
    )
    result: dict[str, AgentRun] = {}
    for run in runs:
        decision_id = run.context_json.get("specialist_selection_decision_id")
        if isinstance(decision_id, str) and decision_id in decision_ids:
            result.setdefault(decision_id, run)
    return result
