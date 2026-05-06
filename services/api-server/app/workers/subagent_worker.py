from __future__ import annotations

import time
from datetime import timedelta
from pathlib import Path

import dramatiq
from sqlalchemy.orm import Session

from app.agents.model_gateway import AuditedModelGateway, ModelMessage, ModelRequest
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
) -> str:
    if session is not None:
        return _execute_subagent_with_session(
            session=session,
            agent_run_id=agent_run_id,
            simulate_timeout=simulate_timeout,
            workspace_root=workspace_root,
        )

    with SessionLocal() as session:
        return _execute_subagent_with_session(
            session=session,
            agent_run_id=agent_run_id,
            simulate_timeout=simulate_timeout,
            workspace_root=workspace_root,
        )


def _execute_subagent_with_session(
    *,
    session: Session,
    agent_run_id: str,
    simulate_timeout: bool,
    workspace_root: Path | None,
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
        tool_results = _execute_assignment_tools(
            session=session,
            task=task,
            agent_run=agent_run,
            workspace_root=workspace_root,
            event_store=event_store,
        )
        summary = _assignment_summary(agent_run.context_json)
        if tool_results:
            summary = _summary_with_tool_results(summary=summary, tool_results=tool_results)
        if task is not None:
            response = AuditedModelGateway(
                session=session,
                task_id=agent_run.task_id,
                agent_run_id=agent_run.id,
            ).complete(
                ModelRequest(
                    model_provider=task.model_provider,
                    model_name=task.model_name,
                    messages=[
                        ModelMessage(
                            role="system",
                            content=(
                                "You are a Harness Subagent. Complete the assigned async task "
                                "and return compact JSON with summary and findings."
                            ),
                        ),
                        ModelMessage(
                            role="user",
                            content=jsonish_assignment(agent_run.context_json),
                        ),
                    ],
                )
            )
            if response.content and response.content != "{}":
                summary = response.content[:1000]
        time.sleep(0)
        agent_run.context_json = {
            **agent_run.context_json,
            "result": {
                "summary": summary,
                "tool_results": tool_results,
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


def jsonish_assignment(assignment: dict) -> str:
    return "\n".join(f"{key}: {value}" for key, value in assignment.items())


def _assignment_summary(assignment: dict) -> str:
    step_key = assignment.get("step_key") or "subagent_task"
    description = assignment.get("description") or assignment.get("goal") or "异步子任务"
    return f"Subagent completed {step_key}: {description}"


def _execute_assignment_tools(
    *,
    session: Session,
    task: Task | None,
    agent_run: AgentRun,
    workspace_root: Path | None,
    event_store: EventStore,
) -> list[dict]:
    tools = _assignment_tools(agent_run.context_json)
    if task is None or not tools:
        return []

    event_store.append(
        task_id=agent_run.task_id,
        agent_run_id=agent_run.id,
        event_type=EventType.SUBAGENT_PROGRESS,
        payload_json={
            "agent_run_id": agent_run.id,
            "stage": "executing_tools",
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


def _assignment_tools(assignment: dict) -> list[dict]:
    raw_tools = assignment.get("tools", [])
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
