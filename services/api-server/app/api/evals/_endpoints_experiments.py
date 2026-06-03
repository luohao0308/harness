"""Eval experiment projection endpoints."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *
from .helpers import *
from app.api.pagination import cursor_paginate


@router.post(
    "/datasets/{dataset_id}/experiments",
    response_model=EvalExperimentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an Eval contrast experiment projection",
)
def create_eval_experiment(
    dataset_id: str,
    request: EvalExperimentCreateRequest,
    session: DbSession,
    principal: Principal,
) -> EvalExperimentResponse:
    dataset = _get_dataset(dataset_id, session, principal.organization_id)
    _validate_experiment_arms(request)
    eval_runs = _runs_for_experiment(
        session=session,
        organization_id=principal.organization_id,
        dataset_id=dataset.id,
        eval_run_ids=[arm.eval_run_id for arm in request.arms],
    )
    experiment = EvalExperiment(
        dataset_id=dataset.id,
        organization_id=principal.organization_id,
        name=request.name,
        description=request.description,
        status="COMPLETED",
        metadata_json={
            **request.metadata_json,
            "experiment_kind": "langgraph_vs_native_harness",
            "projection_only": True,
            "regression_delta_replaced": False,
        },
        created_by=principal.user_id,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    session.add(experiment)
    session.flush()
    arms: list[EvalExperimentArm] = []
    for arm_request in request.arms:
        eval_run = eval_runs[arm_request.eval_run_id]
        status_value = arm_request.status or eval_run.status
        if arm_request.error_message:
            status_value = "FAILED"
        arm = EvalExperimentArm(
            experiment_id=experiment.id,
            dataset_id=dataset.id,
            eval_run_id=eval_run.id,
            organization_id=principal.organization_id,
            name=arm_request.name,
            arm_type=arm_request.arm_type,
            status=status_value,
            capability_hashes_json=_arm_capability_hashes(
                eval_run,
                explicit=arm_request.capability_hashes_json,
            ),
            metrics_json=eval_run.metrics_json if isinstance(eval_run.metrics_json, dict) else {},
            error_message=arm_request.error_message,
            created_at=utc_now(),
        )
        session.add(arm)
        arms.append(arm)
    session.flush()
    _audit(
        session,
        principal=principal,
        event_type=EventType.EVAL_RUN_COMPLETED,
        resource_type="eval_experiment",
        resource_id=experiment.id,
        action="create_experiment",
        payload={
            "dataset_id": dataset.id,
            "experiment_id": experiment.id,
            "eval_run_ids": [arm.eval_run_id for arm in arms],
            "projection_only": True,
        },
    )
    session.commit()
    session.refresh(experiment)
    for arm in arms:
        session.refresh(arm)
    return _experiment_response(experiment, arms)


@router.get(
    "/experiments",
    response_model=EvalExperimentPage,
    summary="List Eval contrast experiments",
)
def list_eval_experiments(
    session: DbSession,
    principal: Principal,
    dataset_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> EvalExperimentPage:
    statement = select(EvalExperiment).where(
        EvalExperiment.organization_id == principal.organization_id
    )
    if dataset_id:
        statement = statement.where(EvalExperiment.dataset_id == dataset_id)
    page = cursor_paginate(
        session=session,
        statement=statement,
        model=EvalExperiment,
        cursor=cursor,
        limit=limit,
    )
    arms_by_experiment = _arms_by_experiment(session, [experiment.id for experiment in page.items])
    return EvalExperimentPage(
        items=[
            _experiment_response(experiment, arms_by_experiment.get(experiment.id, []))
            for experiment in page.items
        ],
        next_cursor=page.next_cursor,
    )


@router.get(
    "/experiments/{experiment_id}",
    response_model=EvalExperimentResponse,
    summary="Get Eval contrast experiment detail",
)
def get_eval_experiment(
    experiment_id: str,
    session: DbSession,
    principal: Principal,
) -> EvalExperimentResponse:
    experiment = session.execute(
        select(EvalExperiment).where(
            EvalExperiment.id == experiment_id,
            EvalExperiment.organization_id == principal.organization_id,
        )
    ).scalar_one_or_none()
    if experiment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eval Experiment 未找到")
    arms = list(
        session.execute(
            select(EvalExperimentArm)
            .where(EvalExperimentArm.experiment_id == experiment.id)
            .order_by(EvalExperimentArm.created_at.asc(), EvalExperimentArm.id.asc())
        ).scalars()
    )
    return _experiment_response(experiment, arms)


def _runs_for_experiment(
    *,
    session: Session,
    organization_id: str,
    dataset_id: str,
    eval_run_ids: list[str],
) -> dict[str, EvalRun]:
    unique_ids = list(dict.fromkeys(eval_run_ids))
    runs = {
        run.id: run
        for run in session.execute(
            select(EvalRun).where(
                EvalRun.id.in_(unique_ids),
                EvalRun.organization_id == organization_id,
            )
        ).scalars()
    }
    for eval_run_id in unique_ids:
        run = runs.get(eval_run_id)
        if run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eval Run 未找到")
        if run.dataset_id != dataset_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Eval Run 不属于该 Dataset",
            )
    return runs


def _validate_experiment_arms(request: EvalExperimentCreateRequest) -> None:
    seen_names: set[str] = set()
    for arm in request.arms:
        normalized_name = arm.name.strip()
        if not normalized_name:
            raise HTTPException(
                status_code=422,
                detail="Experiment arm name cannot be blank",
            )
        if normalized_name in seen_names:
            raise HTTPException(
                status_code=422,
                detail="Experiment arm names must be unique",
            )
        seen_names.add(normalized_name)


def _arm_capability_hashes(eval_run: EvalRun, *, explicit: dict) -> dict:
    if explicit:
        return explicit
    snapshot = (
        eval_run.capability_snapshot_json
        if isinstance(eval_run.capability_snapshot_json, dict)
        else {}
    )
    return {
        "capability_version_ids": snapshot.get("capability_version_ids", []),
        "content_sha256_values": snapshot.get("content_sha256_values", []),
        "config_sha256_values": snapshot.get("config_sha256_values", []),
    }


def _arms_by_experiment(
    session: Session,
    experiment_ids: list[str],
) -> dict[str, list[EvalExperimentArm]]:
    if not experiment_ids:
        return {}
    arms_by_id: dict[str, list[EvalExperimentArm]] = {
        experiment_id: [] for experiment_id in experiment_ids
    }
    for arm in session.execute(
        select(EvalExperimentArm)
        .where(EvalExperimentArm.experiment_id.in_(experiment_ids))
        .order_by(EvalExperimentArm.created_at.asc(), EvalExperimentArm.id.asc())
    ).scalars():
        arms_by_id.setdefault(arm.experiment_id, []).append(arm)
    return arms_by_id


def _experiment_response(
    experiment: EvalExperiment,
    arms: list[EvalExperimentArm],
) -> EvalExperimentResponse:
    arm_responses = [EvalExperimentArmResponse.model_validate(arm) for arm in arms]
    return EvalExperimentResponse(
        id=experiment.id,
        dataset_id=experiment.dataset_id,
        organization_id=experiment.organization_id,
        name=experiment.name,
        description=experiment.description,
        status=experiment.status,
        metadata_json=experiment.metadata_json,
        created_by=experiment.created_by,
        created_at=experiment.created_at,
        updated_at=experiment.updated_at,
        eval_run_ids=[arm.eval_run_id for arm in arms],
        arms=arm_responses,
    )
