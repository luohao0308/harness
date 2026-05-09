from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.model_gateway import (
    AuditedModelGateway,
    ModelGatewayError,
    ModelMessage,
    ModelRequest,
)
from app.agents.planner import PLANNER_PROMPT_VERSION, DeterministicPlanner
from app.agents.react_engine import Act, Observe, ReActTrace, Reason
from app.agents.schemas import ExecutionPlan, PlanStep, StepResult
from app.agents.subagent_manager import SubagentManager
from app.db.models import AgentEvent, Task, TaskStep, utc_now
from app.db.models import ExecutionPlan as ExecutionPlanModel
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.events.replay import EventReplay
from app.observability.metrics import agent_tasks_failed_total
from app.sandbox.warm_pool import WarmPoolManager
from app.tools.runner import ToolRunner

PLANNER_SYSTEM_PROMPT = f"""You are the Planner inside an enterprise AI Agent Harness platform.

Convert the user goal into a structured execution plan. Return JSON only.

Harness architecture:
- Model + Harness = Agent.
- Planner decomposes the goal and does not execute tools.
- Executor performs synchronous ReAct steps.
- Subagents perform asynchronous, long-running, or parallel work.
- Tool Registry and Policy Engine guard all tool execution.
- Docker Sandbox is required for shell, tests, file mutation, Git, package install,
  and network actions.
- Event Store records every important action for replay and audit.

Planning rules:
- Produce 3 to 8 steps.
- Use stable snake_case step keys.
- Mark short inspection, summarization, and read-only work as sync.
- Mark long-running, parallel, broad research, or independently verifiable work as async.
- Set can_spawn_subagent=true only for async work.
- Choose tool_hints from: read_file, list_files, write_file, run_shell, run_tests,
  network_request, git_command.
- Set risk_level from: low, medium, high, critical.
- Add acceptance_criteria for every step.
- Add artifact_expectations when the step should produce a report, file, JSON,
  summary, test result, or audit artifact.
- Do not include hidden reasoning.

Required JSON schema:
{{
  "summary": "string",
  "steps": [
    {{
      "key": "snake_case_string",
      "description": "string",
      "execution_mode": "sync|async",
      "requires_sandbox": true,
      "can_spawn_subagent": false,
      "tool_hints": ["read_file"],
      "acceptance_criteria": ["string"],
      "risk_level": "low|medium|high|critical",
      "artifact_expectations": ["string"],
      "expected_events": ["STEP_STARTED", "STEP_COMPLETED"]
    }}
  ]
}}

Prompt version: {PLANNER_PROMPT_VERSION}
"""


@dataclass(frozen=True)
class StepResumeOutcome:
    task: Task
    plan_id: str
    resume_mode: str
    resume_from_step_key: str
    requested_step_keys: list[str]
    skipped_step_keys: list[str]
    resumed_step_keys: list[str]
    completed_step_keys: list[str]
    pending_step_keys: list[str]
    failed_step_key: str | None
    error_message: str | None
    last_sequence: int


