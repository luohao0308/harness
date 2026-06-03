"""Agent Run workspace, prompt manifest, and context manifest endpoints."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *
from ._capability_helpers import *
from ._grounding_helpers import *
from ._knowledge_helpers import *
from ._plan_helpers import *
from ._session_helpers import *
from ._tool_helpers import *
from ._workspace_chat_helpers import *
from ._workspace_response_helpers import *

@router.get(
    "/runs/{run_id}/workspace",
    response_model=AgentRunWorkspaceResponse,
    summary="查询 Agent Workspace 聚合视图",
    description=(
        "返回一个 Agent Run 的 Plan DAG、事件流、Subagent、工具调用、"
        "模型调用、审批和多 Agent 编排状态。"
    ),
)
def get_agent_run_workspace(
    run_id: str,
    session: DbSession,
    principal: Principal,
    retrieval_session_id: str | None = Query(default=None),
    prompt_manifest_id: str | None = Query(default=None),
) -> AgentRunWorkspaceResponse:
    require_role(principal, {"admin", "engineer", "operator"})
    run = _owned_run(run_id=run_id, session=session, principal=principal)
    plan = _latest_plan(run_id=run.id, session=session)
    events = list(
        session.execute(
            select(AgentEvent)
            .where(AgentEvent.task_id == run.id)
            .order_by(AgentEvent.sequence.asc())
            .limit(200)
        ).scalars()
    )
    subagents = list(
        session.execute(
            select(AgentRun)
            .where(AgentRun.task_id == run.id)
            .order_by(AgentRun.started_at.asc().nullsfirst(), AgentRun.id.asc())
        ).scalars()
    )
    tool_calls = list(
        session.execute(
            select(ToolCall)
            .where(ToolCall.task_id == run.id)
            .order_by(ToolCall.created_at.desc())
            .limit(100)
        ).scalars()
    )
    model_calls = list(
        session.execute(
            select(ModelCall)
            .where(ModelCall.task_id == run.id)
            .order_by(ModelCall.created_at.desc())
            .limit(100)
        ).scalars()
    )
    approvals = list(
        session.execute(
            select(ToolApproval)
            .where(ToolApproval.task_id == run.id)
            .order_by(ToolApproval.created_at.desc())
            .limit(50)
        ).scalars()
    )
    assignments = list(
        session.execute(
            select(AgentAssignment)
            .where(AgentAssignment.run_id == run.id)
            .order_by(AgentAssignment.created_at.asc(), AgentAssignment.id.asc())
        ).scalars()
    )
    handoffs = list(
        session.execute(
            select(AgentHandoff)
            .where(AgentHandoff.run_id == run.id)
            .order_by(AgentHandoff.created_at.asc(), AgentHandoff.id.asc())
        ).scalars()
    )
    trace_ids = _trace_ids_by_subject(events=events)
    context_manifest = session.execute(
        select(ContextAssemblyManifest)
        .where(ContextAssemblyManifest.run_id == run.id)
        .order_by(ContextAssemblyManifest.created_at.desc(), ContextAssemblyManifest.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    return AgentRunWorkspaceResponse(
        run=run,
        plan=_plan_response(plan) if plan is not None else None,
        events=[EventResponse.model_validate(event) for event in events],
        knowledge_grounding=_knowledge_grounding_response(
            session,
            run=run,
            retrieval_session_id=retrieval_session_id,
            prompt_manifest_id=prompt_manifest_id,
        ),
        context_assembly=(
            ContextAssemblyManifestResponse.model_validate(context_manifest)
            if context_manifest is not None
            else None
        ),
        token_optimization=_workspace_token_optimization_response(
            context_manifest=context_manifest,
            model_calls=model_calls,
        ),
        subagents=[SubagentResponse.model_validate(subagent) for subagent in subagents],
        tool_calls=[
            _tool_call_response(call, trace_id=trace_ids.get(("tool", call.id)))
            for call in tool_calls
        ],
        model_calls=[
            _model_call_response(call, trace_id=trace_ids.get(("model", call.id)))
            for call in model_calls
        ],
        approvals=[ToolApprovalResponse.model_validate(approval) for approval in approvals],
        assignments=assignments,
        handoffs=handoffs,
    )
