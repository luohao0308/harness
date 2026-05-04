from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.planner import DeterministicPlanner
from app.agents.react_engine import Act, Observe, ReActTrace, Reason
from app.agents.schemas import ExecutionPlan, PlanStep, StepResult
from app.db.models import ExecutionPlan as ExecutionPlanModel
from app.db.models import ModelCall, Task, TaskStep, ToolCall, utc_now
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.observability.metrics import agent_tasks_failed_total


class Executor:
    def __init__(self, session: Session, planner: DeterministicPlanner | None = None) -> None:
        self.session = session
        self.planner = planner or DeterministicPlanner()
        self.event_store = EventStore(session)

    def start_task(self, task: Task) -> Task:
        task.status = "PLANNING"
        task.updated_at = utc_now()
        self.event_store.append(
            task_id=task.id,
            event_type=EventType.PLAN_REQUESTED,
            payload_json={"task_id": task.id, "goal": task.goal},
        )
        model_call = ModelCall(
            task_id=task.id,
            model_provider=task.model_provider,
            model_name=task.model_name,
            status="SUCCESS",
            prompt_tokens=0,
            completion_tokens=0,
            duration_ms=0,
            request_json={"goal": task.goal, "planner": "deterministic"},
            response_json={"mode": "mock"},
            created_at=utc_now(),
        )
        self.session.add(model_call)
        self.session.flush()
        self.event_store.append(
            task_id=task.id,
            event_type=EventType.MODEL_CALLED,
            payload_json={
                "model_call_id": model_call.id,
                "model_provider": task.model_provider,
                "model_name": task.model_name,
            },
        )

        try:
            plan = ExecutionPlan.model_validate(self.planner.create_plan(task))
        except ValidationError as exc:
            task.status = "FAILED"
            task.updated_at = utc_now()
            self.event_store.append(
                task_id=task.id,
                event_type=EventType.PLAN_REJECTED,
                payload_json={"errors": exc.errors()},
            )
            self.session.flush()
            return task

        plan_row = self._persist_plan(task, plan)
        self.event_store.append(
            task_id=task.id,
            event_type=EventType.PLAN_GENERATED,
            payload_json={"plan_id": plan_row.id, "plan": plan.model_dump()},
        )
        self.event_store.append(
            task_id=task.id,
            event_type=EventType.MODEL_RESPONSE_RECEIVED,
            payload_json={"model_call_id": model_call.id, "plan_id": plan_row.id},
        )

        task.status = "RUNNING"
        task.updated_at = utc_now()
        for step in plan.steps:
            result = self._execute_step(task, plan_row, step)
            if result.status == "STEP_FAILED":
                task.status = "FAILED"
                task.updated_at = utc_now()
                self.event_store.append(
                    task_id=task.id,
                    event_type=EventType.TASK_FAILED,
                    payload_json={"failed_step": step.key, "summary": result.summary},
                )
                agent_tasks_failed_total.inc()
                self.session.flush()
                return task

        task.status = "COMPLETED"
        task.updated_at = utc_now()
        task.completed_at = utc_now()
        self.event_store.append(
            task_id=task.id,
            event_type=EventType.TASK_COMPLETED,
            payload_json={"task_id": task.id, "plan_id": plan_row.id},
        )
        self.session.flush()
        return task

    def _persist_plan(self, task: Task, plan: ExecutionPlan) -> ExecutionPlanModel:
        max_version = self.session.execute(
            select(func.max(ExecutionPlanModel.version)).where(
                ExecutionPlanModel.task_id == task.id
            )
        ).scalar_one()
        plan_row = ExecutionPlanModel(
            task_id=task.id,
            version=(max_version or 0) + 1,
            status="GENERATED",
            plan_json=plan.model_dump(),
            created_at=utc_now(),
        )
        self.session.add(plan_row)
        self.session.flush()
        return plan_row

    def _execute_step(
        self,
        task: Task,
        plan_row: ExecutionPlanModel,
        step: PlanStep,
    ) -> StepResult:
        step_row = TaskStep(
            task_id=task.id,
            plan_id=plan_row.id,
            step_key=step.key,
            description=step.description,
            status="RUNNING",
            execution_mode=step.execution_mode,
            started_at=utc_now(),
        )
        self.session.add(step_row)
        self.session.flush()
        self.event_store.append(
            task_id=task.id,
            event_type=EventType.STEP_STARTED,
            payload_json={"step_id": step_row.id, "step_key": step.key},
        )
        tool_name = "run_shell" if step.requires_sandbox else "read_file"
        tool_call = ToolCall(
            task_id=task.id,
            tool_name=tool_name,
            status="SUCCESS",
            risk_level="high" if step.requires_sandbox else "low",
            requires_sandbox=step.requires_sandbox,
            duration_ms=0,
            input_json={"step_key": step.key, "description": step.description},
            output_json={"summary": "mock tool execution"},
            created_at=utc_now(),
        )
        self.session.add(tool_call)
        self.session.flush()
        self.event_store.append(
            task_id=task.id,
            event_type=EventType.POLICY_CHECKED,
            payload_json={
                "tool_call_id": tool_call.id,
                "tool_name": tool_name,
                "allowed": True,
                "requires_sandbox": step.requires_sandbox,
            },
        )
        self.event_store.append(
            task_id=task.id,
            event_type=EventType.TOOL_CALLED,
            payload_json={"tool_call_id": tool_call.id, "tool_name": tool_name},
        )

        trace = ReActTrace(
            reason=Reason(step_key=step.key, summary=f"Execute {step.description}"),
            act=Act(step_key=step.key),
            observe=Observe(step_key=step.key, status="STEP_COMPLETED"),
        )
        result = StepResult(
            step_key=step.key,
            status="STEP_COMPLETED",
            summary=trace.observe.status,
            tool_calls=[{"tool_call_id": tool_call.id, "tool_name": tool_name}],
            next_action="continue",
        )

        step_row.status = result.status
        step_row.completed_at = utc_now()
        self.event_store.append(
            task_id=task.id,
            event_type=EventType.TOOL_RESULT_RECEIVED,
            payload_json={
                "tool_call_id": tool_call.id,
                "tool_name": tool_name,
                "status": "SUCCESS",
            },
        )
        self.event_store.append(
            task_id=task.id,
            event_type=EventType.STEP_COMPLETED,
            payload_json={
                "step_id": step_row.id,
                "step_key": step.key,
                "summary": result.summary,
                "react_trace": trace.model_dump(),
            },
        )
        self.session.flush()
        return result
