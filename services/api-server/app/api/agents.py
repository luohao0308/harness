import json
import time
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.executor import PLANNER_SYSTEM_PROMPT, Executor
from app.agents.model_gateway import (
    AuditedModelGateway,
    ModelGatewayError,
    ModelMessage,
    ModelRequest,
)
from app.agents.orchestrator import MultiAgentOrchestrator
from app.agents.planner import PLANNER_PROMPT_VERSION, DeterministicPlanner
from app.agents.registry import ensure_default_agents
from app.agents.schemas import ExecutionPlan as ExecutionPlanSchema
from app.api.schemas import (
    AgentAssignmentResponse,
    AgentAutoResponse,
    AgentChatRequest,
    AgentChatResponse,
    AgentChatStreamRequest,
    AgentHandoffResponse,
    AgentMessagePage,
    AgentOrchestrateResponse,
    AgentPage,
    AgentPlanRequest,
    AgentPlanResponse,
    AgentResponse,
    AgentRunCreateRequest,
    AgentRunWorkspaceResponse,
    AgentSessionCreateRequest,
    AgentSessionPage,
    AgentSessionResponse,
    EventResponse,
    ModelCallResponse,
    SubagentResponse,
    TaskPage,
    TaskPlanResponse,
    TaskPlanStepState,
    TaskResponse,
    ToolApprovalResponse,
    ToolCallResponse,
)
from app.db.models import (
    Agent,
    AgentAssignment,
    AgentEvent,
    AgentHandoff,
    AgentMessage,
    AgentRun,
    AgentSession,
    ExecutionPlan,
    ModelCall,
    Task,
    ToolApproval,
    ToolCall,
    utc_now,
)
from app.db.session import get_db_session
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.security.auth import Principal, require_role
from app.tools.registry import ToolMetadata, ToolRegistry
from app.tools.runner import ToolExecution, ToolRunner

router = APIRouter(prefix="/agents", tags=["agents"])
DbSession = Annotated[Session, Depends(get_db_session)]


@router.get(
    "",
    response_model=AgentPage,
    summary="查询 Agent 注册表",
    description="返回组织内可用的具名 Agent。默认 preset 会自动初始化。",
)
def list_agents(session: DbSession, principal: Principal) -> AgentPage:
    require_role(principal, {"admin", "engineer", "operator"})
    ensure_default_agents(session, principal.organization_id)
    session.commit()
    agents = list(
        session.execute(
            select(Agent)
            .order_by(Agent.id.asc())
        ).scalars()
    )
    return AgentPage(items=agents)


