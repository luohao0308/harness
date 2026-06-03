from __future__ import annotations

import importlib.util
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from sqlalchemy.orm import Session

from app.agents.schemas import PlanStep, StepResult
from app.core.config import feature_enabled
from app.db.models import ExecutionPlan as ExecutionPlanModel
from app.db.models import Task
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.tools.capabilities import CapabilityRegistry, stable_json_sha256

if TYPE_CHECKING:
    from app.tools.capabilities import AttachedLangGraphWorkflow


@dataclass(frozen=True)
class LangGraphRuntimeErrorInfo:
    code: str
    message: str
    metadata: dict


@dataclass(frozen=True)
class LangGraphBridgeResult:
    summary: str
    output: str = ""
    metadata: dict = field(default_factory=dict)


class LangGraphSandboxBridge(Protocol):
    def invoke(
        self,
        *,
        workflow: AttachedLangGraphWorkflow,
        task: Task,
        plan: ExecutionPlanModel,
        step: PlanStep,
    ) -> LangGraphBridgeResult: ...


_langgraph_sandbox_bridge: LangGraphSandboxBridge | None = None


def set_langgraph_sandbox_bridge(bridge: LangGraphSandboxBridge | None) -> None:
    global _langgraph_sandbox_bridge
    _langgraph_sandbox_bridge = bridge


def get_langgraph_sandbox_bridge() -> LangGraphSandboxBridge | None:
    return _langgraph_sandbox_bridge


