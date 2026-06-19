from __future__ import annotations

import json
import time
from datetime import timedelta
from pathlib import Path

import dramatiq
from sqlalchemy.orm import Session

from app.agents.model_gateway import (
    AuditedModelGateway,
    ModelGateway,
    ModelMessage,
    ModelRequest,
)
from app.agents.plan_steps import sync_subagent_plan_step
from app.agents.specialists import (
    SpecialistBudgetState,
    budget_state_for_run,
    make_default_output,
)
from app.db.models import AgentRun, Task, utc_now
from app.db.session import SessionLocal
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.observability.metrics import agent_subagents_failed_total, agent_subagents_running
from app.sandbox.docker_manager import DockerManager
from app.tools.capabilities import CapabilityRegistry
from app.tools.registry import ToolRegistry
from app.tools.runner import ToolExecution, ToolRunner
from app.workers.broker import broker

DEFAULT_SUBAGENT_TIMEOUT_SECONDS = 900
DEFAULT_REACT_CONTEXT_RECENT_RESULTS = 3
DEFAULT_REACT_CONTEXT_OUTPUT_PREVIEW_CHARS = 1200


def execute_subagent(
    agent_run_id: str,
    simulate_timeout: bool = False,
    session: Session | None = None,
    workspace_root: Path | None = None,
    model_gateway: ModelGateway | None = None,
) -> str:
    if session is not None:
        return _execute_subagent_with_session(
            session=session,
            agent_run_id=agent_run_id,
            simulate_timeout=simulate_timeout,
            workspace_root=workspace_root,
            model_gateway=model_gateway,
        )

    with SessionLocal() as session:
        return _execute_subagent_with_session(
            session=session,
            agent_run_id=agent_run_id,
            simulate_timeout=simulate_timeout,
            workspace_root=workspace_root,
            model_gateway=model_gateway,
        )


def _execute_subagent_with_session(
    *,
    session: Session,
    agent_run_id: str,
    simulate_timeout: bool,
    workspace_root: Path | None,
    model_gateway: ModelGateway | None,
) -> str:
    agent_run = session.get(AgentRun, agent_run_id)
    if agent_run is None:
        raise ValueError(f"AgentRun not found: {agent_run_id}")

    event_store = EventStore(session)
    agent_run.status = "RUNNING"
    agent_run.started_at = utc_now()
    agent_subagents_running.inc()
    event_store.append(
        task_id=agent_run.task_id,
        agent_run_id=agent_run.id,
        event_type=EventType.SUBAGENT_STARTED,
        payload_json={"agent_run_id": agent_run.id, "assignment": agent_run.context_json},
    )

    try:
        if simulate_timeout:
            agent_run.status = "TIMEOUT"
            agent_run.completed_at = utc_now()
            agent_subagents_running.dec()
            event_store.append(
                task_id=agent_run.task_id,
                agent_run_id=agent_run.id,
                event_type=EventType.SUBAGENT_TIMEOUT,
                payload_json={
                    "agent_run_id": agent_run.id,
                    "timeout_seconds": DEFAULT_SUBAGENT_TIMEOUT_SECONDS,
                },
            )
            sync_subagent_plan_step(
                session=session,
                agent_run=agent_run,
                summary="Subagent timed out",
            )
            session.commit()
            return agent_run.status

        event_store.append(
            task_id=agent_run.task_id,
            agent_run_id=agent_run.id,
            event_type=EventType.SUBAGENT_PROGRESS,
            payload_json={
                "agent_run_id": agent_run.id,
                "stage": "executing_assignment",
                "assignment": agent_run.context_json,
            },
        )
        task = session.get(Task, agent_run.task_id)
        (
            tool_results,
            react_trace,
            model_summary,
            context_summary,
            budget_state,
        ) = _execute_react_loop(
            session=session,
            task=task,
            agent_run=agent_run,
            workspace_root=workspace_root,
            event_store=event_store,
            model_gateway=model_gateway,
        )
        summary = _assignment_summary(agent_run.context_json)
        if tool_results:
            summary = _summary_with_tool_results(summary=summary, tool_results=tool_results)
        if model_summary:
            summary = model_summary
        time.sleep(0)
        agent_run.context_json = {
            **agent_run.context_json,
            "result": {
                "summary": summary,
                "tool_results": tool_results,
                "react_trace": react_trace,
                "context_summary": context_summary,
                "completed_at": utc_now().isoformat(),
            },
            "budget_consumed": budget_state.consumed,
            "budget_exceeded": budget_state.exceeded,
        }
        if budget_state.exceeded:
            agent_run.status = "BUDGET_EXCEEDED"
            agent_run.completed_at = utc_now()
            agent_subagents_running.dec()
            event_store.append(
                task_id=agent_run.task_id,
                agent_run_id=agent_run.id,
                event_type=EventType.SUBAGENT_FAILED,
                payload_json={
                    "agent_run_id": agent_run.id,
                    "failure_reason": "budget_exceeded",
                    "budget_exceeded": budget_state.exceeded,
                    "budget_consumed": budget_state.consumed,
                },
            )
            sync_subagent_plan_step(
                session=session,
                agent_run=agent_run,
                summary="Subagent budget exceeded",
            )
            session.commit()
            return agent_run.status
        if agent_run.specialist_id:
            from app.agents.subagent_manager import SubagentManager

            specialist = agent_run.specialist
            if specialist is not None:
                output_json = make_default_output(specialist=specialist, summary=summary)
                SubagentManager(session).finalize_with_output(
                    agent_run=agent_run,
                    raw_output_dict=output_json,
                    budget_consumed=budget_state.consumed,
                    budget_exceeded=budget_state.exceeded,
                )
                agent_subagents_running.dec()
                session.commit()
                return agent_run.status
        agent_run.status = "SUCCESS"
        agent_run.completed_at = utc_now()
        agent_subagents_running.dec()
        event_store.append(
            task_id=agent_run.task_id,
            agent_run_id=agent_run.id,
            event_type=EventType.SUBAGENT_COMPLETED,
            payload_json={"agent_run_id": agent_run.id, "summary": summary},
        )
        sync_subagent_plan_step(session=session, agent_run=agent_run, summary=summary)
        session.commit()
        return agent_run.status
    except Exception:
        agent_run.status = "FAILED"
        agent_run.completed_at = utc_now()
        agent_subagents_running.dec()
        agent_subagents_failed_total.inc()
        event_store.append(
            task_id=agent_run.task_id,
            agent_run_id=agent_run.id,
            event_type=EventType.SUBAGENT_FAILED,
            payload_json={"agent_run_id": agent_run.id},
        )
        sync_subagent_plan_step(session=session, agent_run=agent_run)
        session.commit()
        raise


