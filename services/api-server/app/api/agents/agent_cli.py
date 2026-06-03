"""Local hao CLI audit endpoint."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *
from ._plan_helpers import _owned_run
from ._workspace_response_helpers import _tool_call_response


@router.post(
    "/runs/{run_id}/local-tool-events",
    response_model=AgentLocalToolEventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="记录 hao 本地工具事件",
    description=(
        "记录 hao CLI 在宿主机上执行的本地工具调用审计，并写入 ToolCall / EventStore。"
    ),
)
def record_local_tool_event(
    run_id: str,
    request: AgentLocalToolEventRequest,
    session: DbSession,
    principal: Principal,
) -> AgentLocalToolEventResponse:
    require_role(principal, {"admin", "engineer"})
    run = _owned_run(run_id=run_id, session=session, principal=principal)
    now = utc_now()
    workflow_metadata = {
        "interaction_mode": request.interaction_mode,
        "act_intent": request.act_intent,
    }
    tool_call = ToolCall(
        task_id=run.id,
        agent_run_id=None,
        tool_name=request.tool_name,
        status=request.status,
        risk_level=request.risk_level,
        capability_snapshot_json={
            "source": "hao_cli_local",
            "execution_target": request.execution_target,
            "permission_mode": request.permission_mode,
            "local_session_id": request.local_session_id,
            "cwd": request.cwd,
            **workflow_metadata,
        },
        requires_sandbox=request.requires_sandbox,
        sandbox_id=request.sandbox_id,
        duration_ms=request.duration_ms,
        input_json=request.input_json,
        output_json=request.output_json,
        error_message=request.error_message,
        created_at=now,
    )
    session.add(tool_call)
    session.flush()

    event_store = EventStore(session)
    event_store.append(
        task_id=run.id,
        agent_run_id=None,
        event_type=EventType.POLICY_CHECKED,
        payload_json={
            "tool_call_id": tool_call.id,
            "tool_name": request.tool_name,
            "allowed": request.status != "DENIED",
            "policy_id": "hao_local_cli",
            "reason": f"hao local {request.permission_mode} / {request.execution_target}",
            "audit_level": "local_cli",
            "requires_sandbox": request.requires_sandbox,
            **workflow_metadata,
        },
        actor_type="user",
        actor_id=principal.user_id,
    )
    if request.status == "DENIED":
        tool_call.status = "DENIED"
        tool_call.output_json = request.output_json
        tool_call.duration_ms = request.duration_ms
        tool_call.error_message = request.error_message or "local tool denied"
        event = event_store.append(
            task_id=run.id,
            agent_run_id=None,
            event_type=EventType.TOOL_DENIED_BY_POLICY,
            payload_json={
                "tool_call_id": tool_call.id,
                "tool_name": request.tool_name,
                "status": tool_call.status,
                "permission_mode": request.permission_mode,
                "execution_target": request.execution_target,
                "local_session_id": request.local_session_id,
                "cwd": request.cwd,
                **workflow_metadata,
            },
            actor_type="user",
            actor_id=principal.user_id,
        )
    else:
        event_store.append(
            task_id=run.id,
            agent_run_id=None,
            event_type=EventType.TOOL_CALLED,
            payload_json={
                "tool_call_id": tool_call.id,
                "tool_name": request.tool_name,
                "permission_mode": request.permission_mode,
                "execution_target": request.execution_target,
                "local_session_id": request.local_session_id,
                "cwd": request.cwd,
                **workflow_metadata,
            },
            actor_type="user",
            actor_id=principal.user_id,
        )
        event_type = {
            "SUCCESS": EventType.TOOL_RESULT_RECEIVED,
            "FAILED": EventType.TOOL_FAILED,
            "TIMEOUT": EventType.TOOL_TIMEOUT,
        }.get(request.status, EventType.TOOL_RESULT_RECEIVED)
        tool_call.status = request.status
        tool_call.output_json = request.output_json
        tool_call.duration_ms = request.duration_ms
        tool_call.error_message = request.error_message
        event = event_store.append(
            task_id=run.id,
            agent_run_id=None,
            event_type=event_type,
            payload_json={
                "tool_call_id": tool_call.id,
                "tool_name": request.tool_name,
                "status": tool_call.status,
                "permission_mode": request.permission_mode,
                "execution_target": request.execution_target,
                "local_session_id": request.local_session_id,
                "cwd": request.cwd,
                **workflow_metadata,
            },
            actor_type="user",
            actor_id=principal.user_id,
        )
    run.updated_at = utc_now()
    session.commit()
    session.refresh(tool_call)
    return AgentLocalToolEventResponse(
        tool_call=_tool_call_response(tool_call, trace_id=event.trace_id),
        event_sequence=event.sequence,
    )
