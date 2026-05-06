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
from app.db.models import AgentRun, Task, utc_now
from app.db.session import SessionLocal
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.observability.metrics import agent_subagents_failed_total, agent_subagents_running
from app.sandbox.docker_manager import DockerManager
from app.tools.registry import ToolRegistry
from app.tools.runner import ToolExecution, ToolRunner
from app.workers.broker import broker

DEFAULT_SUBAGENT_TIMEOUT_SECONDS = 900


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
        tool_results, react_trace, model_summary = _execute_react_loop(
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
                "completed_at": utc_now().isoformat(),
            },
        }
        agent_run.status = "SUCCESS"
        agent_run.completed_at = utc_now()
        agent_subagents_running.dec()
        event_store.append(
            task_id=agent_run.task_id,
            agent_run_id=agent_run.id,
            event_type=EventType.SUBAGENT_COMPLETED,
            payload_json={"agent_run_id": agent_run.id, "summary": summary},
        )
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
) -> tuple[list[dict], list[dict], str | None]:
    if task is None:
        return [], [], None

    max_rounds = _assignment_max_tool_rounds(agent_run.context_json)
    pending_tools = _assignment_tools(agent_run.context_json)
    tool_results: list[dict] = []
    react_trace: list[dict] = []
    model_summary: str | None = None

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
        response = _complete_react_round(
            session=session,
            task=task,
            agent_run=agent_run,
            tool_results=tool_results,
            round_index=round_index,
            model_gateway=model_gateway,
        )
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
            },
        )
        if parsed["done"] or not next_tools:
            break
        pending_tools = next_tools
    return tool_results, react_trace, model_summary


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
    registry = ToolRegistry.default()
    runner = ToolRunner(session=session, workspace_root=workspace_root, registry=registry)
    roles = _assignment_roles(agent_run.context_json)
    sandbox = None
    results = []
    for item in tools:
        tool_name = str(item["tool_name"])
        metadata = registry.tools[tool_name]
        if metadata.requires_sandbox and task.enable_sandbox and sandbox is None:
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
    return results


def _complete_react_round(
    *,
    session: Session,
    task: Task,
    agent_run: AgentRun,
    tool_results: list[dict],
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
                    content=(
                        "You are a Harness Subagent. Use ReAct style execution. "
                        "Return compact JSON with keys summary, done and next_tools. "
                        "next_tools must be a list of {tool_name,input_json}."
                    ),
                ),
                ModelMessage(
                    role="user",
                    content=json.dumps(
                        {
                            "assignment": agent_run.context_json,
                            "round": round_index,
                            "tool_results": tool_results,
                        },
                        ensure_ascii=False,
                        default=str,
                    ),
                ),
            ],
        )
    )
    return response.content


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


def _tool_result_payload(execution: ToolExecution) -> dict:
    return {
        "tool_call_id": execution.tool_call.id,
        "tool_name": execution.tool_call.tool_name,
        "status": execution.tool_call.status,
        "allowed": execution.allowed,
        "duration_ms": execution.tool_call.duration_ms,
        "output": execution.output,
        "error_message": execution.tool_call.error_message,
    }


def _summary_with_tool_results(*, summary: str, tool_results: list[dict]) -> str:
    success_count = sum(1 for result in tool_results if result["status"] == "SUCCESS")
    denied_count = sum(1 for result in tool_results if result["status"] == "DENIED")
    failed_count = sum(
        1 for result in tool_results if result["status"] in {"FAILED", "TIMEOUT"}
    )
    return (
        f"{summary}。工具执行 {len(tool_results)} 个，"
        f"成功 {success_count} 个，拒绝 {denied_count} 个，失败 {failed_count} 个"
    )