@dramatiq.actor(
    broker=broker,
    max_retries=0,
    time_limit=DEFAULT_SUBAGENT_TIMEOUT_SECONDS * 1000,
    queue_name="subagents",
)
def run_subagent(agent_run_id: str) -> None:
    execute_subagent(agent_run_id)


def timeout_at_from_now(timeout_seconds: int = DEFAULT_SUBAGENT_TIMEOUT_SECONDS):
    return utc_now() + timedelta(seconds=timeout_seconds)


def _assignment_summary(assignment: dict) -> str:
    step_key = assignment.get("step_key") or "subagent_task"
    description = assignment.get("description") or assignment.get("goal") or "异步子任务"
    return f"Subagent completed {step_key}: {description}"


def _execute_react_loop(
    *,
    session: Session,
    task: Task | None,
    agent_run: AgentRun,
    workspace_root: Path | None,
    event_store: EventStore,
    model_gateway: ModelGateway | None,
) -> tuple[list[dict], list[dict], str | None, dict, SpecialistBudgetState]:
    if task is None:
        return [], [], None, _compact_react_context([]), SpecialistBudgetState(
            consumed={},
            exceeded=[],
        )

    max_rounds = _assignment_max_tool_rounds(agent_run.context_json)
    pending_tools = _assignment_tools(agent_run.context_json)
    tool_results: list[dict] = []
    react_trace: list[dict] = []
    model_summary: str | None = None
    context_summary = _compact_react_context(tool_results)
    budget_state = budget_state_for_run(session, agent_run)

    for round_index in range(1, max_rounds + 1):
        round_results = _execute_tool_batch(
            session=session,
            task=task,
            agent_run=agent_run,
            workspace_root=workspace_root,
            event_store=event_store,
            tools=pending_tools,
            round_index=round_index,
        )
        tool_results.extend(round_results)
        context_summary = _compact_react_context(tool_results)
        budget_state = budget_state_for_run(session, agent_run)
        if budget_state.exceeded:
            _record_budget_exceeded(
                event_store=event_store,
                agent_run=agent_run,
                budget_state=budget_state,
                stage="after_tool_call",
            )
            break
        response = _complete_react_round(
            session=session,
            task=task,
            agent_run=agent_run,
            context_summary=context_summary,
            round_index=round_index,
            model_gateway=model_gateway,
        )
        budget_state = budget_state_for_run(session, agent_run)
        if budget_state.exceeded:
            _record_budget_exceeded(
                event_store=event_store,
                agent_run=agent_run,
                budget_state=budget_state,
                stage="after_model_call",
            )
            break
        parsed = _parse_react_response(response)
        if parsed["summary"]:
            model_summary = parsed["summary"]
        next_tools = parsed["next_tools"]
        react_trace.append(
            {
                "round": round_index,
                "executed_tool_count": len(round_results),
                "next_tool_count": len(next_tools),
                "done": parsed["done"],
                "context_retained_tool_result_count": context_summary["retained_tool_results"],
                "context_omitted_tool_result_count": context_summary["omitted_tool_results"],
            }
        )
        event_store.append(
            task_id=agent_run.task_id,
            agent_run_id=agent_run.id,
            event_type=EventType.SUBAGENT_PROGRESS,
            payload_json={
                "agent_run_id": agent_run.id,
                "stage": "react_round_completed",
                "round": round_index,
                "executed_tool_count": len(round_results),
                "next_tool_count": len(next_tools),
                "done": parsed["done"],
                "context_retained_tool_result_count": context_summary["retained_tool_results"],
                "context_omitted_tool_result_count": context_summary["omitted_tool_results"],
            },
        )
        if parsed["done"] or not next_tools:
            break
        pending_tools = next_tools
    return tool_results, react_trace, model_summary, context_summary, budget_state