class Executor:
    def __init__(self, session: Session, planner: DeterministicPlanner | None = None) -> None:
        self.session = session
        self.planner = planner or DeterministicPlanner()
        self.event_store = EventStore(session)
        self.workspace_root = Path(__file__).resolve().parents[2]

    def start_task(self, task: Task) -> Task:
        task.status = "PLANNING"
        task.updated_at = utc_now()
        self.event_store.append(
            task_id=task.id,
            event_type=EventType.PLAN_REQUESTED,
            payload_json={
                "task_id": task.id,
                "goal": task.goal,
                "prompt_version": PLANNER_PROMPT_VERSION,
            },
        )
        try:
            planner_response = AuditedModelGateway(session=self.session, task_id=task.id).complete(
                ModelRequest(
                    model_provider=task.model_provider,
                    model_name=task.model_name,
                    messages=[
                        ModelMessage(
                            role="system",
                            content=PLANNER_SYSTEM_PROMPT,
                        ),
                        ModelMessage(
                            role="user",
                            content=(
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
        except ModelGatewayError as exc:
            task.status = "FAILED"
            task.updated_at = utc_now()
            self.event_store.append(
                task_id=task.id,
                event_type=EventType.TASK_FAILED,
                payload_json={"summary": str(exc), "stage": "model_gateway"},
            )
            self.session.flush()
            return task

        plan = self.planner.parse_model_plan(
            planner_response.content,
            planner_source="llm",
            planner_attempts=1,
        )
        if plan is None and not self._is_empty_mock_plan(planner_response.content):
            self.event_store.append(
                task_id=task.id,
                event_type=EventType.PLAN_REJECTED,
                payload_json={
                    "reason": "model_plan_schema_invalid",
                    "attempt": 1,
                    "content_preview": planner_response.content[:500],
                    "prompt_version": PLANNER_PROMPT_VERSION,
                },
            )
            repair_response = self._repair_plan(task=task, invalid_content=planner_response.content)
            if repair_response is not None:
                plan = self.planner.parse_model_plan(
                    repair_response.content,
                    planner_source="llm_repaired",
                    planner_attempts=2,
                )
        if plan is None:
            plan = self.planner.create_plan(task)

        try:
            plan = ExecutionPlan.model_validate(plan)
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
            payload_json={
                "plan_id": plan_row.id,
                "plan": plan.model_dump(),
                "prompt_version": PLANNER_PROMPT_VERSION,
            },
        )

        task.status = "RUNNING"
        task.updated_at = utc_now()
        for step in plan.steps:
            result = self._execute_step(task, plan_row, step)
            if result.status == "STEP_FAILED":
                self._apply_step_failure(task=task, step=step, result=result)
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

    def execute_existing_plan(self, task: Task) -> Task:
        plan_row = self._latest_plan(task)
        if plan_row is None:
            msg = "Execution plan not found"
            raise ValueError(msg)
        plan = ExecutionPlan.model_validate(plan_row.plan_json)

        task.status = "RUNNING"
        task.updated_at = utc_now()
        task.completed_at = None
        self.event_store.append(
            task_id=task.id,
            event_type=EventType.TASK_STARTED,
            payload_json={
                "task_id": task.id,
                "plan_id": plan_row.id,
                "mode": "execute_existing_plan",
                "trace_summary": "用户确认 Agent Plan，开始执行现有计划。",
            },
        )
        for step in plan.steps:
            result = self._execute_step(task, plan_row, step)
            if result.status == "STEP_FAILED":
                self._apply_step_failure(task=task, step=step, result=result)
                return task

        task.status = "COMPLETED"
        task.updated_at = utc_now()
        task.completed_at = utc_now()
        self.event_store.append(
            task_id=task.id,
            event_type=EventType.TASK_COMPLETED,
            payload_json={
                "task_id": task.id,
                "plan_id": plan_row.id,
                "mode": "execute_existing_plan",
            },
        )
        self.session.flush()
        return task

    def resume_task(self, task: Task) -> Task:
        replay_state = EventReplay(self.session).replay_state_json(task_id=task.id)
        plan_row = self._latest_plan(task)
        if plan_row is None:
            return self.start_task(task)
        plan = ExecutionPlan.model_validate(plan_row.plan_json)

        completed_steps = set(replay_state.get("completed_steps", []))
        failed_steps = set(replay_state.get("failed_steps", []))
        if not completed_steps and not failed_steps:
            return self.start_task(task)

        task.status = "RUNNING"
        task.updated_at = utc_now()
        resumed_step_keys = []
        for step in plan.steps:
            if step.key in completed_steps:
                resumed_step_keys.append(step.key)
                self.event_store.append(
                    task_id=task.id,
                    event_type=EventType.STEP_SKIPPED,
                    payload_json={
                        "step_key": step.key,
                        "reason": "already completed before resume",
                    },
                )
                continue
            self.event_store.append(
                task_id=task.id,
                event_type=EventType.STEP_RETRIED,
                payload_json={
                    "step_key": step.key,
                    "resume_mode": "full_task",
                },
            )
            result = self._execute_step(task, plan_row, step)
            if result.status == "STEP_FAILED":
                self._apply_step_failure(task=task, step=step, result=result)
                return task

        task.status = "COMPLETED"
        task.updated_at = utc_now()
        task.completed_at = utc_now()
        self.event_store.append(
            task_id=task.id,
            event_type=EventType.TASK_COMPLETED,
            payload_json={
                "task_id": task.id,
                "plan_id": plan_row.id,
                "resumed_from_steps": resumed_step_keys,
            },
        )
        self.session.flush()
        return task

    def resume_steps(
        self,
        task: Task,
        *,
        step_keys: list[str],
        resume_mode: str = "from_first_selected",
    ) -> StepResumeOutcome:
        replay_state = EventReplay(self.session).replay_state_json(task_id=task.id)
        plan_row = self._latest_plan(task)
        if plan_row is None:
            msg = "Execution plan not found"
            raise ValueError(msg)
        plan = ExecutionPlan.model_validate(plan_row.plan_json)
        requested_step_keys = list(dict.fromkeys(step_keys))
        step_index = {step.key: index for index, step in enumerate(plan.steps)}
        unknown_step_keys = [
            step_key for step_key in requested_step_keys if step_key not in step_index
        ]
        if unknown_step_keys:
            msg = f"Unknown step keys: {', '.join(unknown_step_keys)}"
            raise ValueError(msg)
        first_step_index = min(step_index[step_key] for step_key in requested_step_keys)
        resume_from_step_key = plan.steps[first_step_index].key

        task.status = "RUNNING"
        task.updated_at = utc_now()
        task.completed_at = None
        completed_steps = set(replay_state.get("completed_steps", []))
        skipped_step_keys: list[str] = []
        resumed_step_keys: list[str] = []
        failed_step_key: str | None = None
        error_message: str | None = None

        for step in plan.steps[first_step_index:]:
            if step.key in completed_steps:
                skipped_step_keys.append(step.key)
                self.event_store.append(
                    task_id=task.id,
                    event_type=EventType.STEP_SKIPPED,
                    payload_json={
                        "step_key": step.key,
                        "reason": "already completed before step resume",
                        "resume_mode": resume_mode,
                        "resume_from_step_key": resume_from_step_key,
                    },
                )
                continue
            self.event_store.append(
                task_id=task.id,
                event_type=EventType.STEP_RETRIED,
                payload_json={
                    "step_key": step.key,
                    "resume_mode": resume_mode,
                    "resume_from_step_key": resume_from_step_key,
                },
            )
            resumed_step_keys.append(step.key)
            result = self._execute_step(task, plan_row, step)
            if result.status == "STEP_FAILED":
                failed_step_key = step.key
                error_message = result.summary
                self._apply_step_failure(
                    task=task,
                    step=step,
                    result=result,
                    extra_payload={
                        "resume_mode": resume_mode,
                        "resume_from_step_key": resume_from_step_key,
                    },
                )
                return self._step_resume_outcome(
                    task=task,
                    plan=plan,
                    plan_id=plan_row.id,
                    resume_mode=resume_mode,
                    resume_from_step_key=resume_from_step_key,
                    requested_step_keys=requested_step_keys,
                    skipped_step_keys=skipped_step_keys,
                    resumed_step_keys=resumed_step_keys,
                    completed_steps=completed_steps,
                    failed_step_key=failed_step_key,
                    error_message=error_message,
                )
            completed_steps.add(step.key)

        pending_step_keys = [step.key for step in plan.steps if step.key not in completed_steps]
        if pending_step_keys:
            task.status = "FAILED"
            task.updated_at = utc_now()
            error_message = "所选断点之前仍存在未完成步骤"
            self.event_store.append(
                task_id=task.id,
                event_type=EventType.TASK_FAILED,
                payload_json={
                    "summary": error_message,
                    "pending_step_keys": pending_step_keys,
                    "resume_mode": resume_mode,
                    "resume_from_step_key": resume_from_step_key,
                },
            )
            agent_tasks_failed_total.inc()
        else:
            task.status = "COMPLETED"
            task.updated_at = utc_now()
            task.completed_at = utc_now()
            self.event_store.append(
                task_id=task.id,
                event_type=EventType.TASK_COMPLETED,
                payload_json={
                    "task_id": task.id,
                    "plan_id": plan_row.id,
                    "resume_mode": resume_mode,
                    "resume_from_step_key": resume_from_step_key,
                    "resumed_step_keys": resumed_step_keys,
                    "skipped_step_keys": skipped_step_keys,
                },
            )
        self.session.flush()
        return self._step_resume_outcome(
            task=task,
            plan=plan,
            plan_id=plan_row.id,
            resume_mode=resume_mode,
            resume_from_step_key=resume_from_step_key,
            requested_step_keys=requested_step_keys,
            skipped_step_keys=skipped_step_keys,
            resumed_step_keys=resumed_step_keys,
            completed_steps=completed_steps,
            failed_step_key=failed_step_key,
            error_message=error_message,
        )

    def _apply_step_failure(
        self,
        *,
        task: Task,
        step: PlanStep,
        result: StepResult,
        extra_payload: dict | None = None,
    ) -> None:
        awaiting_approval = result.next_action == "await_approval"
        task.status = "WAITING_APPROVAL" if awaiting_approval else "FAILED"
        task.updated_at = utc_now()
        payload = {
            "failed_step": step.key,
            "summary": result.summary,
            **(extra_payload or {}),
        }
        if awaiting_approval:
            payload["awaiting_approval"] = True
            payload["trace_summary"] = "工具调用需要人工审批，Run 已暂停等待批准。"
        self.event_store.append(
            task_id=task.id,
            event_type=EventType.TASK_FAILED,
            payload_json=payload,
        )
        if not awaiting_approval:
            agent_tasks_failed_total.inc()
        self.session.flush()

    def _step_resume_outcome(
        self,
        *,
        task: Task,
        plan: ExecutionPlan,
        plan_id: str,
        resume_mode: str,
        resume_from_step_key: str,
        requested_step_keys: list[str],
        skipped_step_keys: list[str],
        resumed_step_keys: list[str],
        completed_steps: set[str],
        failed_step_key: str | None,
        error_message: str | None,
    ) -> StepResumeOutcome:
        completed_step_keys = [step.key for step in plan.steps if step.key in completed_steps]
        pending_step_keys = [step.key for step in plan.steps if step.key not in completed_steps]
        last_sequence = self.session.execute(
            select(func.max(AgentEvent.sequence)).where(AgentEvent.task_id == task.id)
        ).scalar_one_or_none()
        return StepResumeOutcome(
            task=task,
            plan_id=plan_id,
            resume_mode=resume_mode,
            resume_from_step_key=resume_from_step_key,
            requested_step_keys=requested_step_keys,
            skipped_step_keys=skipped_step_keys,
            resumed_step_keys=resumed_step_keys,
            completed_step_keys=completed_step_keys,
            pending_step_keys=pending_step_keys,
            failed_step_key=failed_step_key,
            error_message=error_message,
            last_sequence=int(last_sequence or 0),
        )

    def _repair_plan(self, *, task: Task, invalid_content: str):
        try:
            return AuditedModelGateway(session=self.session, task_id=task.id).complete(
                ModelRequest(
                    model_provider=task.model_provider,
                    model_name=task.model_name,
                    messages=[
                        ModelMessage(
                            role="system",
                            content=(
                                f"{PLANNER_SYSTEM_PROMPT}\nRepair the previous Planner output. "
                                "Return one valid JSON object that matches the required schema."
                            ),
                        ),
                        ModelMessage(
                            role="user",
                            content=(
                                "Task goal:\n"
                                f"{task.goal}\n\nInvalid Planner output:\n{invalid_content}"
                            ),
                        ),
                    ],
                )
            )
        except ModelGatewayError:
            return None

    def _is_empty_mock_plan(self, content: str) -> bool:
        return content.strip() in {"", "{}"}

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

    def _latest_plan(self, task: Task) -> ExecutionPlanModel | None:
        return self.session.execute(
            select(ExecutionPlanModel)
            .where(ExecutionPlanModel.task_id == task.id)
            .order_by(ExecutionPlanModel.version.desc())
            .limit(1)
        ).scalar_one_or_none()

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
            payload_json={
                "step_id": step_row.id,
                "step_key": step.key,
                "execution_mode": step.execution_mode,
                "requires_sandbox": step.requires_sandbox,
                "can_spawn_subagent": step.can_spawn_subagent,
                "tool_hints": step.tool_hints,
                "risk_level": step.risk_level,
                "artifact_expectations": step.artifact_expectations,
                "trace_summary": f"开始{step.execution_mode}步骤 {step.key}",
            },
        )
        if step.can_spawn_subagent:
            agent_run = SubagentManager(self.session).spawn(
                task=task,
                assignment={
                    "step_key": step.key,
                    "description": step.description,
                    "execution_mode": step.execution_mode,
                },
                enqueue=True,
            )
            step_row.assigned_agent_id = agent_run.id
            result = StepResult(
                step_key=step.key,
                status="STEP_COMPLETED",
                summary=f"Subagent spawned: {agent_run.id}",
                tool_calls=[],
                next_action="spawn_subagent",
            )
            step_row.status = result.status
            step_row.completed_at = utc_now()
            self.event_store.append(
                task_id=task.id,
                agent_run_id=agent_run.id,
                event_type=EventType.STEP_COMPLETED,
                payload_json={
                    "step_id": step_row.id,
                    "step_key": step.key,
                    "summary": result.summary,
                    "assigned_agent_id": agent_run.id,
                    "execution_mode": step.execution_mode,
                    "next_action": result.next_action,
                    "trace_summary": (
                        f"异步步骤 {step.key} 已派生子 Agent {agent_run.id[:8]}"
                    ),
                    "react_trace": {
                        "reason": {
                            "step_key": step.key,
                            "summary": f"异步执行需要独立子 Agent：{step.description}",
                        },
                        "act": {
                            "step_key": step.key,
                            "tool_name": "subagent.spawn",
                            "input_json": {"agent_run_id": agent_run.id},
                        },
                        "observe": {
                            "step_key": step.key,
                            "status": "SUBAGENT_SPAWNED",
                            "summary": result.summary,
                        },
                    },
                },
            )
            self.session.flush()
            return result
        tool_name = "run_shell" if step.requires_sandbox else "read_file"
        tool_input = (
            {
                "command": f"echo {step.key}",
                "cwd": "/workspace",
                "timeout_seconds": 60,
            }
            if step.requires_sandbox
            else {"path": "pyproject.toml"}
        )
        sandbox = None
        try:
            if step.requires_sandbox and task.enable_sandbox:
                sandbox = WarmPoolManager().acquire(session=self.session, task_id=task.id)
            execution = ToolRunner(
                session=self.session,
                workspace_root=self.workspace_root,
            ).execute(
                task_id=task.id,
                tool_name=tool_name,
                input_json={
                    **tool_input,
                    "step_key": step.key,
                    "description": step.description,
                },
                sandbox=sandbox,
            )
        finally:
            if sandbox is not None:
                WarmPoolManager().release(session=self.session, sandbox=sandbox)
        if not execution.allowed or execution.tool_call.status != "SUCCESS":
            awaiting_approval = execution.tool_call.status == "PENDING_APPROVAL"
            result = StepResult(
                step_key=step.key,
                status="STEP_FAILED",
                summary=execution.tool_call.error_message or "Tool execution failed",
                tool_calls=[
                    {
                        "tool_call_id": execution.tool_call.id,
                        "tool_name": tool_name,
                    }
                ],
                next_action="await_approval" if awaiting_approval else "stop",
            )
            step_row.status = result.status
            step_row.error_message = result.summary
            step_row.completed_at = utc_now()
            self.event_store.append(
                task_id=task.id,
                event_type=EventType.STEP_FAILED,
                payload_json={
                    "step_id": step_row.id,
                    "step_key": step.key,
                    "summary": result.summary,
                    "awaiting_approval": awaiting_approval,
                    "tool_call_id": execution.tool_call.id,
                },
            )
            self.session.flush()
            return result

        trace = ReActTrace(
            reason=Reason(step_key=step.key, summary=f"Execute {step.description}"),
            act=Act(step_key=step.key),
            observe=Observe(step_key=step.key, status="STEP_COMPLETED"),
        )
        result = StepResult(
            step_key=step.key,
            status="STEP_COMPLETED",
            summary=trace.observe.status,
            tool_calls=[{"tool_call_id": execution.tool_call.id, "tool_name": tool_name}],
            next_action="continue",
        )

        step_row.status = result.status
        step_row.completed_at = utc_now()
        self.event_store.append(
            task_id=task.id,
            event_type=EventType.STEP_COMPLETED,
            payload_json={
                "step_id": step_row.id,
                "step_key": step.key,
                "summary": result.summary,
                "execution_mode": step.execution_mode,
                "tool_call_id": execution.tool_call.id,
                "tool_name": tool_name,
                "duration_ms": execution.tool_call.duration_ms,
                "next_action": result.next_action,
                "trace_summary": (
                    f"同步步骤 {step.key} 通过 {tool_name} 完成，"
                    f"耗时 {execution.tool_call.duration_ms}ms"
                ),
                "react_trace": trace.model_dump(),
            },
        )
        self.session.flush()
        return result
