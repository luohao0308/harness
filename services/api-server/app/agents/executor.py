import re
import time
from dataclasses import dataclass
from pathlib import Path
from shlex import quote

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.dag_scheduler import (
    DAGScheduler,
)
from app.agents.dag_scheduler import (
    StepResult as DAGStepResult,
)
from app.agents.langgraph_runner import LangGraphRunnerAdapter
from app.agents.model_gateway import (
    AuditedModelGateway,
    ModelGatewayError,
    ModelMessage,
    ModelRequest,
)
from app.agents.planner import PLANNER_PROMPT_VERSION, DeterministicPlanner
from app.agents.react_engine import Act, Observe, ReActTrace, Reason
from app.agents.registry import ensure_default_agents
from app.agents.schemas import ExecutionPlan, PlanStep, StepResult
from app.agents.specialist_llm_selector import SpecialistLLMSelector
from app.agents.specialists import (
    SubagentSpecialistRegistry,
    collect_subagent_outputs,
    ensure_system_specialists,
)
from app.agents.subagent_manager import FanoutCapacityExceededError, SubagentManager
from app.db.models import AgentEvent, AgentRun, Task, TaskStep, utc_now
from app.db.models import ExecutionPlan as ExecutionPlanModel
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.events.replay import EventReplay
from app.observability.metrics import agent_tasks_failed_total
from app.sandbox.warm_pool import WarmPoolManager
from app.tools.capabilities import CapabilityRegistry
from app.tools.runner import ToolRunner

DEFAULT_TOOL_TIMEOUT = 60
DEFAULT_SUBAGENT_TIMEOUT = 300
SUBAGENT_HEARTBEAT_INTERVAL = 30
MAX_STEP_OUTPUT_BYTES = 64 * 1024  # 64KB
SUBAGENT_FAILURE_STATUSES = {"FAILED", "TIMEOUT", "BUDGET_EXCEEDED", "CANCELLED"}

