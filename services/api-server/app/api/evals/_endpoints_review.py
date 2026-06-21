"""Eval human review route handlers."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *
from .helpers import *
from app.security.auth import require_permission_value
from app.security.rbac import Permission


def _requires_human_review(result: EvalResult) -> bool:
    scores = result.scores_json if isinstance(result.scores_json, dict) else {}
    trace = result.grader_trace_json if isinstance(result.grader_trace_json, dict) else {}
    human_review = trace.get("human_review") if isinstance(trace.get("human_review"), dict) else {}
    markers = (
        scores.get("human_escalation"),
        scores.get("requires_manual_review"),
        trace.get("human_escalation"),
        trace.get("requires_manual_review"),
        human_review.get("required") if isinstance(human_review, dict) else None,
    )
    return any(bool(marker) for marker in markers)


def _review_result_statement(result_id: str | None, organization_id: str):
    statement = select(EvalResult).join(EvalRun, EvalResult.eval_run_id == EvalRun.id).where(
        EvalRun.organization_id == organization_id,
    )
    if result_id is not None:
        statement = statement.where(EvalResult.id == result_id)
    return statement


def _reviewer_user_id(session: Session, principal: Principal) -> str | None:
    return principal.user_id if session.get(User, principal.user_id) is not None else None


@router.get(
    "/results/pending-review",
    response_model=list[EvalResultResponse],
    summary="查询待人工审核 Eval Result",
    description="返回当前组织中需要人工复核且尚未给出人工结论的评测结果。",
)
def list_pending_human_review_results(
    session: DbSession,
    principal: Principal,
) -> list[EvalResultResponse]:
    require_permission_value(principal, Permission.EVAL_MANAGE)
    results = list(
        session.execute(
            _review_result_statement(None, principal.organization_id)
            .where(EvalResult.human_verdict.is_(None))
            .order_by(EvalResult.created_at.asc(), EvalResult.id.asc())
        ).scalars()
    )
    return [_eval_result_response(result) for result in results if _requires_human_review(result)]


@router.patch(
    "/results/{result_id}/review",
    response_model=EvalResultResponse,
    summary="提交 Eval Result 人工审核",
    description="为需要人工复核的评测结果写入批准或拒绝结论。",
)
def review_eval_result(
    result_id: str,
    request: EvalHumanReviewRequest,
    session: DbSession,
    principal: Principal,
) -> EvalResultResponse:
    require_permission_value(principal, Permission.EVAL_MANAGE)
    result = session.execute(
        _review_result_statement(result_id, principal.organization_id)
    ).scalar_one_or_none()
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eval Result 未找到")
    if not _requires_human_review(result):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Eval Result 不需要人工复核",
        )

    reviewer_id = _reviewer_user_id(session, principal)
    result.human_verdict = request.verdict
    result.reviewer_id = reviewer_id
    result.reviewed_at = utc_now()
    trace = result.grader_trace_json if isinstance(result.grader_trace_json, dict) else {}
    result.grader_trace_json = {
        **trace,
        "human_review": {
            **(trace.get("human_review") if isinstance(trace.get("human_review"), dict) else {}),
            "verdict": request.verdict,
            "notes": request.notes,
            "reviewer_id": principal.user_id,
            "reviewer_user_id": reviewer_id,
            "reviewed_at": result.reviewed_at.isoformat(),
        },
    }
    _audit(
        session,
        principal=principal,
        event_type=EventType.EVAL_RUN_COMPLETED,
        resource_type="eval_result",
        resource_id=result.id,
        action="human_review",
        payload={"eval_result_id": result.id, "verdict": request.verdict},
    )
    session.commit()
    session.refresh(result)
    return _eval_result_response(result)


__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