@router.get(
    "/{agent_id}/sessions",
    response_model=AgentSessionPage,
    summary="查询 Agent 会话",
)
def list_agent_sessions(
    agent_id: str,
    session: DbSession,
    principal: Principal,
) -> AgentSessionPage:
    require_role(principal, {"admin", "engineer", "operator"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)
    sessions = list(
        session.execute(
            select(AgentSession)
            .where(
                AgentSession.organization_id == principal.organization_id,
                AgentSession.agent_id == agent_id,
            )
            .order_by(AgentSession.updated_at.desc(), AgentSession.id.asc())
        ).scalars()
    )
    return AgentSessionPage(items=sessions)


@router.post(
    "/{agent_id}/sessions",
    response_model=AgentSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建 Agent 会话",
)
def create_agent_session(
    agent_id: str,
    request: AgentSessionCreateRequest,
    session: DbSession,
    principal: Principal,
) -> AgentSession:
    require_role(principal, {"admin", "engineer"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)
    now = utc_now()
    agent_session = AgentSession(
        organization_id=principal.organization_id,
        agent_id=agent_id,
        created_by=principal.user_id,
        title=request.title or "New Agent Session",
        status="ACTIVE",
        created_at=now,
        updated_at=now,
    )
    session.add(agent_session)
    session.commit()
    session.refresh(agent_session)
    return agent_session


@router.get(
    "/sessions/{session_id}/messages",
    response_model=AgentMessagePage,
    summary="查询 Agent 会话消息",
)
def list_agent_messages(
    session_id: str,
    session: DbSession,
    principal: Principal,
) -> AgentMessagePage:
    require_role(principal, {"admin", "engineer", "operator"})
    agent_session = _owned_session(session_id=session_id, session=session, principal=principal)
    messages = list(
        session.execute(
            select(AgentMessage)
            .where(AgentMessage.session_id == agent_session.id)
            .order_by(AgentMessage.created_at.asc(), AgentMessage.id.asc())
        ).scalars()
    )
    return AgentMessagePage(items=messages)


@router.post(
    "/sessions/{session_id}/messages",
    response_model=AgentChatResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
    summary="内部兼容：发送 Agent 会话消息",
)
def send_agent_message(
    session_id: str,
    request: AgentChatRequest,
    session: DbSession,
    principal: Principal,
) -> AgentChatResponse:
    require_role(principal, {"admin", "engineer"})
    agent_session = _owned_session(session_id=session_id, session=session, principal=principal)
    now = utc_now()
    user_message = AgentMessage(
        session_id=agent_session.id,
        agent_id=agent_session.agent_id,
        role="user",
        content=request.content,
        metadata_json={},
        created_at=now,
    )
    session.add(user_message)
    session.flush()
    assistant_message = AgentMessage(
        session_id=agent_session.id,
        agent_id=agent_session.agent_id,
        role="assistant",
        content=_chat_reply(agent_id=agent_session.agent_id, content=request.content),
        metadata_json={"mode": "chat", "agent_id": agent_session.agent_id},
        created_at=utc_now(),
    )
    agent_session.updated_at = now
    session.add(assistant_message)
    session.commit()
    session.refresh(agent_session)
    session.refresh(user_message)
    session.refresh(assistant_message)
    return AgentChatResponse(
        session=agent_session,
        messages=[user_message, assistant_message],
    )


@router.post(
    "/{agent_id}/runs",
    response_model=AgentPlanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建 Agent Run",
    description="Agent Workspace 的主入口，固定使用 Plan 模式生成可审计 DAG，不自动执行工具。",
)
def create_agent_run(
    agent_id: str,
    request: AgentRunCreateRequest,
    session: DbSession,
    principal: Principal,
) -> AgentPlanResponse:
    require_role(principal, {"admin", "engineer"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)
    payload = request.model_copy(update={"agent_id": agent_id})
    return plan_with_agent(request=payload, session=session, principal=principal)


@router.post(
    "/{agent_id}/runs/plan/stream",
    summary="流式创建 Agent Plan",
    description=(
        "local Agent CLI 风格入口：用户只提交目标，服务端流式返回计划进度，"
        "最终创建 Agent Run。"
    ),
)
def stream_agent_plan_run(
    agent_id: str,
    request: AgentRunCreateRequest,
    session: DbSession,
    principal: Principal,
) -> StreamingResponse:
    require_role(principal, {"admin", "engineer"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)

    def sse(event: str, payload: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def iterator() -> Iterator[str]:
        yield sse(
            "delta",
            {"content": "我会先理解目标，然后生成一个可审计的执行计划。\n"},
        )
        time.sleep(0.05)
        yield sse(
            "delta",
            {"content": "Planner 正在拆解步骤，Harness 会同步记录事件流。\n"},
        )
        time.sleep(0.05)
        try:
            payload = request.model_copy(update={"agent_id": agent_id, "mode": "plan"})
            planned = plan_with_agent(request=payload, session=session, principal=principal)
        except Exception as exc:
            yield sse("error", {"message": str(exc)})
            return
        yield sse(
            "delta",
            {"content": f"计划已生成：{len(planned.plan.steps)} 个步骤。右侧已同步 Plan DAG。\n"},
        )
        yield sse(
            "run_created",
            {
                "run_id": planned.run_id,
                "status": planned.task.status,
                "step_count": len(planned.plan.steps),
                "message": planned.message,
            },
        )

    return StreamingResponse(iterator(), media_type="text/event-stream")


@router.post(
    "/{agent_id}/runs/chat/stream",
    summary="Workspace Pro 对话流",
    description=(
        "Cursor/Workspace artifacts 风格 Workspace Pro 入口。服务端通过 SSE 返回 "
        "think、delta、artifact、usage 和 done 事件；底层仍创建 Agent Run 和可审计 Plan。"
    ),
)
def stream_agent_chat_run(
    agent_id: str,
    request: AgentChatStreamRequest,
    session: DbSession,
    principal: Principal,
) -> StreamingResponse:
    require_role(principal, {"admin", "engineer"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)

    def sse(event: str, payload: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def message_goal() -> str:
        if request.goal and request.goal.strip():
            return request.goal.strip()
        user_messages = [node for node in request.messages if node.role == "user"]
        if user_messages:
            return user_messages[-1].content.strip()
        return "Generate an auditable Agent Plan."

    def estimated_input_tokens() -> int:
        pinned = {node.id for node in request.messages if node.id in set(request.pinned_node_ids)}
        carried = [
            node
            for node in request.messages[-request.context_window_turns :]
            if node.role in {"user", "assistant", "system"}
        ]
        pinned_nodes = [
            node for node in request.messages if node.id in pinned and node not in carried
        ]
        content_length = sum(len(node.content) for node in [*pinned_nodes, *carried])
        return max(1, content_length // 4)

    def requested_tool_payload(
        mention,
        metadata: ToolMetadata,
        tool_call_id: str,
        status: str,
    ) -> dict:
        return {
            "tool_call_id": tool_call_id,
            "tool_name": mention.name,
            "source": mention.source or metadata.source,
            "status": status,
            "input_json": mention.payload,
            "risk": metadata.category,
            "sandbox": "sandboxed" if metadata.requires_sandbox else "none",
        }

    def result_payload(execution: ToolExecution, tool_call_id: str) -> dict:
        tool_call = execution.tool_call
        output_json = tool_call.output_json if isinstance(tool_call.output_json, dict) else {}
        payload = {
            "tool_call_id": tool_call_id,
            "tool_name": tool_call.tool_name,
            "status": _workspace_tool_status(tool_call.status),
            "output_summary": _tool_output_summary(tool_call, output_json),
            "output_json": output_json,
            "duration_ms": tool_call.duration_ms,
            "trace_id": _trace_id_for_tool_call(tool_call.id, session=session),
        }
        approval_id = output_json.get("approval_id")
        if isinstance(approval_id, str):
            payload["approval_id"] = approval_id
        return payload

    def iterator() -> Iterator[str]:
        started_at = time.monotonic()
        first_byte_at = time.monotonic()
        goal = message_goal()
        yield sse(
            "think_delta",
            {
                "content": "已读取当前分支、Pinned 消息和上下文窗口，准备生成可审计计划。\n",
                "active_leaf_id": request.active_leaf_id,
                "active_branch_id": request.active_branch_id,
                "pinned_node_ids": request.pinned_node_ids,
                "context_window_turns": request.context_window_turns,
            },
        )
        try:
            if request.run_id:
                existing_run = _owned_run(
                    run_id=request.run_id,
                    session=session,
                    principal=principal,
                )
                planned = _agent_plan_response_from_run(
                    agent_id=agent_id,
                    run=existing_run,
                    session=session,
                    message_prefix="已继续原 Run",
                )
            else:
                payload = AgentPlanRequest(
                    agent_id=agent_id,
                    goal=goal,
                    title=None,
                    model_provider="default",
                    model_name="default",
                    max_runtime_seconds=1800,
                    max_subagents=5,
                    enable_sandbox=True,
                    enable_network=False,
                )
                planned = plan_with_agent(request=payload, session=session, principal=principal)
        except HTTPException as exc:
            if request.run_id:
                yield sse(
                    "error",
                    {
                        "message": f"run_id cannot be continued: {request.run_id}",
                        "recoverable": True,
                        "run_id": request.run_id,
                    },
                )
                return
            yield sse("error", {"message": str(exc.detail), "recoverable": True})
            return
        except Exception as exc:
            yield sse("error", {"message": str(exc), "recoverable": False})
            return
        registry = ToolRegistry.default()
        runner = ToolRunner(session=session, registry=registry)
        if request.tool_mentions:
            for index, mention in enumerate(request.tool_mentions):
                metadata = registry.tools.get(mention.name)
                tool_call_id = f"workspace-tool-{planned.run_id}-{index}"
                if metadata is None:
                    yield sse(
                        "tool_call_requested",
                        {
                            "tool_call_id": tool_call_id,
                            "tool_name": mention.name,
                            "source": mention.source,
                            "input_json": mention.payload,
                            "status": "failed",
                            "risk": "unknown",
                            "sandbox": "none",
                        },
                    )
                    yield sse(
                        "tool_call_result",
                        {
                            "tool_call_id": tool_call_id,
                            "tool_name": mention.name,
                            "status": "failed",
                            "output_summary": "unknown tool",
                            "output_json": {},
                            "duration_ms": 0,
                            "trace_id": None,
                        },
                    )
                    continue
                executable = (
                    metadata.risk_level == "low"
                    and metadata.idempotent
                    and not metadata.requires_sandbox
                    and metadata.network_policy in {"none", "restricted"}
                )
                if not executable:
                    yield sse(
                        "tool_call_requested",
                        requested_tool_payload(mention, metadata, tool_call_id, "pending_approval"),
                    )
                    continue
                yield sse(
                    "tool_call_requested",
                    requested_tool_payload(mention, metadata, tool_call_id, "running"),
                )
                execution = runner.execute(
                    task_id=planned.run_id,
                    agent_run_id=planned.run_id,
                    tool_name=mention.name,
                    input_json=_normalize_tool_mention_payload(mention.name, mention.payload, goal),
                    roles=principal.roles,
                )
                session.commit()
                yield sse("tool_call_result", result_payload(execution, tool_call_id))
        plan_json = planned.plan.plan_json
        summary = planned.plan.summary or planned.message
        yield sse("delta", {"content": f"{summary}\n"})
        yield sse(
            "artifact_created",
            {
                "name": "plan.json",
                "artifact_type": "json",
                "status": "ready",
                "content": plan_json,
                "run_id": planned.run_id,
            },
        )
        output_tokens = max(1, len(summary) // 4)
        yield sse(
            "usage",
            {
                "input_tokens": estimated_input_tokens(),
                "output_tokens": output_tokens,
                "cost_usd": None,
                "cost_unavailable": True,
                "ttfb_ms": int((first_byte_at - started_at) * 1000),
                "duration_ms": int((time.monotonic() - started_at) * 1000),
                "model_call_id": _latest_model_call_id(planned.run_id, session=session),
            },
        )
        yield sse(
            "done",
            {
                "run_id": planned.run_id,
                "active_branch_id": request.active_branch_id,
                "continue_from_node_id": request.continue_from_node_id,
                "status": planned.task.status,
                "step_count": len(planned.plan.steps),
                "message": planned.message,
            },
        )

    return StreamingResponse(iterator(), media_type="text/event-stream")


@router.post(
    "/plan",
    response_model=AgentPlanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Agent Plan 模式",
    description="在 Agent 工作台中只做任务分解与规划，不执行工具、Subagent 或 Sandbox。",
)
def plan_with_agent(
    request: AgentPlanRequest,
    session: DbSession,
    principal: Principal,
) -> AgentPlanResponse:
    require_role(principal, {"admin", "engineer"})
    task = Task(
        organization_id=principal.organization_id,
        created_by=principal.user_id,
        title=request.title or _title_from_goal(request.goal),
        goal=request.goal,
        status="CREATED",
        model_provider=request.model_provider,
        model_name=request.model_name,
        max_runtime_seconds=request.max_runtime_seconds,
        max_subagents=request.max_subagents,
        enable_sandbox=request.enable_sandbox,
        enable_network=request.enable_network,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    session.add(task)
    session.flush()
    event_store = EventStore(session)
    event_store.append(
        task_id=task.id,
        event_type=EventType.TASK_CREATED,
        payload_json={
            "task_id": task.id,
            "title": task.title,
            "goal": task.goal,
            "agent_id": request.agent_id,
            "mode": "plan",
        },
        actor_type="user",
        actor_id=principal.user_id,
    )
    task.status = "PLANNING"
    task.updated_at = utc_now()
    event_store.append(
        task_id=task.id,
        event_type=EventType.PLAN_REQUESTED,
        payload_json={
            "task_id": task.id,
            "goal": task.goal,
            "agent_id": request.agent_id,
            "mode": "plan",
            "prompt_version": PLANNER_PROMPT_VERSION,
        },
    )
    planner_response_content = _complete_plan_prompt(task=task, session=session)
    planner = DeterministicPlanner()
    plan = planner.parse_model_plan(
        planner_response_content,
        planner_source="llm",
        planner_attempts=1,
    )
    if plan is None:
        plan = planner.create_plan(task)
    try:
        plan = ExecutionPlanSchema.model_validate(plan)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    plan_row = ExecutionPlan(
        task_id=task.id,
        version=1,
        status="GENERATED",
        plan_json=plan.model_dump(),
        created_at=utc_now(),
    )
    session.add(plan_row)
    session.flush()
    event_store.append(
        task_id=task.id,
        event_type=EventType.PLAN_GENERATED,
        payload_json={
            "plan_id": plan_row.id,
            "plan": plan.model_dump(),
            "agent_id": request.agent_id,
            "mode": "plan",
            "prompt_version": PLANNER_PROMPT_VERSION,
            "trace_summary": "Agent Plan 模式已生成计划，等待用户确认执行。",
        },
    )
    task.status = "PLANNED"
    task.updated_at = utc_now()
    session.commit()
    session.refresh(task)
    session.refresh(plan_row)
    return AgentPlanResponse(
        agent_id=request.agent_id,
        run_id=task.id,
        task=task,
        plan=_plan_response(plan_row),
        message=f"已为目标生成 {len(plan.steps)} 个步骤的计划，当前未执行任何工具。",
    )


@router.post(
    "/auto",
    response_model=AgentAutoResponse,
    status_code=status.HTTP_202_ACCEPTED,
    include_in_schema=False,
    summary="内部兼容：自动执行 Agent Run",
    description="内部兼容端点。主产品入口只暴露 Plan，自动执行能力保留给测试和后台编排。",
)
def auto_with_agent(
    request: AgentPlanRequest,
    session: DbSession,
    principal: Principal,
) -> AgentAutoResponse:
    require_role(principal, {"admin", "engineer"})
    planned = plan_with_agent(request=request, session=session, principal=principal)
    ensure_default_agents(session, principal.organization_id)
    run = _owned_run(run_id=planned.run_id, session=session, principal=principal)
    orchestrator = MultiAgentOrchestrator(session)
    assignments, handoffs = orchestrator.execute_assignments(run=run)
    routing_strategy = orchestrator.routing_strategy(run=run)
    routing_reasoning = orchestrator.routing_reasoning(run=run)
    session.commit()
    run = _owned_run(run_id=planned.run_id, session=session, principal=principal)
    executed = Executor(session).execute_existing_plan(run)
    session.commit()
    session.refresh(executed)
    plan = _latest_plan(run_id=executed.id, session=session)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent Run 尚未规划")
    return AgentAutoResponse(
        agent_id=request.agent_id,
        run_id=executed.id,
        task=executed,
        plan=_plan_response(plan),
        orchestration=AgentOrchestrateResponse(
            run_id=executed.id,
            strategy=routing_strategy,
            routing_reasoning=routing_reasoning,
            assignments=assignments,
            handoffs=handoffs,
            message=f"已执行 {len(assignments)} 个具名 Agent assignment 并完成 Reduce。",
        ),
        message="内部自动流程已完成计划、多 Agent 编排和 Run 执行。",
    )


@router.get(
    "/runs",
    response_model=TaskPage,
    summary="查询 Agent Run 历史",
    description="返回 Agent Workspace 创建的 Run 历史；底层兼容 tasks 表。",
)
def list_agent_runs(
    session: DbSession,
    principal: Principal,
) -> TaskPage:
    require_role(principal, {"admin", "engineer", "operator"})
    runs = list(
        session.execute(
            select(Task)
            .where(Task.organization_id == principal.organization_id)
            .order_by(Task.created_at.desc())
            .limit(100)
        ).scalars()
    )
    return TaskPage(items=runs)


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
    return AgentRunWorkspaceResponse(
        run=run,
        plan=_plan_response(plan) if plan is not None else None,
        events=[EventResponse.model_validate(event) for event in events],
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


@router.post(
    "/runs/{run_id}/execute",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="执行 Agent Run 的既有计划",
    description="确认 Plan 模式生成的计划后，复用同一个 Agent Run 执行步骤，不重新规划。",
)
def execute_agent_run(
    run_id: str,
    session: DbSession,
    principal: Principal,
) -> Task:
    require_role(principal, {"admin", "engineer"})
    task = (
        session.query(Task)
        .filter(Task.id == run_id, Task.organization_id == principal.organization_id)
        .one_or_none()
    )
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent Run 未找到")
    if task.status != "PLANNED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="只有 PLANNED 状态的 Agent Run 可以确认执行",
        )
    try:
        executed = Executor(session).execute_existing_plan(task)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    session.commit()
    session.refresh(executed)
    return executed


@router.post(
    "/runs/{run_id}/orchestrate",
    response_model=AgentOrchestrateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建多 Agent 编排分配",
    description="基于已规划 Run 选择具名 Agent，创建 assignments 和 handoffs，不执行分支。",
)
def orchestrate_agent_run(
    run_id: str,
    session: DbSession,
    principal: Principal,
) -> AgentOrchestrateResponse:
    require_role(principal, {"admin", "engineer"})
    ensure_default_agents(session, principal.organization_id)
    run = _owned_run(run_id=run_id, session=session, principal=principal)
    if _latest_plan(run_id=run.id, session=session) is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent Run 尚未规划")
    orchestrator = MultiAgentOrchestrator(session)
    assignments, handoffs = orchestrator.orchestrate(
        run=run,
        entry_agent_id="default",
    )
    routing_strategy = orchestrator.routing_strategy(run=run)
    routing_reasoning = orchestrator.routing_reasoning(run=run)
    session.commit()
    return AgentOrchestrateResponse(
        run_id=run.id,
        strategy=routing_strategy,
        routing_reasoning=routing_reasoning,
        assignments=assignments,
        handoffs=handoffs,
        message=f"已为 Run 创建 {len(assignments)} 个具名 Agent assignment。",
    )


@router.post(
    "/runs/{run_id}/orchestrate/execute",
    response_model=AgentOrchestrateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="执行多 Agent 编排 assignments",
    description="执行 Run 的具名 Agent assignments，并用 Reducer 聚合分支输出。",
)
def execute_agent_orchestration(
    run_id: str,
    session: DbSession,
    principal: Principal,
) -> AgentOrchestrateResponse:
    require_role(principal, {"admin", "engineer"})
    ensure_default_agents(session, principal.organization_id)
    run = _owned_run(run_id=run_id, session=session, principal=principal)
    if _latest_plan(run_id=run.id, session=session) is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent Run 尚未规划")
    orchestrator = MultiAgentOrchestrator(session)
    assignments, handoffs = orchestrator.execute_assignments(run=run)
    routing_strategy = orchestrator.routing_strategy(run=run)
    routing_reasoning = orchestrator.routing_reasoning(run=run)
    session.commit()
    return AgentOrchestrateResponse(
        run_id=run.id,
        strategy=routing_strategy,
        routing_reasoning=routing_reasoning,
        assignments=assignments,
        handoffs=handoffs,
        message=f"已执行 {len(assignments)} 个具名 Agent assignment 并完成 Reduce。",
    )


@router.post(
    "/runs/{run_id}/orchestrate/enqueue",
    response_model=AgentOrchestrateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="入队执行多 Agent 编排 assignments",
    description="将 Run 的具名 Agent assignments 投递到 Dramatiq 队列。",
)
def enqueue_agent_orchestration(
    run_id: str,
    session: DbSession,
    principal: Principal,
) -> AgentOrchestrateResponse:
    require_role(principal, {"admin", "engineer"})
    ensure_default_agents(session, principal.organization_id)
    run = _owned_run(run_id=run_id, session=session, principal=principal)
    if _latest_plan(run_id=run.id, session=session) is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent Run 尚未规划")
    orchestrator = MultiAgentOrchestrator(session)
    assignments, handoffs = orchestrator.enqueue_assignments(run=run)
    routing_strategy = orchestrator.routing_strategy(run=run)
    routing_reasoning = orchestrator.routing_reasoning(run=run)
    session.commit()
    return AgentOrchestrateResponse(
        run_id=run.id,
        strategy=routing_strategy,
        routing_reasoning=routing_reasoning,
        assignments=assignments,
        handoffs=handoffs,
        message=f"已将 {len(assignments)} 个具名 Agent assignment 投递到队列。",
    )


@router.get(
    "/runs/{run_id}/assignments",
    response_model=list[AgentAssignmentResponse],
    summary="查询 Run 的 Agent assignments",
)
def list_agent_run_assignments(
    run_id: str,
    session: DbSession,
    principal: Principal,
) -> list[AgentAssignment]:
    require_role(principal, {"admin", "engineer", "operator"})
    run = _owned_run(run_id=run_id, session=session, principal=principal)
    return list(
        session.execute(
            select(AgentAssignment)
            .where(AgentAssignment.run_id == run.id)
            .order_by(AgentAssignment.created_at.asc(), AgentAssignment.id.asc())
        ).scalars()
    )


@router.get(
    "/runs/{run_id}/handoffs",
    response_model=list[AgentHandoffResponse],
    summary="查询 Run 的 Agent handoffs",
)
def list_agent_run_handoffs(
    run_id: str,
    session: DbSession,
    principal: Principal,
) -> list[AgentHandoff]:
    require_role(principal, {"admin", "engineer", "operator"})
    run = _owned_run(run_id=run_id, session=session, principal=principal)
    return list(
        session.execute(
            select(AgentHandoff)
            .where(AgentHandoff.run_id == run.id)
            .order_by(AgentHandoff.created_at.asc(), AgentHandoff.id.asc())
        ).scalars()
    )


@router.get(
    "/{agent_id}",
    response_model=AgentResponse,
    summary="查询 Agent 详情",
    description="返回指定具名 Agent 的模型、工具、角色和路由标签。",
)
def get_agent(agent_id: str, session: DbSession, principal: Principal) -> Agent:
    require_role(principal, {"admin", "engineer", "operator"})
    return _get_agent(agent_id=agent_id, session=session, principal=principal)


def _complete_plan_prompt(*, task: Task, session: Session) -> str:
    try:
        response = AuditedModelGateway(session=session, task_id=task.id).complete(
            ModelRequest(
                model_provider=task.model_provider,
                model_name=task.model_name,
                messages=[
                    ModelMessage(role="system", content=PLANNER_SYSTEM_PROMPT),
                    ModelMessage(
                        role="user",
                        content=(
                            f"Agent Plan mode only. Do not execute tools.\n\n"
                            f"Task title:\n{task.title}\n\n"
                            f"Task goal:\n{task.goal}\n\n"
                            f"Max subagents: {task.max_subagents}\n"
                            f"Sandbox enabled: {task.enable_sandbox}\n"
                            f"Network enabled: {task.enable_network}"
                        ),
                    ),
                ],
            )
        )
    except ModelGatewayError:
        return "{}"
    return response.content


def _plan_response(plan: ExecutionPlan) -> TaskPlanResponse:
    steps = []
    for raw_step in plan.plan_json.get("steps", []):
        step_key = str(raw_step.get("key", ""))
        steps.append(
            TaskPlanStepState(
                step_key=step_key,
                description=str(raw_step.get("description", "")),
                execution_mode=str(raw_step.get("execution_mode", "")),
                requires_sandbox=bool(raw_step.get("requires_sandbox", False)),
                can_spawn_subagent=bool(raw_step.get("can_spawn_subagent", False)),
                tool_hints=_string_list(raw_step.get("tool_hints")),
                acceptance_criteria=_string_list(raw_step.get("acceptance_criteria")),
                risk_level=str(raw_step.get("risk_level") or "low"),
                artifact_expectations=_string_list(raw_step.get("artifact_expectations")),
                quality_notes=_string_list(raw_step.get("quality_notes")),
                status="PENDING",
                assigned_agent_id=None,
                error_message=None,
                trace_summary=None,
                last_event_sequence=None,
                execution_trace=[],
            )
        )
    return TaskPlanResponse(
        id=plan.id,
        task_id=plan.task_id,
        version=plan.version,
        status=plan.status,
        summary=plan.plan_json.get("summary"),
        planner_source=str(plan.plan_json.get("planner_source", "deterministic")),
        planner_attempts=int(plan.plan_json.get("planner_attempts", 1) or 1),
        planner_prompt_version=str(plan.plan_json.get("planner_prompt_version") or "1.1.0"),
        quality_score=int(plan.plan_json.get("quality_score", 100) or 100),
        validation_warnings=_string_list(plan.plan_json.get("validation_warnings")),
        quality_gates=(
            plan.plan_json.get("quality_gates")
            if isinstance(plan.plan_json.get("quality_gates"), dict)
            else {}
        ),
        plan_json=plan.plan_json,
        steps=steps,
        created_at=plan.created_at,
    )


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def _title_from_goal(goal: str) -> str:
    title = " ".join(goal.strip().split())
    if len(title) <= 48:
        return title or "Agent Plan"
    return title[:45] + "..."


def _owned_run(*, run_id: str, session: Session, principal: Principal) -> Task:
    run = session.execute(
        select(Task).where(
            Task.id == run_id,
            Task.organization_id == principal.organization_id,
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent Run 未找到")
    return run


def _latest_plan(*, run_id: str, session: Session) -> ExecutionPlan | None:
    return session.execute(
        select(ExecutionPlan)
        .where(ExecutionPlan.task_id == run_id)
        .order_by(ExecutionPlan.version.desc())
        .limit(1)
    ).scalar_one_or_none()


def _latest_model_call_id(run_id: str, *, session: Session) -> str | None:
    model_call = session.execute(
        select(ModelCall)
        .where(ModelCall.task_id == run_id)
        .order_by(ModelCall.created_at.desc(), ModelCall.id.desc())
    ).scalars().first()
    return model_call.id if model_call is not None else None


def _agent_plan_response_from_run(
    *,
    agent_id: str,
    run: Task,
    session: Session,
    message_prefix: str,
) -> AgentPlanResponse:
    plan = _latest_plan(run_id=run.id, session=session)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent Run 尚未规划")
    return AgentPlanResponse(
        agent_id=agent_id,
        run_id=run.id,
        task=run,
        plan=_plan_response(plan),
        message=f"{message_prefix} {run.id}，当前未执行新的规划。",
    )


def _normalize_tool_mention_payload(tool_name: str, payload: dict, goal: str) -> dict:
    if tool_name == "mcp_context_search" and "query" not in payload:
        return {**payload, "query": goal, "limit": int(payload.get("limit", 5) or 5)}
    if tool_name == "list_files" and "root" not in payload:
        return {**payload, "root": ".", "glob": str(payload.get("glob", "**/*"))}
    if tool_name == "read_file" and "path" not in payload:
        return {**payload, "path": "README.md"}
    return payload


def _trace_id_for_tool_call(tool_call_id: str, *, session: Session) -> str | None:
    event = session.execute(
        select(AgentEvent)
        .where(AgentEvent.payload_json["tool_call_id"].as_string() == tool_call_id)
        .order_by(AgentEvent.sequence.desc())
    ).scalars().first()
    return event.trace_id if event is not None else None


def _trace_ids_by_subject(*, events: list[AgentEvent]) -> dict[tuple[str, str], str]:
    trace_ids: dict[tuple[str, str], str] = {}
    for event in events:
        if not isinstance(event.trace_id, str):
            continue
        model_call_id = event.payload_json.get("model_call_id")
        if isinstance(model_call_id, str):
            trace_ids.setdefault(("model", model_call_id), event.trace_id)
        tool_call_id = event.payload_json.get("tool_call_id")
        if isinstance(tool_call_id, str):
            trace_ids.setdefault(("tool", tool_call_id), event.trace_id)
    return trace_ids


def _workspace_tool_status(status_value: str) -> str:
    return {
        "SUCCESS": "success",
        "FAILED": "failed",
        "TIMEOUT": "failed",
        "DENIED": "rejected",
        "PENDING_APPROVAL": "pending_approval",
        "RUNNING": "running",
    }.get(status_value, status_value.lower())


def _model_call_response(
    model_call: ModelCall,
    *,
    trace_id: str | None,
) -> ModelCallResponse:
    return ModelCallResponse(
        id=model_call.id,
        task_id=model_call.task_id,
        agent_run_id=model_call.agent_run_id,
        trace_id=trace_id,
        model_provider=model_call.model_provider,
        model_name=model_call.model_name,
        status=model_call.status,
        prompt_tokens=model_call.prompt_tokens,
        completion_tokens=model_call.completion_tokens,
        duration_ms=model_call.duration_ms,
        request_json=model_call.request_json,
        response_json=model_call.response_json,
        error_message=model_call.error_message,
        created_at=model_call.created_at,
    )


def _tool_call_response(
    tool_call: ToolCall,
    *,
    trace_id: str | None,
) -> ToolCallResponse:
    output = tool_call.output_json if isinstance(tool_call.output_json, dict) else {}
    return ToolCallResponse(
        id=tool_call.id,
        task_id=tool_call.task_id,
        agent_run_id=tool_call.agent_run_id,
        trace_id=trace_id,
        tool_name=tool_call.tool_name,
        status=tool_call.status,
        risk_level=tool_call.risk_level,
        requires_sandbox=tool_call.requires_sandbox,
        sandbox_id=tool_call.sandbox_id,
        duration_ms=tool_call.duration_ms,
        input_json=tool_call.input_json,
        output_json=tool_call.output_json,
        output_kind=_tool_output_kind(tool_call, output),
        output_summary=_tool_output_summary(tool_call, output),
        timeout_category="tool_timeout" if tool_call.status == "TIMEOUT" else None,
        error_message=tool_call.error_message,
        created_at=tool_call.created_at,
    )


def _tool_output_kind(tool_call: ToolCall, output: dict) -> str:
    if tool_call.status == "DENIED":
        return "policy_denied"
    if tool_call.status == "TIMEOUT":
        return "timeout"
    if "content" in output:
        return "file_content"
    if "files" in output:
        return "file_list"
    if "exit_code" in output:
        return "shell_result"
    if "status_code" in output:
        return "http_response"
    if "path" in output and "bytes_written" in output:
        return "file_write"
    if tool_call.status == "FAILED":
        return "error"
    return "empty" if not output else "json"


def _tool_output_summary(tool_call: ToolCall, output: dict) -> str:
    if tool_call.error_message and tool_call.status in {"DENIED", "FAILED", "TIMEOUT"}:
        return tool_call.error_message[:300]
    if "content" in output:
        content = str(output.get("content") or "")
        return f"文件内容 {len(content)} 字符"
    if "files" in output and isinstance(output.get("files"), list):
        return f"文件列表 {len(output['files'])} 项"
    if "exit_code" in output:
        return f"命令退出码 {output.get('exit_code')}"
    if "status_code" in output:
        return f"HTTP {output.get('status_code')}"
    if "path" in output and "bytes_written" in output:
        return f"写入 {output.get('path')}，{output.get('bytes_written')} bytes"
    if not output:
        return "无输出"
    return f"JSON 输出字段 {len(output)} 个"


def _get_agent(*, agent_id: str, session: Session, principal: Principal) -> Agent:
    ensure_default_agents(session, principal.organization_id)
    session.commit()
    agent = session.execute(select(Agent).where(Agent.id == agent_id)).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent 未找到")
    return agent


def _owned_session(
    *,
    session_id: str,
    session: Session,
    principal: Principal,
) -> AgentSession:
    agent_session = session.execute(
        select(AgentSession).where(
            AgentSession.id == session_id,
            AgentSession.organization_id == principal.organization_id,
        )
    ).scalar_one_or_none()
    if agent_session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent Session 未找到")
    return agent_session


def _chat_reply(*, agent_id: str, content: str) -> str:
    return (
        f"{agent_id} 已收到你的消息。"
        "当前会话端点仅作为内部兼容层；主工作台固定使用 Plan 模式。"
        f"消息摘要：{content[:80]}"
    )