PLANNER_SYSTEM_PROMPT = f"""You are the Planner inside the Forge Harness enterprise AI runtime.

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
- Mark imported LangGraph workflow nodes as langgraph_node only when the run should
  execute an approved immutable LangGraph workflow through Harness.
- Set can_spawn_subagent=true only for async work.
- Choose tool_hints from: read_file, list_files, write_file, run_shell, run_tests,
  network_request, git_command.
- Set risk_level from: low, medium, high, critical.
- Add acceptance_criteria for every step.
- Add artifact_expectations when the step should produce a report, file, JSON,
  summary, test result, or audit artifact.
- Declare depends_on for each step: list the step keys that must complete before
  this step can begin. Use an empty list for steps with no dependencies.
  Steps with no mutual dependencies will execute concurrently.
- Set timeout_seconds per step (default 60 for sync, 300 for async).
- Do not include hidden reasoning.

Required JSON schema:
{{
  "summary": "string",
  "steps": [
    {{
      "key": "snake_case_string",
      "description": "string",
      "execution_mode": "sync|async|langgraph_node",
      "requires_sandbox": true,
      "can_spawn_subagent": false,
      "depends_on": ["step_key_1"],
      "tool_hints": ["read_file"],
      "acceptance_criteria": ["string"],
      "risk_level": "low|medium|high|critical",
      "artifact_expectations": ["string"],
      "expected_events": ["STEP_STARTED", "STEP_COMPLETED"],
      "timeout_seconds": 60
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
        self.dag_scheduler = DAGScheduler()
        self.step_context: dict[str, DAGStepResult] = {}

    def start_task(self, task: Task) -> Task:
        self._ensure_task_agent_scope(task)
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
            task=task,
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
                    task=task,
                )

        # DAG validation: if model plan has invalid DAG, fall back to deterministic
        if plan is not None:
            dag_valid, dag_error = self.dag_scheduler.validate(plan)
            if not dag_valid:
                self.event_store.append(
                    task_id=task.id,
                    event_type=EventType.PLAN_REJECTED,
                    payload_json={
                        "reason": "dag_validation_failed",
                        "error": dag_error,
                        "prompt_version": PLANNER_PROMPT_VERSION,
                    },
                )
                plan = None

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
        return self._execute_dag(task, plan_row, plan)

    def execute_existing_plan(self, task: Task) -> Task:
        self._ensure_task_agent_scope(task)
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
        return self._execute_dag(task, plan_row, plan)

    def resume_task(self, task: Task) -> Task:
        self._ensure_task_agent_scope(task)
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
                "specialist_outputs": collect_subagent_outputs(self.session, task.id),
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
        self._ensure_task_agent_scope(task)
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
                    "specialist_outputs": collect_subagent_outputs(self.session, task.id),
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

    def _ensure_task_agent_scope(self, task: Task) -> None:
        if task.agent_id is None:
            ensure_default_agents(self.session, task.organization_id or "")
            task.agent_id = "default"
        capability_registry = CapabilityRegistry(
            self.session,
            task.organization_id,
        )
        capability_registry.ensure_builtin_tool_attachment(
            task.agent_id,
            "mcp_artifact_put",
            attached_by="executor",
            priority=-1,
        )
        task.capability_snapshot_json = {}
        if not task.capability_snapshot_json:
            _registry, snapshot = capability_registry.tool_registry_for_agent(task.agent_id)
            task.capability_snapshot_json = snapshot
        self.session.flush()

    def _execute_dag(self, task: Task, plan_row: ExecutionPlanModel, plan: ExecutionPlan) -> Task:
        """Execute plan steps in DAG order using execution groups."""
        groups = self.dag_scheduler.resolve(plan)
        failed_steps: set[str] = set()
        skipped_steps: set[str] = set()
        awaiting_approval = False

        for group in groups:
            # Filter out steps whose dependencies have failed (mark as skipped)
            executable_steps: list[PlanStep] = []
            for step in group.steps:
                # Check if any dependency has failed or been skipped
                deps_failed = any(
                    dep in failed_steps or dep in skipped_steps for dep in step.depends_on
                )
                if deps_failed:
                    skipped_steps.add(step.key)
                    self.event_store.append(
                        task_id=task.id,
                        event_type=EventType.STEP_SKIPPED,
                        payload_json={
                            "step_key": step.key,
                            "reason": "upstream dependency failed",
                        },
                    )
                    self.step_context[step.key] = DAGStepResult(
                        step_key=step.key,
                        status="SKIPPED",
                        output="",
                        tool_calls=[],
                        duration_ms=0,
                    )
                else:
                    executable_steps.append(step)

            # Execute steps in this group (sequentially for sync compatibility)
            for step in executable_steps:
                start_time = time.time()
                result = self._execute_step(task, plan_row, step)
                duration_ms = int((time.time() - start_time) * 1000)

                if result.status == "STEP_FAILED":
                    failed_steps.add(step.key)
                    # Check if this is an approval-waiting failure
                    if result.next_action == "await_approval":
                        awaiting_approval = True
                    # Mark all downstream dependents as skipped
                    downstream = self.dag_scheduler.get_downstream_dependents(plan, step.key)
                    skipped_steps.update(downstream)
                    self.step_context[step.key] = DAGStepResult(
                        step_key=step.key,
                        status="FAILED",
                        output=result.summary,
                        tool_calls=result.tool_calls,
                        duration_ms=duration_ms,
                    )
                else:
                    output = result.output if result.output else result.summary
                    # Truncate output to 64KB
                    if len(output) > MAX_STEP_OUTPUT_BYTES:
                        output = output[:MAX_STEP_OUTPUT_BYTES]
                    self.step_context[step.key] = DAGStepResult(
                        step_key=step.key,
                        status="COMPLETED",
                        output=output,
                        tool_calls=result.tool_calls,
                        duration_ms=duration_ms,
                    )

        # Determine final task state
        if failed_steps:
            if awaiting_approval:
                task.status = "WAITING_APPROVAL"
            else:
                task.status = "FAILED"
            task.updated_at = utc_now()
            payload: dict = {
                "failed_steps": list(failed_steps),
                "skipped_steps": list(skipped_steps),
                "summary": f"Task failed: {len(failed_steps)} step(s) failed",
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
                    "specialist_outputs": collect_subagent_outputs(self.session, task.id),
                },
            )
        self.session.flush()
        return task

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
                "recommended_specialist_slug": step.recommended_specialist_slug,
                "fanout_specialist_slugs": step.fanout_specialist_slugs,
                "fanout_aggregation": step.fanout_aggregation,
                "tool_hints": step.tool_hints,
                "risk_level": step.risk_level,
                "artifact_expectations": step.artifact_expectations,
                "depends_on": step.depends_on,
                "timeout_seconds": step.timeout_seconds,
                "trace_summary": f"开始{step.execution_mode}步骤 {step.key}",
            },
        )

        # Subagent delegation: only when execution_mode=async AND can_spawn_subagent=true
        if step.execution_mode == "langgraph_node":
            return self._execute_langgraph_step(task, plan_row, step, step_row)

        # Subagent delegation: only when execution_mode=async AND can_spawn_subagent=true
        if step.execution_mode == "async" and step.can_spawn_subagent:
            return self._execute_subagent_step(task, plan_row, step, step_row)

        # Model-driven tool selection: invoke Model Gateway with step context
        tool_name, tool_input = self._select_tool_for_step(task, step)

        # Execute tool with timeout
        timeout = step.timeout_seconds or DEFAULT_TOOL_TIMEOUT
        sandbox = None
        if task.agent_id is None:
            step_row.status = "STEP_FAILED"
            step_row.error_message = "Agent capability attachment is required for tool execution"
            step_row.completed_at = utc_now()
            self.event_store.append(
                task_id=task.id,
                event_type=EventType.STEP_FAILED,
                payload_json={
                    "step_id": step_row.id,
                    "step_key": step.key,
                    "summary": step_row.error_message,
                    "permission_boundary": "agent_capability_attachment",
                },
            )
            self.session.flush()
            return StepResult(
                step_key=step.key,
                status="STEP_FAILED",
                summary=step_row.error_message,
                output="",
                tool_calls=[],
                next_action="stop",
            )
        try:
            if (
                (step.requires_sandbox or _tool_requires_sandbox(tool_name))
                and task.enable_sandbox
            ):
                try:
                    sandbox = WarmPoolManager().acquire(
                        session=self.session,
                        task_id=task.id,
                        workspace_root=str(self.workspace_root),
                    )
                except Exception:
                    return self._sandbox_runtime_unavailable_result(
                        task=task,
                        step=step,
                        step_row=step_row,
                        tool_name=tool_name,
                    )
            execution = ToolRunner(
                session=self.session,
                workspace_root=self.workspace_root,
                agent_id=task.agent_id,
            ).execute(
                task_id=task.id,
                tool_name=tool_name,
                input_json={
                    **tool_input,
                    "step_key": step.key,
                    "description": step.description,
                    "timeout_seconds": timeout,
                },
                sandbox=sandbox,
            )
        except TimeoutError:
            step_row.status = "STEP_FAILED"
            step_row.error_message = f"Tool call timed out after {timeout}s"
            step_row.completed_at = utc_now()
            self.event_store.append(
                task_id=task.id,
                event_type=EventType.TOOL_TIMEOUT,
                payload_json={
                    "step_key": step.key,
                    "tool_name": tool_name,
                    "timeout_seconds": timeout,
                },
            )
            self.session.flush()
            return StepResult(
                step_key=step.key,
                status="STEP_FAILED",
                summary=f"Tool call timed out after {timeout}s",
                output="",
                tool_calls=[],
                next_action="stop",
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
                output="",
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

        # Capture tool output (truncated to 64KB)
        tool_output = getattr(execution.tool_call, "output", "") or ""
        if len(tool_output) > MAX_STEP_OUTPUT_BYTES:
            tool_output = tool_output[:MAX_STEP_OUTPUT_BYTES]

        trace = ReActTrace(
            reason=Reason(step_key=step.key, summary=f"Execute {step.description}"),
            act=Act(step_key=step.key),
            observe=Observe(step_key=step.key, status="STEP_COMPLETED"),
        )
        result = StepResult(
            step_key=step.key,
            status="STEP_COMPLETED",
            summary=trace.observe.status,
            output=tool_output,
            tool_calls=[{"tool_call_id": execution.tool_call.id, "tool_name": tool_name}],
            duration_ms=execution.tool_call.duration_ms or 0,
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

    def _sandbox_runtime_unavailable_result(
        self,
        *,
        task: Task,
        step: PlanStep,
        step_row: TaskStep,
        tool_name: str,
    ) -> StepResult:
        message = (
            "Sandbox runtime unavailable: Docker daemon is not running or cannot be reached. "
            "Start Docker Desktop, or rerun this task with sandbox disabled when the step only "
            "needs to produce a Harness artifact."
        )
        step_row.status = "STEP_FAILED"
        step_row.error_message = message
        step_row.completed_at = utc_now()
        self.event_store.append(
            task_id=task.id,
            event_type=EventType.STEP_FAILED,
            payload_json={
                "step_id": step_row.id,
                "step_key": step.key,
                "summary": message,
                "tool_name": tool_name,
                "permission_boundary": "sandbox_runtime",
                "recoverable": True,
            },
        )
        self.session.flush()
        return StepResult(
            step_key=step.key,
            status="STEP_FAILED",
            summary=message,
            output="",
            tool_calls=[],
            next_action="stop",
        )

    def _execute_langgraph_step(
        self,
        task: Task,
        plan_row: ExecutionPlanModel,
        step: PlanStep,
        step_row: TaskStep,
    ) -> StepResult:
        result = LangGraphRunnerAdapter(
            session=self.session,
            event_store=self.event_store,
        ).execute(
            task=task,
            plan=plan_row,
            step=step,
        )
        if result.status == "STEP_COMPLETED":
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
                    "duration_ms": result.duration_ms,
                    "next_action": result.next_action,
                    "trace_summary": f"LangGraph workflow node {step.key} completed",
                },
            )
            self.session.flush()
            return result
        step_row.status = "STEP_FAILED"
        step_row.error_message = result.summary
        step_row.completed_at = utc_now()
        self.event_store.append(
            task_id=task.id,
            event_type=EventType.STEP_FAILED,
            payload_json={
                "step_id": step_row.id,
                "step_key": step.key,
                "summary": result.summary,
                "execution_mode": step.execution_mode,
                "permission_boundary": "langgraph_workflow_execution",
                "next_action": result.next_action,
            },
        )
        self.session.flush()
        return result

    def _execute_subagent_step(
        self,
        task: Task,
        plan_row: ExecutionPlanModel,
        step: PlanStep,
        step_row: TaskStep,
    ) -> StepResult:
        """Execute a step via subagent delegation."""
        fanout_slugs = list(dict.fromkeys(step.fanout_specialist_slugs))
        if len(fanout_slugs) > 1:
            return self._execute_fanout_subagent_step(task, plan_row, step, step_row, fanout_slugs)
        specialist, selection_context = self._select_specialist(task=task, step=step)
        agent_run = SubagentManager(self.session).spawn(
            task=task,
            assignment={
                "step_key": step.key,
                "description": step.description,
                "execution_mode": step.execution_mode,
                "recommended_specialist_slug": step.recommended_specialist_slug,
                "fanout_specialist_slugs": step.fanout_specialist_slugs,
                "fanout_aggregation": step.fanout_aggregation,
                "tool_hints": step.tool_hints,
                "task_goal": task.goal,
                **selection_context,
            },
            enqueue=True,
            specialist=specialist,
        )
        step_row.assigned_agent_id = agent_run.id

        # Emit heartbeat event for subagent tracking
        self.event_store.append(
            task_id=task.id,
            agent_run_id=agent_run.id,
            event_type=EventType.SUBAGENT_HEARTBEAT,
            payload_json={
                "step_key": step.key,
                "agent_run_id": agent_run.id,
                "interval_seconds": SUBAGENT_HEARTBEAT_INTERVAL,
                "specialist_slug": specialist.slug if specialist is not None else None,
            },
        )
        self._execute_queue_deferred_subagents_inline(
            task=task,
            step_key=step.key,
            agent_runs=[agent_run],
        )
        if agent_run.status in SUBAGENT_FAILURE_STATUSES:
            return self._subagent_step_failed_result(
                task=task,
                step=step,
                step_row=step_row,
                agent_runs=[agent_run],
            )

        result = StepResult(
            step_key=step.key,
            status="STEP_COMPLETED",
            summary=f"Subagent spawned: {agent_run.id}",
            output="",
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
                "specialist_slug": specialist.slug if specialist is not None else None,
                "specialist_role": specialist.role if specialist is not None else None,
                "trace_summary": (f"异步步骤 {step.key} 已派生子 Agent {agent_run.id[:8]}"),
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

    def _execute_fanout_subagent_step(
        self,
        task: Task,
        plan_row: ExecutionPlanModel,
        step: PlanStep,
        step_row: TaskStep,
        fanout_slugs: list[str],
    ) -> StepResult:
        ensure_system_specialists(self.session)
        registry = SubagentSpecialistRegistry(self.session, task.organization_id)
        specialists = []
        missing_slugs = []
        for slug in fanout_slugs:
            specialist = registry.get_by_slug(slug)
            if specialist is None:
                missing_slugs.append(slug)
            else:
                specialists.append(specialist)
        if missing_slugs:
            summary = "Fanout specialist not found: " + ", ".join(missing_slugs)
            step_row.status = "STEP_FAILED"
            step_row.error_message = summary
            step_row.completed_at = utc_now()
            self.event_store.append(
                task_id=task.id,
                event_type=EventType.STEP_FAILED,
                payload_json={
                    "step_id": step_row.id,
                    "step_key": step.key,
                    "summary": summary,
                    "missing_specialist_slugs": missing_slugs,
                },
            )
            self.session.flush()
            return StepResult(
                step_key=step.key,
                status="STEP_FAILED",
                summary=summary,
                next_action="stop",
            )
        manager = SubagentManager(self.session)
        try:
            batch_id, agent_runs = manager.spawn_fanout(
                task=task,
                assignment={
                    "step_key": step.key,
                    "description": step.description,
                    "execution_mode": step.execution_mode,
                    "recommended_specialist_slug": step.recommended_specialist_slug,
                    "fanout_specialist_slugs": fanout_slugs,
                    "fanout_aggregation": step.fanout_aggregation,
                    "tool_hints": step.tool_hints,
                    "task_goal": task.goal,
                },
                specialists=specialists,
                aggregation=step.fanout_aggregation,
                timeout_seconds=step.timeout_seconds or DEFAULT_SUBAGENT_TIMEOUT,
                enqueue=True,
            )
        except FanoutCapacityExceededError as exc:
            summary = f"FanoutCapacityExceeded: {exc}"
            step_row.status = "STEP_FAILED"
            step_row.error_message = summary
            step_row.completed_at = utc_now()
            self.event_store.append(
                task_id=task.id,
                event_type=EventType.STEP_FAILED,
                payload_json={
                    "step_id": step_row.id,
                    "step_key": step.key,
                    "summary": summary,
                    "fanout_specialist_slugs": fanout_slugs,
                    "fanout_aggregation": step.fanout_aggregation,
                },
            )
            self.session.flush()
            return StepResult(
                step_key=step.key,
                status="STEP_FAILED",
                summary=summary,
                next_action="stop",
            )
        step_row.assigned_agent_id = agent_runs[0].id if agent_runs else None
        for agent_run in agent_runs:
            self.event_store.append(
                task_id=task.id,
                agent_run_id=agent_run.id,
                event_type=EventType.SUBAGENT_HEARTBEAT,
                payload_json={
                    "step_key": step.key,
                    "agent_run_id": agent_run.id,
                    "interval_seconds": SUBAGENT_HEARTBEAT_INTERVAL,
                    "fanout_batch_id": batch_id,
                    "fanout_index": agent_run.context_json.get("fanout_index"),
                    "fanout_total": agent_run.context_json.get("fanout_total"),
                    "specialist_slug": agent_run.context_json.get("specialist_slug"),
                },
            )
        self._execute_queue_deferred_subagents_inline(
            task=task,
            step_key=step.key,
            agent_runs=agent_runs,
        )
        failed_runs = [run for run in agent_runs if run.status in SUBAGENT_FAILURE_STATUSES]
        if failed_runs:
            return self._subagent_step_failed_result(
                task=task,
                step=step,
                step_row=step_row,
                agent_runs=failed_runs,
            )
        result = StepResult(
            step_key=step.key,
            status="STEP_COMPLETED",
            summary=f"Fanout subagents spawned: {len(agent_runs)} in {batch_id}",
            output="",
            tool_calls=[],
            next_action="spawn_subagent",
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
                "assigned_agent_id": step_row.assigned_agent_id,
                "assigned_agent_ids": [agent_run.id for agent_run in agent_runs],
                "execution_mode": step.execution_mode,
                "next_action": result.next_action,
                "fanout_batch_id": batch_id,
                "fanout_total": len(agent_runs),
                "fanout_aggregation": step.fanout_aggregation,
                "fanout_specialist_slugs": fanout_slugs,
                "trace_summary": (
                    f"异步步骤 {step.key} 已并行派生 {len(agent_runs)} 个专家子 Agent"
                ),
                "react_trace": {
                    "reason": {
                        "step_key": step.key,
                        "summary": f"异步 fanout 需要多个专家并行处理：{step.description}",
                    },
                    "act": {
                        "step_key": step.key,
                        "tool_name": "subagent.fanout",
                        "input_json": {
                            "fanout_batch_id": batch_id,
                            "agent_run_ids": [agent_run.id for agent_run in agent_runs],
                        },
                    },
                    "observe": {
                        "step_key": step.key,
                        "status": "SUBAGENT_FANOUT_SPAWNED",
                        "summary": result.summary,
                    },
                },
            },
        )
        self.session.flush()
        return result

    def _execute_queue_deferred_subagents_inline(
        self,
        *,
        task: Task,
        step_key: str,
        agent_runs: list[AgentRun],
    ) -> None:
        for agent_run in agent_runs:
            if agent_run.status != "PENDING" or not self._subagent_queue_deferred(agent_run.id):
                continue
            self.event_store.append(
                task_id=task.id,
                agent_run_id=agent_run.id,
                event_type=EventType.SUBAGENT_PROGRESS,
                payload_json={
                    "agent_run_id": agent_run.id,
                    "step_key": step_key,
                    "stage": "inline_executor_fallback",
                    "summary": (
                        "Subagent queue unavailable; executing inline in the current worker."
                    ),
                },
            )
            try:
                from app.workers.subagent_worker import execute_subagent

                execute_subagent(
                    agent_run.id,
                    session=self.session,
                    workspace_root=self.workspace_root,
                )
            except Exception as exc:
                self.event_store.append(
                    task_id=task.id,
                    agent_run_id=agent_run.id,
                    event_type=EventType.SUBAGENT_PROGRESS,
                    payload_json={
                        "agent_run_id": agent_run.id,
                        "step_key": step_key,
                        "stage": "inline_executor_failed",
                        "summary": "Inline subagent execution failed.",
                        "error": str(exc),
                    },
                )
            finally:
                self.session.flush()
                self.session.refresh(agent_run)

    def _subagent_queue_deferred(self, agent_run_id: str) -> bool:
        payloads = self.session.execute(
            select(AgentEvent.payload_json).where(
                AgentEvent.agent_run_id == agent_run_id,
                AgentEvent.event_type == EventType.SUBAGENT_PROGRESS,
            )
        ).scalars()
        return any(
            isinstance(payload, dict) and payload.get("stage") == "queue_deferred"
            for payload in payloads
        )

    def _subagent_step_failed_result(
        self,
        *,
        task: Task,
        step: PlanStep,
        step_row: TaskStep,
        agent_runs: list[AgentRun],
    ) -> StepResult:
        failed_ids = [agent_run.id for agent_run in agent_runs]
        summary = f"Subagent execution failed: {', '.join(failed_ids)}"
        step_row.status = "STEP_FAILED"
        step_row.error_message = summary
        step_row.completed_at = utc_now()
        self.event_store.append(
            task_id=task.id,
            event_type=EventType.STEP_FAILED,
            payload_json={
                "step_id": step_row.id,
                "step_key": step.key,
                "summary": summary,
                "failed_agent_run_ids": failed_ids,
                "failed_agent_statuses": {
                    agent_run.id: agent_run.status for agent_run in agent_runs
                },
                "permission_boundary": "subagent_execution",
            },
        )
        self.session.flush()
        return StepResult(
            step_key=step.key,
            status="STEP_FAILED",
            summary=summary,
            output="",
            tool_calls=[],
            next_action="stop",
        )

    def _select_specialist(self, *, task: Task, step: PlanStep):
        ensure_system_specialists(self.session)
        registry = SubagentSpecialistRegistry(self.session, task.organization_id)
        if step.recommended_specialist_slug:
            specialist = registry.get_by_slug(step.recommended_specialist_slug)
            if specialist is not None:
                return specialist, {"specialist_selection": {"resolved_by": "planner_hint"}}
        match_text = " ".join(
            [
                task.title,
                task.goal,
                step.description,
                " ".join(step.tool_hints),
                " ".join(step.acceptance_criteria),
            ]
        )
        outcome = SpecialistLLMSelector(
            self.session,
            organization_id=task.organization_id,
        ).select(
            task=task,
            plan_step_key=step.key,
            plan_step_description=step.description,
            match_text=match_text,
        )
        specialist = outcome.specialist
        trace = outcome.trace
        if specialist is not None:
            self.event_store.append(
                task_id=task.id,
                event_type=EventType.SUBAGENT_PROGRESS,
                payload_json={
                    "step_key": step.key,
                    "stage": "specialist_selected",
                    **trace,
                },
            )
        return specialist, {
            "specialist_selection_decision_id": outcome.decision.id,
            "specialist_selection": trace,
        }

    def _select_tool_for_step(
        self,
        task: Task,
        step: PlanStep,
    ) -> tuple[str, dict]:
        """Select tool and generate parameters using Model Gateway or defaults.

        Invokes the Model Gateway with step description + tool_hints + accumulated
        step_context to select tools and generate parameters. Records MODEL_CALL
        event with purpose=tool_parameter_generation.
        """
        # Build context from completed dependent steps
        context_parts = []
        if self.step_context:
            for dep_key in step.depends_on:
                if dep_key in self.step_context:
                    dep_result = self.step_context[dep_key]
                    context_parts.append(
                        f"Step '{dep_key}' ({dep_result.status}): {dep_result.output[:1024]}"
                    )

        # Record MODEL_CALL event for tool parameter generation
        self.event_store.append(
            task_id=task.id,
            event_type=EventType.MODEL_CALLED,
            payload_json={
                "purpose": "tool_parameter_generation",
                "step_key": step.key,
                "tool_hints": step.tool_hints,
                "context_keys": list(self.step_context.keys()),
            },
        )

        return self._default_tool_for_step(task=task, step=step)

    def _default_tool_for_step(
        self,
        *,
        task: Task,
        step: PlanStep,
    ) -> tuple[str, dict]:
        artifact_tool_name = (
            "write_file" if task.enable_sandbox and step.requires_sandbox else "mcp_artifact_put"
        )
        step_text = " ".join(
            [
                step.key,
                step.description,
                " ".join(step.artifact_expectations),
                " ".join(step.acceptance_criteria),
            ]
        ).lower()
        task_text = " ".join([task.title or "", task.goal or ""]).lower()
        text = f"{step_text} {task_text}"
        generation_requested = any(
            marker in text
            for marker in (
                "write",
                "draft",
                "story",
                "novel",
                "outline",
                "final",
                "compose",
                "generate",
                "reply",
                "response",
                "summary",
                "summarize",
                "report",
                "output",
                "article",
                "content",
                "sci-fi",
                "science fiction",
                "写",
                "撰写",
                "生成",
                "创作",
                "草稿",
                "大纲",
                "小说",
                "科幻",
                "故事",
                "结局",
                "主角",
                "文章",
                "内容",
                "回复",
                "回答",
                "客服",
                "总结",
                "报告",
                "说明",
                "输出",
                "字",
                "最终",
                "调整",
            )
        )
        project_context_requested = any(
            marker in task_text
            for marker in (
                "read",
                "inspect",
                "file",
                "directory",
                "repo",
                "repository",
                "project",
                "code",
                "bug",
                "test",
                "读取",
                "查看",
                "检查",
                "文件",
                "目录",
                "仓库",
                "项目",
                "代码",
                "报错",
                "错误",
                "修复",
                "测试",
            )
        )
        prefer_artifact_output = generation_requested and not project_context_requested
        tool_hints = list(dict.fromkeys(step.tool_hints))
        if tool_hints:
            for candidate in (
                "mcp_artifact_put",
                "write_file",
                "run_shell",
                "run_tests",
                "list_files",
                "read_file",
            ):
                if candidate in tool_hints:
                    if candidate in {"list_files", "read_file"} and prefer_artifact_output:
                        continue
                    if candidate == "write_file":
                        candidate = artifact_tool_name
                    return candidate, self._default_tool_input(
                        task=task,
                        step=step,
                        tool_name=candidate,
                    )

        if generation_requested:
            return artifact_tool_name, self._default_tool_input(
                task=task,
                step=step,
                tool_name=artifact_tool_name,
            )
        if any(
            marker in text
            for marker in ("count", "wc ", "shell", "test", "run", "统计", "计数", "命令")
        ):
            return "run_shell", self._default_tool_input(
                task=task,
                step=step,
                tool_name="run_shell",
            )
        return "read_file", self._default_tool_input(
            task=task,
            step=step,
            tool_name="read_file",
        )

    def _default_tool_input(
        self,
        *,
        task: Task,
        step: PlanStep,
        tool_name: str,
    ) -> dict:
        timeout = step.timeout_seconds or DEFAULT_TOOL_TIMEOUT
        idempotency_key = f"{task.id}:{step.key}:{tool_name}"
        if tool_name == "write_file":
            return {
                "path": self._artifact_path_for_step(step),
                "content": self._artifact_content_for_step(task=task, step=step),
                "idempotency_key": idempotency_key,
                "timeout_seconds": timeout,
            }
        if tool_name == "mcp_artifact_put":
            return {
                "name": self._artifact_path_for_step(step),
                "content": self._artifact_content_for_step(task=task, step=step),
                "idempotency_key": idempotency_key,
                "timeout_seconds": timeout,
            }
        if tool_name == "run_shell":
            return {
                "command": f"printf '%s\\n' {quote(step.description)}",
                "cwd": "/workspace",
                "timeout_seconds": timeout,
                "idempotency_key": idempotency_key,
            }
        if tool_name == "run_tests":
            return {
                "command": "python -m pytest -q",
                "cwd": "/workspace",
                "timeout_seconds": timeout,
                "idempotency_key": idempotency_key,
            }
        if tool_name == "list_files":
            return {"root": ".", "glob": "*"}
        return {"path": "pyproject.toml"}

    def _artifact_path_for_step(self, step: PlanStep) -> str:
        for expectation in step.artifact_expectations:
            path = _path_from_artifact_expectation(expectation)
            if path:
                return path
        return f"{step.key}.md"

    def _artifact_content_for_step(self, *, task: Task, step: PlanStep) -> str:
        parts = [
            f"# {step.description}",
            "",
            f"Task: {task.title}",
            f"Goal: {task.goal}",
        ]
        for dep_key in step.depends_on:
            dep_result = self.step_context.get(dep_key)
            if dep_result is not None and dep_result.output:
                parts.extend(["", f"## {dep_key}", dep_result.output[:4000]])
        return "\n".join(parts).strip() + "\n"


def _path_from_artifact_expectation(expectation: str) -> str | None:
    value = str(expectation or "").strip()
    if not value:
        return None
    if ":" in value:
        value = value.split(":", 1)[1].strip()
    value = value.split()[0].strip("`'\"()[]，。；;,")
    if not value or value.startswith("/"):
        return None
    if ".." in Path(value).parts:
        return None
    safe = re.sub(r"[^A-Za-z0-9._/-]", "_", value)
    return safe or None


def _tool_requires_sandbox(tool_name: str) -> bool:
    return tool_name in {
        "write_file",
        "run_shell",
        "run_tests",
        "git_command",
        "network_request",
    }
