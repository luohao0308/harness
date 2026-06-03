"""Agent run planning, execution, orchestration, and assignment endpoints."""

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
from app.api.pagination import cursor_paginate

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
        "目标驱动流式规划入口：用户只提交目标，服务端流式返回计划进度，最终创建 Agent Run。"
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

    return StreamingResponse(iterator(), media_type="text/event-stream", headers=_SSE_HEADERS)

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
    ensure_default_agents(session, principal.organization_id)
    _get_agent(agent_id=request.agent_id, session=session, principal=principal)
    task = Task(
        organization_id=principal.organization_id,
        agent_id=request.agent_id,
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
    capability_registry = CapabilityRegistry(session, principal.organization_id)
    _registry, capability_snapshot = capability_registry.tool_registry_for_agent(request.agent_id)
    task.capability_snapshot_json = capability_snapshot
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
    try:
        planner_response_content = _complete_plan_prompt(task=task, session=session)
    except ModelGatewayError as exc:
        task.status = "FAILED"
        task.updated_at = utc_now()
        event_store.append(
            task_id=task.id,
            event_type=EventType.TASK_FAILED,
            payload_json={
                "task_id": task.id,
                "goal": task.goal,
                "agent_id": request.agent_id,
                "mode": "plan",
                "reason": str(exc),
            },
        )
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Plan 模型调用失败：{exc}",
        ) from exc
    planner = DeterministicPlanner()
    plan = planner.parse_model_plan(
        planner_response_content,
        planner_source="llm",
        planner_attempts=1,
    )
    if plan is None:
        event_store.append(
            task_id=task.id,
            event_type=EventType.PLAN_REJECTED,
            payload_json={
                "reason": "model_plan_schema_invalid",
                "attempt": 1,
                "content_preview": planner_response_content[:500],
                "prompt_version": PLANNER_PROMPT_VERSION,
            },
        )
        repaired_content = _repair_plan_prompt(
            task=task,
            invalid_content=planner_response_content,
            session=session,
        )
        if repaired_content is not None:
            plan = planner.parse_model_plan(
                repaired_content,
                planner_source="llm_repaired",
                planner_attempts=2,
            )
            if plan is None:
                event_store.append(
                    task_id=task.id,
                    event_type=EventType.PLAN_REJECTED,
                    payload_json={
                        "reason": "model_plan_repair_schema_invalid",
                        "attempt": 2,
                        "content_preview": repaired_content[:500],
                        "prompt_version": PLANNER_PROMPT_VERSION,
                    },
                )
        else:
            event_store.append(
                task_id=task.id,
                event_type=EventType.PLAN_REJECTED,
                payload_json={
                    "reason": "model_plan_repair_call_failed",
                    "attempt": 2,
                    "prompt_version": PLANNER_PROMPT_VERSION,
                },
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
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> TaskPage:
    require_role(principal, {"admin", "engineer", "operator"})
    page = cursor_paginate(
        session=session,
        statement=select(Task).where(Task.organization_id == principal.organization_id),
        model=Task,
        cursor=cursor,
        limit=limit,
    )
    return TaskPage(items=page.items, next_cursor=page.next_cursor)

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
