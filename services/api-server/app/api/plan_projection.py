from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import TaskPlanResponse, TaskPlanStepState
from app.db.models import AgentEvent, ExecutionPlan, TaskStep
from app.events.event_types import EventType


def build_plan_response(plan: ExecutionPlan, *, session: Session | None = None) -> TaskPlanResponse:
    step_rows: dict[str, TaskStep] = {}
    step_events: dict[str, list[dict]] = {}
    if session is not None:
        step_rows = {
            step.step_key: step
            for step in session.execute(
                select(TaskStep)
                .where(TaskStep.task_id == plan.task_id, TaskStep.plan_id == plan.id)
                .order_by(
                    TaskStep.started_at.asc(),
                    TaskStep.completed_at.asc(),
                    TaskStep.id.asc(),
                )
            ).scalars()
        }
        step_events = _step_events_by_key(task_id=plan.task_id, session=session)

    steps = []
    for raw_step in plan.plan_json.get("steps", []):
        step_key = str(raw_step.get("key", ""))
        step_row = step_rows.get(step_key)
        execution_trace = step_events.get(step_key, [])
        steps.append(
            TaskPlanStepState(
                step_key=step_key,
                description=str(raw_step.get("description", "")),
                depends_on=_string_list(raw_step.get("depends_on")),
                execution_mode=str(raw_step.get("execution_mode", "")),
                requires_sandbox=bool(raw_step.get("requires_sandbox", False)),
                can_spawn_subagent=bool(raw_step.get("can_spawn_subagent", False)),
                recommended_specialist_slug=_optional_string(
                    raw_step.get("recommended_specialist_slug")
                ),
                fanout_specialist_slugs=_string_list(raw_step.get("fanout_specialist_slugs")),
                fanout_aggregation=str(raw_step.get("fanout_aggregation") or "synthesizer_chain"),
                tool_hints=_string_list(raw_step.get("tool_hints")),
                acceptance_criteria=_string_list(raw_step.get("acceptance_criteria")),
                risk_level=str(raw_step.get("risk_level") or "low"),
                artifact_expectations=_string_list(raw_step.get("artifact_expectations")),
                quality_notes=_string_list(raw_step.get("quality_notes")),
                status=step_row.status if step_row is not None else "PENDING",
                assigned_agent_id=step_row.assigned_agent_id if step_row is not None else None,
                error_message=step_row.error_message if step_row is not None else None,
                trace_summary=_last_trace_summary(execution_trace),
                last_event_sequence=(
                    int(execution_trace[-1]["sequence"]) if execution_trace else None
                ),
                execution_trace=execution_trace,
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


def _step_events_by_key(*, task_id: str, session: Session) -> dict[str, list[dict]]:
    events = session.execute(
        select(AgentEvent)
        .where(
            AgentEvent.task_id == task_id,
            AgentEvent.event_type.in_(
                [
                    EventType.STEP_STARTED.value,
                    EventType.STEP_COMPLETED.value,
                    EventType.STEP_FAILED.value,
                    EventType.STEP_RETRIED.value,
                    EventType.STEP_SKIPPED.value,
                    EventType.LANGGRAPH_WORKFLOW_STARTED.value,
                    EventType.LANGGRAPH_WORKFLOW_COMPLETED.value,
                    EventType.LANGGRAPH_WORKFLOW_FAILED.value,
                    EventType.LANGGRAPH_NODE_STARTED.value,
                    EventType.LANGGRAPH_NODE_COMPLETED.value,
                    EventType.LANGGRAPH_NODE_FAILED.value,
                    EventType.LANGGRAPH_TOOL_NODE_REQUESTED.value,
                    EventType.LANGGRAPH_TOOL_NODE_DENIED.value,
                    EventType.LANGGRAPH_TOOL_NODE_COMPLETED.value,
                ]
            ),
        )
        .order_by(AgentEvent.sequence.asc())
    ).scalars()
    grouped: dict[str, list[dict]] = {}
    for event in events:
        step_key = event.payload_json.get("step_key")
        if not isinstance(step_key, str) or not step_key:
            continue
        grouped.setdefault(step_key, []).append(
            {
                "sequence": event.sequence,
                "event_type": event.event_type,
                "trace_id": event.trace_id,
                "summary": event.payload_json.get("trace_summary")
                or event.payload_json.get("summary"),
                "payload_json": event.payload_json,
                "created_at": event.created_at.isoformat(),
            }
        )
    return grouped


def _last_trace_summary(execution_trace: list[dict]) -> str | None:
    for item in reversed(execution_trace):
        summary = item.get("summary")
        if isinstance(summary, str) and summary:
            return summary
    return None


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str) and value:
        return [value]
    return []


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