class LangGraphRunnerAdapter:
    """Harness-owned LangGraph execution boundary.

    V1 intentionally fails closed unless the execution feature flag and optional
    dependency are present. LangGraph state/checkpoints are never authoritative.
    """

    def __init__(self, *, session: Session, event_store: EventStore) -> None:
        self.session = session
        self.event_store = event_store

    def execute(
        self,
        *,
        task: Task,
        plan: ExecutionPlanModel,
        step: PlanStep,
    ) -> StepResult:
        started_at = time.monotonic()
        workflow = self._select_workflow(task=task, step=step)
        workflow_payload = self._workflow_event_payload(
            workflow=workflow,
            task=task,
            plan=plan,
            step=step,
        )
        self.event_store.append(
            task_id=task.id,
            event_type=EventType.LANGGRAPH_WORKFLOW_STARTED,
            payload_json=workflow_payload,
        )
        self.event_store.append(
            task_id=task.id,
            event_type=EventType.LANGGRAPH_NODE_STARTED,
            payload_json={**workflow_payload, "node_key": step.key},
        )
        bridge = get_langgraph_sandbox_bridge()
        error = self._runtime_error(workflow=workflow, bridge=bridge)
        if error is not None:
            denied_payload = {
                **workflow_payload,
                "node_key": step.key,
                "requested_bridge": "langgraph_runtime",
                "status": "DENIED",
                "denial_code": error.code,
                "reason": error.message,
            }
            self.event_store.append(
                task_id=task.id,
                event_type=EventType.LANGGRAPH_TOOL_NODE_REQUESTED,
                payload_json={**denied_payload, "requested_bridge": "workflow.invoke"},
            )
            self.event_store.append(
                task_id=task.id,
                event_type=EventType.LANGGRAPH_TOOL_NODE_DENIED,
                payload_json=denied_payload,
            )
            self.event_store.append(
                task_id=task.id,
                event_type=EventType.LANGGRAPH_NODE_FAILED,
                payload_json={**denied_payload, "error": error.metadata},
            )
            self.event_store.append(
                task_id=task.id,
                event_type=EventType.LANGGRAPH_WORKFLOW_FAILED,
                payload_json={**workflow_payload, "error": error.metadata},
            )
            return StepResult(
                step_key=step.key,
                status="STEP_FAILED",
                summary=error.message,
                output="",
                tool_calls=[],
                duration_ms=int((time.monotonic() - started_at) * 1000),
                next_action="stop",
            )
        assert workflow is not None
        assert bridge is not None
        requested_payload = {
            **workflow_payload,
            "node_key": step.key,
            "requested_bridge": "workflow.invoke",
            "status": "REQUESTED",
        }
        self.event_store.append(
            task_id=task.id,
            event_type=EventType.LANGGRAPH_TOOL_NODE_REQUESTED,
            payload_json=requested_payload,
        )
        try:
            bridge_result = bridge.invoke(workflow=workflow, task=task, plan=plan, step=step)
        except Exception as exc:  # pragma: no cover - exercised through integration tests if needed
            error_payload = {
                **workflow_payload,
                "node_key": step.key,
                "status": "FAILED",
                "error": {
                    "typed_error": "langgraph_bridge_failed",
                    "message": str(exc),
                },
            }
            if isinstance(exc, PermissionError):
                denied_payload = {
                    **error_payload,
                    "status": "DENIED",
                    "denial_code": "langgraph_bridge_permission_denied",
                    "reason": str(exc),
                }
                self.event_store.append(
                    task_id=task.id,
                    event_type=EventType.LANGGRAPH_TOOL_NODE_DENIED,
                    payload_json=denied_payload,
                )
            self.event_store.append(
                task_id=task.id,
                event_type=EventType.LANGGRAPH_NODE_FAILED,
                payload_json=error_payload,
            )
            self.event_store.append(
                task_id=task.id,
                event_type=EventType.LANGGRAPH_WORKFLOW_FAILED,
                payload_json=error_payload,
            )
            return StepResult(
                step_key=step.key,
                status="STEP_FAILED",
                summary="LangGraph sandbox bridge failed",
                output="",
                tool_calls=[],
                duration_ms=int((time.monotonic() - started_at) * 1000),
                next_action="stop",
            )
        completed_payload = {
            **workflow_payload,
            "node_key": step.key,
            "bridge": "harness_langgraph_sandbox_runner",
            "status": "COMPLETED",
            "result": bridge_result.metadata,
        }
        self.event_store.append(
            task_id=task.id,
            event_type=EventType.LANGGRAPH_TOOL_NODE_COMPLETED,
            payload_json=completed_payload,
        )
        self.event_store.append(
            task_id=task.id,
            event_type=EventType.LANGGRAPH_NODE_COMPLETED,
            payload_json=completed_payload,
        )
        self.event_store.append(
            task_id=task.id,
            event_type=EventType.LANGGRAPH_WORKFLOW_COMPLETED,
            payload_json={**workflow_payload, "status": "COMPLETED"},
        )
        return StepResult(
            step_key=step.key,
            status="STEP_COMPLETED",
            summary=bridge_result.summary,
            output=bridge_result.output,
            tool_calls=[],
            duration_ms=int((time.monotonic() - started_at) * 1000),
            next_action="continue",
        )

    def _select_workflow(
        self,
        *,
        task: Task,
        step: PlanStep,
    ) -> AttachedLangGraphWorkflow | None:
        if task.agent_id is None:
            return None
        workflows = CapabilityRegistry(
            self.session,
            task.organization_id,
        ).attached_langgraph_workflows(task.agent_id)
        if not workflows:
            return None
        hinted_graphs = {hint.removeprefix("langgraph:") for hint in step.tool_hints}
        for workflow in workflows:
            if workflow.graph_id in hinted_graphs or workflow.version.id in hinted_graphs:
                return workflow
        return workflows[0]

    def _runtime_error(
        self,
        *,
        workflow: AttachedLangGraphWorkflow | None,
        bridge: LangGraphSandboxBridge | None,
    ) -> LangGraphRuntimeErrorInfo | None:
        if workflow is None:
            return LangGraphRuntimeErrorInfo(
                code="langgraph_workflow_not_attached",
                message="Agent has no approved LangGraph workflow attachment",
                metadata={"typed_error": "langgraph_workflow_not_attached"},
            )
        if not feature_enabled("langgraph_workflow_execution_enabled"):
            return LangGraphRuntimeErrorInfo(
                code="langgraph_execution_disabled",
                message="LangGraph workflow execution is disabled by feature flag",
                metadata={
                    "typed_error": "langgraph_execution_disabled",
                    "feature_flag": "langgraph_workflow_execution_enabled",
                },
            )
        if importlib.util.find_spec("langgraph") is None:
            return LangGraphRuntimeErrorInfo(
                code="missing_optional_dependency",
                message="Optional dependency langgraph is not installed",
                metadata={"typed_error": "missing_optional_dependency", "package": "langgraph"},
            )
        if bridge is None:
            return LangGraphRuntimeErrorInfo(
                code="langgraph_sandbox_bridge_unavailable",
                message="LangGraph sandbox execution bridge is not configured",
                metadata={
                    "typed_error": "langgraph_sandbox_bridge_unavailable",
                    "required_bridge": "harness_langgraph_sandbox_runner",
                },
            )
        return None

    def _workflow_event_payload(
        self,
        *,
        workflow: AttachedLangGraphWorkflow | None,
        task: Task,
        plan: ExecutionPlanModel,
        step: PlanStep,
    ) -> dict:
        if workflow is None:
            return {
                "task_id": task.id,
                "plan_id": plan.id,
                "step_key": step.key,
                "execution_mode": step.execution_mode,
                "execution_authority": "harness",
                "checkpoint_store_authoritative": False,
            }
        return {
            "task_id": task.id,
            "plan_id": plan.id,
            "step_key": step.key,
            "execution_mode": step.execution_mode,
            "agent_id": task.agent_id,
            "capability_id": workflow.capability.id,
            "capability_version_id": workflow.version.id,
            "capability_type": workflow.version.type,
            "content_sha256": workflow.version.content_sha256,
            "config_sha256": workflow.version.config_sha256,
            "graph_id": workflow.graph_id,
            "langgraph_json_sha256": stable_json_sha256(workflow.langgraph_json),
            "execution_authority": "harness",
            "external_effects": "harness_bridges_only",
            "checkpoint_store_authoritative": False,
        }