def _execute_tool_batch(
    *,
    session: Session,
    task: Task,
    agent_run: AgentRun,
    workspace_root: Path | None,
    event_store: EventStore,
    tools: list[dict],
    round_index: int,
) -> list[dict]:
    if not tools:
        return []

    event_store.append(
        task_id=agent_run.task_id,
        agent_run_id=agent_run.id,
        event_type=EventType.SUBAGENT_PROGRESS,
        payload_json={
            "agent_run_id": agent_run.id,
            "stage": "executing_tools",
            "round": round_index,
            "tool_count": len(tools),
        },
    )
    if task.agent_id is None:
        return [
            {
                "tool_name": str(item.get("tool_name", "")),
                "status": "DENIED",
                "allowed": False,
                "output": {
                    "error": "Agent capability attachment is required for subagent tool execution",
                },
            }
            for item in tools
        ]
    capability_registry = CapabilityRegistry(session, task.organization_id)
    registry, _snapshot = capability_registry.tool_registry_for_agent(task.agent_id)
    runner = ToolRunner(
        session=session,
        workspace_root=workspace_root,
        agent_id=task.agent_id,
        capability_registry=capability_registry,
    )
    roles = _assignment_roles(agent_run.context_json)
    capability_whitelist = _assignment_capability_whitelist(agent_run.context_json)
    sandbox = None
    results = []
    for item in tools:
        tool_name = str(item["tool_name"])
        if capability_whitelist is not None and tool_name not in capability_whitelist:
            results.append(
                _denied_tool_result(
                    session=session,
                    task=task,
                    agent_run=agent_run,
                    tool_name=tool_name,
                    input_json=dict(item.get("input_json", {})),
                    reason="Tool is not in specialist capability whitelist",
                )
            )
            budget_state = budget_state_for_run(session, agent_run)
            if budget_state.exceeded:
                _record_budget_exceeded(
                    event_store=event_store,
                    agent_run=agent_run,
                    budget_state=budget_state,
                    stage="after_tool_call",
                )
                break
            continue
        metadata = registry.tools.get(tool_name)
        if (
            metadata is not None
            and metadata.requires_sandbox
            and task.enable_sandbox
            and sandbox is None
        ):
            sandbox = DockerManager().create_sandbox(
                session=session,
                task_id=task.id,
                agent_run_id=agent_run.id,
                workspace_root=str(workspace_root) if workspace_root is not None else None,
            )
        execution = runner.execute(
            task_id=task.id,
            agent_run_id=agent_run.id,
            tool_name=tool_name,
            input_json=dict(item.get("input_json", {})),
            roles=roles,
            sandbox=sandbox,
        )
        results.append(_tool_result_payload(execution))
        budget_state = budget_state_for_run(session, agent_run)
        if budget_state.exceeded:
            _record_budget_exceeded(
                event_store=event_store,
                agent_run=agent_run,
                budget_state=budget_state,
                stage="after_tool_call",
            )
            break
    return results


