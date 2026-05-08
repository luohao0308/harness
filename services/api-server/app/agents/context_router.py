from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.model_gateway import (
    DEFAULT_MODEL_SETTINGS,
    MODEL_SETTINGS_KEY,
    ModelMessage,
    ModelRequest,
    ModelSettingsResolver,
)
from app.db.models import (
    AgentEvent,
    AgentRun,
    ExecutionPlan,
    ModelCall,
    SystemSetting,
    Task,
    ToolCall,
    utc_now,
)
from app.events.event_store import EventStore
from app.events.event_types import EventType


class RunContextRouter:
    def __init__(self, session: Session) -> None:
        self.session = session

    def build(
        self,
        *,
        task: Task,
        persist_events: bool = False,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        plan = self._latest_plan(task.id)
        events = self._events(task.id)
        model_calls = self._model_calls(task.id)
        tool_calls = self._tool_calls(task.id)
        subagents = self._subagents(task.id)
        task_type = self._classify_task_type(task=task, plan=plan, tool_calls=tool_calls)
        routing = self._route_model(task=task, task_type=task_type)
        compression = self._compress_trace(
            events=events,
            model_calls=model_calls,
            tool_calls=tool_calls,
            subagents=subagents,
        )
        generated_at = utc_now()
        context = {
            "task_id": task.id,
            "generated_at": generated_at.isoformat(),
            "working_memory": self._working_memory(task=task, plan=plan),
            "long_term_memory": self._long_term_memory(task=task),
            "artifact_memory": self._artifact_memory(tool_calls=tool_calls, subagents=subagents),
            "rag_context": self._rag_context(tool_calls=tool_calls),
            "trace_memory": self._trace_memory(events=events),
            "context_compression": compression,
            "model_routing": routing,
            "latest_agent_router": self._latest_agent_router(events=events),
        }
        if persist_events:
            self._append_context_events(
                task=task,
                context=context,
                actor_id=actor_id,
                generated_at=generated_at,
            )
        return context

    def _append_context_events(
        self,
        *,
        task: Task,
        context: dict[str, Any],
        actor_id: str | None,
        generated_at: datetime,
    ) -> None:
        event_store = EventStore(self.session)
        compression = context["context_compression"]
        routing = context["model_routing"]
        event_store.append(
            task_id=task.id,
            event_type=EventType.CONTEXT_COMPRESSED,
            payload_json={
                "task_id": task.id,
                "generated_at": generated_at.isoformat(),
                "original_event_count": compression["original_event_count"],
                "retained_event_count": compression["retained_event_count"],
                "omitted_event_count": compression["omitted_event_count"],
                "retained_sequences": compression["retained_sequences"],
                "compression_strategy": compression["compression_strategy"],
            },
            actor_type="user" if actor_id else "system",
            actor_id=actor_id,
        )
        event_store.append(
            task_id=task.id,
            event_type=EventType.MODEL_ROUTED,
            payload_json={
                "task_id": task.id,
                "task_type": routing["task_type"],
                "model_provider": routing["selected_provider"],
                "model_name": routing["selected_model"],
                "model_class": routing["model_class"],
                "reasoning": routing["reasoning"],
                "routing_policy": routing["routing_policy"],
            },
            actor_type="user" if actor_id else "system",
            actor_id=actor_id,
        )

    def _latest_plan(self, task_id: str) -> ExecutionPlan | None:
        return self.session.execute(
            select(ExecutionPlan)
            .where(ExecutionPlan.task_id == task_id)
            .order_by(ExecutionPlan.version.desc())
            .limit(1)
        ).scalar_one_or_none()

    def _events(self, task_id: str) -> list[AgentEvent]:
        return list(
            self.session.execute(
                select(AgentEvent)
                .where(AgentEvent.task_id == task_id)
                .order_by(AgentEvent.sequence.asc())
            ).scalars()
        )

    def _model_calls(self, task_id: str) -> list[ModelCall]:
        return list(
            self.session.execute(
                select(ModelCall)
                .where(ModelCall.task_id == task_id)
                .order_by(ModelCall.created_at.asc())
            ).scalars()
        )

    def _tool_calls(self, task_id: str) -> list[ToolCall]:
        return list(
            self.session.execute(
                select(ToolCall)
                .where(ToolCall.task_id == task_id)
                .order_by(ToolCall.created_at.asc())
            ).scalars()
        )

    def _subagents(self, task_id: str) -> list[AgentRun]:
        return list(
            self.session.execute(
                select(AgentRun)
                .where(AgentRun.task_id == task_id, AgentRun.agent_type == "subagent")
                .order_by(AgentRun.started_at.asc(), AgentRun.id.asc())
            ).scalars()
        )

    def _working_memory(self, *, task: Task, plan: ExecutionPlan | None) -> dict[str, Any]:
        steps = []
        if plan is not None and isinstance(plan.plan_json.get("steps"), list):
            steps = [
                {
                    "key": str(step.get("key") or step.get("step_key") or ""),
                    "description": str(step.get("description") or ""),
                    "execution_mode": str(step.get("execution_mode") or ""),
                    "risk_level": str(step.get("risk_level") or "low"),
                }
                for step in plan.plan_json["steps"]
                if isinstance(step, dict)
            ]
        return {
            "title": task.title,
            "goal": task.goal,
            "status": task.status,
            "plan_version": plan.version if plan is not None else None,
            "plan_status": plan.status if plan is not None else None,
            "plan_summary": plan.plan_json.get("summary") if plan is not None else None,
            "step_count": len(steps),
            "active_steps": steps[:8],
        }

    def _long_term_memory(self, *, task: Task) -> dict[str, Any]:
        rows = list(
            self.session.execute(
                select(Task)
                .where(
                    Task.organization_id == task.organization_id,
                    Task.id != task.id,
                    Task.status == "COMPLETED",
                )
                .order_by(Task.completed_at.desc())
                .limit(3)
            ).scalars()
        )
        return {
            "source": "completed_runs_same_org",
            "item_count": len(rows),
            "items": [
                {
                    "task_id": row.id,
                    "title": row.title,
                    "goal": row.goal[:240],
                    "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                }
                for row in rows
            ],
        }

    def _artifact_memory(
        self,
        *,
        tool_calls: list[ToolCall],
        subagents: list[AgentRun],
    ) -> dict[str, Any]:
        artifact_like_tools = [
            call
            for call in tool_calls
            if isinstance(call.output_json, dict)
            and any(key in call.output_json for key in ["path", "content", "files", "artifact"])
        ]
        subagent_artifacts = []
        for subagent in subagents:
            context = subagent.context_json if isinstance(subagent.context_json, dict) else {}
            artifacts = context.get("artifacts", [])
            if not isinstance(artifacts, list):
                artifacts = []
            for artifact in artifacts:
                if isinstance(artifact, dict):
                    subagent_artifacts.append(artifact)
        return {
            "tool_artifact_count": len(artifact_like_tools),
            "subagent_artifact_count": len(subagent_artifacts),
            "recent_tool_artifacts": [
                {
                    "tool_call_id": call.id,
                    "tool_name": call.tool_name,
                    "status": call.status,
                    "summary": self._summarize_json(call.output_json),
                }
                for call in artifact_like_tools[-5:]
            ],
            "recent_subagent_artifacts": subagent_artifacts[-5:],
        }

    def _rag_context(self, *, tool_calls: list[ToolCall]) -> dict[str, Any]:
        rag_calls = [
            call
            for call in tool_calls
            if call.tool_name in {"mcp_context_search", "browser_search", "http_request"}
        ]
        return {
            "source": "tool_trace",
            "retrieval_count": len(rag_calls),
            "items": [
                {
                    "tool_call_id": call.id,
                    "tool_name": call.tool_name,
                    "status": call.status,
                    "query": (
                        call.input_json.get("query")
                        if isinstance(call.input_json, dict)
                        else None
                    ),
                    "summary": self._summarize_json(call.output_json),
                }
                for call in rag_calls[-5:]
            ],
        }

    def _trace_memory(self, *, events: list[AgentEvent]) -> dict[str, Any]:
        counts = Counter(event.event_type for event in events)
        failure = next(
            (
                event
                for event in reversed(events)
                if event.event_type.endswith("FAILED") or event.event_type in {"POLICY_DENIED"}
            ),
            None,
        )
        return {
            "event_count": len(events),
            "last_sequence": events[-1].sequence if events else 0,
            "event_type_counts": dict(counts),
            "failure_point": self._event_summary(failure) if failure is not None else None,
            "recent_events": [self._event_summary(event) for event in events[-8:]],
        }

    def _compress_trace(
        self,
        *,
        events: list[AgentEvent],
        model_calls: list[ModelCall],
        tool_calls: list[ToolCall],
        subagents: list[AgentRun],
    ) -> dict[str, Any]:
        retained = events[-8:]
        status_counts = Counter(event.event_type for event in events)
        return {
            "compression_strategy": "retain_recent_8_plus_aggregate_counts",
            "original_event_count": len(events),
            "retained_event_count": len(retained),
            "omitted_event_count": max(len(events) - len(retained), 0),
            "retained_sequences": [event.sequence for event in retained],
            "model_call_count": len(model_calls),
            "tool_call_count": len(tool_calls),
            "subagent_count": len(subagents),
            "status_counts": dict(status_counts),
            "prompt_tokens": sum(call.prompt_tokens for call in model_calls),
            "completion_tokens": sum(call.completion_tokens for call in model_calls),
            "tool_latency_ms": sum(call.duration_ms for call in tool_calls),
            "model_latency_ms": sum(call.duration_ms for call in model_calls),
        }

    def _route_model(self, *, task: Task, task_type: str) -> dict[str, Any]:
        request_payload = ModelRequest(
            model_provider=task.model_provider or "default",
            model_name=task.model_name or "default",
            messages=[ModelMessage(role="user", content=task.goal[:2000])],
        )
        resolved_request, _settings = ModelSettingsResolver(self.session).resolve(
            task_id=task.id,
            request_payload=request_payload,
        )
        settings = self._settings_for_org(task.organization_id)
        routing_policy = self._routing_policy(
            settings=settings,
            default_model=resolved_request.model_name,
        )
        policy_entry = routing_policy.get(task_type, routing_policy["general"])
        explicit_task_model = task.model_name not in {"", "default", None}
        explicit_task_provider = task.model_provider not in {"", "default", None}
        selected_provider = (
            resolved_request.model_provider
            if explicit_task_provider
            else str(policy_entry.get("provider") or resolved_request.model_provider)
        )
        selected_model = (
            resolved_request.model_name
            if explicit_task_model
            else str(policy_entry.get("model") or resolved_request.model_name)
        )
        model_class = str(policy_entry.get("model_class") or task_type)
        decision_source = (
            "task override"
            if explicit_task_model or explicit_task_provider
            else "routing policy"
        )
        reason = (
            f"task_type={task_type}; {decision_source} "
            f"selected {selected_provider}/{selected_model}"
        )
        return {
            "task_type": task_type,
            "selected_provider": selected_provider,
            "selected_model": selected_model,
            "model_class": model_class,
            "reasoning": reason,
            "routing_policy": routing_policy,
            "explicit_task_override": explicit_task_model or explicit_task_provider,
        }

    def _settings_for_org(self, organization_id: str | None) -> dict[str, Any]:
        if organization_id is None:
            return dict(DEFAULT_MODEL_SETTINGS)
        setting = self.session.execute(
            select(SystemSetting).where(
                SystemSetting.organization_id == organization_id,
                SystemSetting.key == MODEL_SETTINGS_KEY,
            )
        ).scalar_one_or_none()
        if setting is None:
            return dict(DEFAULT_MODEL_SETTINGS)
        if not isinstance(setting.value_json, dict):
            return dict(DEFAULT_MODEL_SETTINGS)
        return setting.value_json

    def _routing_policy(
        self,
        *,
        settings: dict[str, Any],
        default_model: str,
    ) -> dict[str, dict[str, str]]:
        configured = settings.get("model_router")
        base = {
            "planning": {
                "provider": settings.get("default_provider", "openai-compatible"),
                "model": default_model,
                "model_class": "strong-planning",
            },
            "coding": {
                "provider": settings.get("default_provider", "openai-compatible"),
                "model": default_model,
                "model_class": "strong-coding",
            },
            "grading": {
                "provider": settings.get("default_provider", "openai-compatible"),
                "model": default_model,
                "model_class": "stable-grading",
            },
            "guardrail": {
                "provider": settings.get("default_provider", "openai-compatible"),
                "model": default_model,
                "model_class": "fast-guardrail",
            },
            "summarization": {
                "provider": settings.get("default_provider", "openai-compatible"),
                "model": default_model,
                "model_class": "long-context-summarization",
            },
            "general": {
                "provider": settings.get("default_provider", "openai-compatible"),
                "model": default_model,
                "model_class": "general",
            },
        }
        if isinstance(configured, dict):
            for key, value in configured.items():
                if key in base and isinstance(value, dict):
                    base[key] = {**base[key], **{str(k): str(v) for k, v in value.items()}}
        return base

    def _classify_task_type(
        self,
        *,
        task: Task,
        plan: ExecutionPlan | None,
        tool_calls: list[ToolCall],
    ) -> str:
        haystack = f"{task.title}\n{task.goal}".lower()
        if plan is not None:
            haystack += "\n" + str(plan.plan_json).lower()
        haystack += "\n" + " ".join(call.tool_name.lower() for call in tool_calls)
        checks = [
            (
                "guardrail",
                ["guardrail", "policy", "approval", "permission", "secret", "安全策略", "审批"],
            ),
            ("grading", ["eval", "grader", "regression", "score", "评测", "评分", "回归"]),
            ("coding", ["code", "github", "bug", "test", "pytest", "react", "api", "代码", "修复"]),
            (
                "summarization",
                ["summarize", "summary", "compress", "report", "总结", "压缩", "报告"],
            ),
            ("planning", ["plan", "planner", "decompose", "architecture", "规划", "分解", "架构"]),
        ]
        for task_type, keywords in checks:
            if any(keyword in haystack for keyword in keywords):
                return task_type
        return "general"

    def _latest_agent_router(self, *, events: list[AgentEvent]) -> dict[str, Any] | None:
        for event in reversed(events):
            if event.event_type == EventType.AGENT_SELECTED.value:
                return {
                    "sequence": event.sequence,
                    "trace_id": event.trace_id,
                    "payload_json": event.payload_json,
                    "created_at": event.created_at.isoformat(),
                }
        return None

    def _event_summary(self, event: AgentEvent | None) -> dict[str, Any] | None:
        if event is None:
            return None
        return {
            "sequence": event.sequence,
            "event_type": event.event_type,
            "trace_id": event.trace_id,
            "payload_summary": self._summarize_json(event.payload_json),
            "created_at": event.created_at.isoformat(),
        }

    def _summarize_json(self, value: Any) -> str:
        if not isinstance(value, dict) or not value:
            return "empty"
        keys = ", ".join(sorted(str(key) for key in value.keys())[:8])
        return f"{len(value)} fields: {keys}"

    def organization_context_summary(self, *, organization_id: str | None) -> dict[str, int]:
        return {
            "completed_run_count": int(
                self.session.execute(
                    select(func.count(Task.id)).where(
                        Task.organization_id == organization_id,
                        Task.status == "COMPLETED",
                    )
                ).scalar_one()
                or 0
            )
        }
