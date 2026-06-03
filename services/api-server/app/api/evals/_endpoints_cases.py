"""Eval API route handlers."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *
from .aggregations import *
from .graders import *
from .helpers import *
from .regression import *
from app.api.pagination import cursor_paginate
from app.cache.invalidation import bump_entity_version, entity_version
from app.cache.query_cache import query_cache


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
    bump_entity_version(
        session,
        organization_id=principal.organization_id,
        entity="eval_datasets",
        updated_by=principal.user_id,
    )
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
    cursor: str | None = None,
) -> EvalDatasetPage:
    version = entity_version(
        session,
        organization_id=principal.organization_id,
        entity="eval_datasets",
    )
    cache_key = (
        f"eval_datasets:v{version}:{principal.organization_id}:"
        f"list:{limit}:{cursor or 'first'}"
    )
    cached = query_cache.get_with_metrics(cache_key, entity="eval_datasets")
    if cached is not None:
        return EvalDatasetPage.model_validate(cached)
    page = cursor_paginate(
        session=session,
        statement=select(EvalDataset).where(
            EvalDataset.organization_id == principal.organization_id
        ),
        model=EvalDataset,
        cursor=cursor,
        limit=limit,
    )
    datasets = page.items
    counts = _case_counts(session, [dataset.id for dataset in datasets])
    response = EvalDatasetPage(
        items=[
            _dataset_response(dataset, case_count=counts.get(dataset.id, 0)) for dataset in datasets
        ],
        next_cursor=page.next_cursor,
    )
    query_cache.set(cache_key, response, ttl_seconds=60)
    return response


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
    bump_entity_version(
        session,
        organization_id=principal.organization_id,
        entity="eval_datasets",
        updated_by=principal.user_id,
    )
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
    bump_entity_version(
        session,
        organization_id=principal.organization_id,
        entity="eval_datasets",
        updated_by=principal.user_id,
    )
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
