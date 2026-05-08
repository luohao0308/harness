from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
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
    AgentHandoffResponse,
    AgentMessagePage,
    AgentOrchestrateResponse,
    AgentPage,
    AgentPlanRequest,
    AgentPlanResponse,
    AgentResponse,
    AgentSessionCreateRequest,
    AgentSessionPage,
    AgentSessionResponse,
    TaskPlanResponse,
    TaskPlanStepState,
    TaskResponse,
)
from app.db.models import (
    Agent,
    AgentAssignment,
    AgentHandoff,
    AgentMessage,
    AgentSession,
    ExecutionPlan,
    Task,
    utc_now,
)
from app.db.session import get_db_session
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.security.auth import Principal, require_role

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
    summary="发送 Agent Chat 消息",
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


@router.get(
    "/{agent_id}",
    response_model=AgentResponse,
    summary="查询 Agent 详情",
    description="返回指定具名 Agent 的模型、工具、角色和路由标签。",
)
def get_agent(agent_id: str, session: DbSession, principal: Principal) -> Agent:
    require_role(principal, {"admin", "engineer", "operator"})
    return _get_agent(agent_id=agent_id, session=session, principal=principal)


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
    summary="Agent Auto 模式",
    description="自动完成 Plan、多 Agent 编排执行和 Run 执行。",
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
        message="Auto 模式已完成计划、多 Agent 编排和 Run 执行。",
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
        "当前 Chat 模式会持久化会话上下文；需要执行时可切换到 Plan、编排 Agent 或 Execute。"
        f"消息摘要：{content[:80]}"
    )