def _complete_react_round(
    *,
    session: Session,
    task: Task,
    agent_run: AgentRun,
    context_summary: dict,
    round_index: int,
    model_gateway: ModelGateway | None,
) -> str:
    response = AuditedModelGateway(
        session=session,
        task_id=agent_run.task_id,
        agent_run_id=agent_run.id,
        gateway=model_gateway,
    ).complete(
        ModelRequest(
            model_provider=task.model_provider,
            model_name=task.model_name,
            messages=[
                ModelMessage(
                    role="system",
                    content=_react_system_prompt(agent_run.context_json),
                ),
                ModelMessage(
                    role="user",
                    content=json.dumps(
                        {
                            "assignment": agent_run.context_json,
                            "round": round_index,
                            "tool_context": context_summary,
                        },
                        ensure_ascii=False,
                        default=str,
                    ),
                ),
            ],
        )
    )
    return response.content


def _compact_react_context(tool_results: list[dict]) -> dict:
    retained = [
        _compact_tool_result(result)
        for result in tool_results[-DEFAULT_REACT_CONTEXT_RECENT_RESULTS:]
    ]
    status_counts: dict[str, int] = {}
    tool_counts: dict[str, int] = {}
    for result in tool_results:
        status = str(result.get("status") or "UNKNOWN")
        tool_name = str(result.get("tool_name") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
    omitted_count = max(0, len(tool_results) - len(retained))
    notes = [
        f"累计工具结果 {len(tool_results)} 个，保留最近 {len(retained)} 个给模型继续规划。",
    ]
    if omitted_count:
        notes.append(
            f"已压缩较早工具结果 {omitted_count} 个，完整审计结果仍保存在 result.tool_results。"
        )
    return {
        "strategy": "recent_tool_results_with_counts",
        "total_tool_results": len(tool_results),
        "retained_tool_results": len(retained),
        "omitted_tool_results": omitted_count,
        "status_counts": status_counts,
        "tool_counts": tool_counts,
        "recent_tool_results": retained,
        "notes": notes,
    }


def _compact_tool_result(result: dict) -> dict:
    return {
        "tool_call_id": result.get("tool_call_id"),
        "tool_name": result.get("tool_name"),
        "status": result.get("status"),
        "allowed": result.get("allowed"),
        "duration_ms": result.get("duration_ms"),
        "input_json": (
            result.get("input_json") if isinstance(result.get("input_json"), dict) else {}
        ),
        "output_preview": _preview_value(result.get("output")),
        "error_message": _preview_text(result.get("error_message")),
    }


def _preview_value(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _preview_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_preview_value(item) for item in value[:10]]
    return _preview_text(value)


def _preview_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    if len(text) <= DEFAULT_REACT_CONTEXT_OUTPUT_PREVIEW_CHARS:
        return text
    return f"{text[:DEFAULT_REACT_CONTEXT_OUTPUT_PREVIEW_CHARS]}...[truncated]"


def _assignment_tools(assignment: dict) -> list[dict]:
    raw_tools = assignment.get("tools", [])
    return _normalize_tools(raw_tools)


def _normalize_tools(raw_tools: object) -> list[dict]:
    if not isinstance(raw_tools, list):
        return []
    registry = ToolRegistry.default()
    tools = []
    for raw_tool in raw_tools:
        if not isinstance(raw_tool, dict):
            continue
        tool_name = raw_tool.get("tool_name") or raw_tool.get("name")
        if not isinstance(tool_name, str) or tool_name not in registry.tools:
            raise ValueError(f"unknown assignment tool: {tool_name}")
        input_json = raw_tool.get("input_json", {})
        if not isinstance(input_json, dict):
            raise ValueError(f"tool input_json must be an object: {tool_name}")
        tools.append({"tool_name": tool_name, "input_json": input_json})
    return tools


def _assignment_max_tool_rounds(assignment: dict) -> int:
    raw_value = assignment.get("max_tool_rounds", 1)
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return 1
    return max(1, min(value, 5))


def _parse_react_response(content: str) -> dict:
    if not content or content == "{}":
        return {"summary": None, "done": True, "next_tools": []}
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return {"summary": content[:1000], "done": True, "next_tools": []}
    if not isinstance(parsed, dict):
        return {"summary": content[:1000], "done": True, "next_tools": []}
    summary = parsed.get("summary")
    next_tools = _normalize_tools(parsed.get("next_tools", []))
    done = bool(parsed.get("done", not next_tools))
    return {
        "summary": summary[:1000] if isinstance(summary, str) else None,
        "done": done,
        "next_tools": next_tools,
    }


def _assignment_roles(assignment: dict) -> list[str]:
    raw_roles = assignment.get("roles")
    if isinstance(raw_roles, list):
        roles = [str(role) for role in raw_roles if isinstance(role, str)]
        if roles:
            return roles
    return ["admin", "engineer"]


def _assignment_capability_whitelist(assignment: dict) -> set[str] | None:
    raw_whitelist = assignment.get("capability_whitelist")
    if not isinstance(raw_whitelist, list):
        return None
    return {str(item) for item in raw_whitelist if isinstance(item, str)}


def _react_system_prompt(assignment: dict) -> str:
    base_prompt = (
        "You are a Harness Subagent. Use ReAct style execution. "
        "Return compact JSON with keys summary, done and next_tools. "
        "next_tools must be a list of {tool_name,input_json}."
    )
    override = assignment.get("system_prompt_override")
    if isinstance(override, str) and override.strip():
        return f"{override.strip()}\n\n{base_prompt}"
    return base_prompt


def _record_budget_exceeded(
    *,
    event_store: EventStore,
    agent_run: AgentRun,
    budget_state: SpecialistBudgetState,
    stage: str,
) -> None:
    event_store.append(
        task_id=agent_run.task_id,
        agent_run_id=agent_run.id,
        event_type=EventType.SUBAGENT_PROGRESS,
        payload_json={
            "agent_run_id": agent_run.id,
            "stage": stage,
            "budget_exceeded": budget_state.exceeded,
            "budget_consumed": budget_state.consumed,
        },
    )


def _denied_tool_result(
    *,
    session: Session,
    task: Task,
    agent_run: AgentRun,
    tool_name: str,
    input_json: dict,
    reason: str,
) -> dict:
    from app.sandbox.policies import SandboxPolicyDecision

    registry = ToolRegistry.default()
    metadata = registry.tools[tool_name]
    runner = ToolRunner(session=session, agent_id=task.agent_id)
    execution = runner._deny(  # noqa: SLF001 - worker owns whitelist denial audit.
        task_id=task.id,
        agent_run_id=agent_run.id,
        metadata=metadata,
        input_json=input_json,
        decision=SandboxPolicyDecision(
            allowed=False,
            reason=reason,
            policy_id="specialist-capability-whitelist",
            audit_level=metadata.audit_level,
            requires_sandbox=metadata.requires_sandbox,
        ),
        requires_sandbox=metadata.requires_sandbox,
    )
    return _tool_result_payload(execution)


def _tool_result_payload(execution: ToolExecution) -> dict:
    return {
        "tool_call_id": execution.tool_call.id,
        "tool_name": execution.tool_call.tool_name,
        "status": execution.tool_call.status,
        "allowed": execution.allowed,
        "duration_ms": execution.tool_call.duration_ms,
        "input_json": execution.tool_call.input_json,
        "output": execution.output,
        "error_message": execution.tool_call.error_message,
    }


def _summary_with_tool_results(*, summary: str, tool_results: list[dict]) -> str:
    success_count = sum(1 for result in tool_results if result["status"] == "SUCCESS")
    denied_count = sum(1 for result in tool_results if result["status"] == "DENIED")
    failed_count = sum(1 for result in tool_results if result["status"] in {"FAILED", "TIMEOUT"})
    return (
        f"{summary}。工具执行 {len(tool_results)} 个，"
        f"成功 {success_count} 个，拒绝 {denied_count} 个，失败 {failed_count} 个"
    )
