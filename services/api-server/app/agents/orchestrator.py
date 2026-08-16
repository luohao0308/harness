import json
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.model_gateway import AuditedModelGateway, ModelMessage, ModelRequest
from app.db.models import (
    Agent,
    AgentAssignment,
    AgentEvent,
    AgentHandoff,
    ExecutionPlan,
    Task,
    utc_now,
)
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.observability.metrics import (
    agent_assignment_duration_seconds,
    agent_assignments_running,
    agent_assignments_total,
    agent_handoffs_total,
    agent_parallel_branches_running,
    agent_reduce_duration_seconds,
)
from app.tools.capabilities import CapabilityRegistry
from app.tools.runner import ToolRunner

AGENT_ROUTER_PROMPT_VERSION = "agent-router-v1"


class AgentRouterDecision(BaseModel):
    selected_agent_ids: list[str] = Field(default_factory=list)
    strategy: str = "parallel_fanout_reduce"
    reasoning: str = "deterministic fallback"


class MultiAgentOrchestrator:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.event_store = EventStore(session)
        self.last_router_decision: AgentRouterDecision | None = None
        self.workspace_root = Path(__file__).resolve().parents[2]

    def orchestrate(
        self,
        *,
        run: Task,
        entry_agent_id: str,
    ) -> tuple[list[AgentAssignment], list[AgentHandoff]]:
        existing = list(
            self.session.execute(
                select(AgentAssignment)
                .where(AgentAssignment.run_id == run.id)
                .order_by(AgentAssignment.created_at.asc(), AgentAssignment.id.asc())
            ).scalars()
        )
        if existing:
            handoffs = list(
                self.session.execute(
                    select(AgentHandoff)
                    .where(AgentHandoff.run_id == run.id)
                    .order_by(AgentHandoff.created_at.asc(), AgentHandoff.id.asc())
                ).scalars()
            )
            self.last_router_decision = self._router_decision_from_events(run)
            return existing, handoffs

        agents = {
            agent.id: agent
            for agent in self.session.execute(select(Agent).order_by(Agent.id.asc())).scalars()
        }
        plan = self._latest_plan(run)
        router_decision = self._route_agents(
            run=run,
            plan=plan,
            agents=list(agents.values()),
            entry_agent_id=entry_agent_id,
        )
        self.last_router_decision = router_decision
        selected_agent_ids = router_decision.selected_agent_ids
        selected_agents = [
            agents[agent_id] for agent_id in selected_agent_ids if agent_id in agents
        ]
        if not selected_agents:
            selected_agents = [agents[entry_agent_id]]

        self.event_store.append(
            task_id=run.id,
            event_type=EventType.AGENT_SELECTED,
            payload_json={
                "run_id": run.id,
                "entry_agent_id": entry_agent_id,
                "selected_agent_ids": [agent.id for agent in selected_agents],
                "strategy": router_decision.strategy,
                "router_prompt_version": AGENT_ROUTER_PROMPT_VERSION,
                "reasoning": router_decision.reasoning,
                "trace_summary": "Agent Router 已选择具名 Agent 参与编排。",
            },
        )
        self.event_store.append(
            task_id=run.id,
            event_type=EventType.AGENT_PARALLEL_FANOUT_STARTED,
            payload_json={
                "run_id": run.id,
                "selected_agent_ids": [agent.id for agent in selected_agents],
                "branch_count": len(selected_agents),
                "strategy": router_decision.strategy,
            },
        )

        now = utc_now()
        assignments: list[AgentAssignment] = []
        for agent in selected_agents:
            assignment = AgentAssignment(
                run_id=run.id,
                agent_id=agent.id,
                parent_assignment_id=None,
                step_key=None,
                role=agent.role,
                status="PENDING",
                input_json={
                    "goal": run.goal,
                    "plan_summary": plan.plan_json.get("summary") if plan is not None else None,
                    "routing_tags": agent.routing_tags,
                    "router_reasoning": router_decision.reasoning,
                },
                output_json={},
                created_at=now,
            )
            self.session.add(assignment)
            self.session.flush()
            assignments.append(assignment)
            agent_assignments_total.labels(agent_id=agent.id, role=agent.role).inc()
            self.event_store.append(
                task_id=run.id,
                event_type=EventType.AGENT_ASSIGNMENT_CREATED,
                payload_json={
                    "run_id": run.id,
                    "assignment_id": assignment.id,
                    "agent_id": agent.id,
                    "role": agent.role,
                    "status": assignment.status,
                },
            )

        handoffs: list[AgentHandoff] = []
        reducer = next(
            (assignment for assignment in assignments if assignment.agent_id == "reviewer"),
            None,
        )
        if reducer is None and assignments:
            reducer = assignments[-1]
        for assignment in assignments:
            if reducer is None or assignment.id == reducer.id:
                continue
            handoff = AgentHandoff(
                run_id=run.id,
                from_assignment_id=assignment.id,
                to_assignment_id=reducer.id,
                handoff_type="reduce_input",
                status="COMPLETED",
                payload_json={
                    "from_agent_id": assignment.agent_id,
                    "to_agent_id": reducer.agent_id,
                    "strategy": "parallel_fanout_reduce",
                },
                created_at=now,
                completed_at=now,
            )
            self.session.add(handoff)
            self.session.flush()
            handoffs.append(handoff)
            agent_handoffs_total.labels(handoff_type=handoff.handoff_type).inc()
            self.event_store.append(
                task_id=run.id,
                event_type=EventType.AGENT_HANDOFF_COMPLETED,
                payload_json={
                    "run_id": run.id,
                    "handoff_id": handoff.id,
                    "from_assignment_id": handoff.from_assignment_id,
                    "to_assignment_id": handoff.to_assignment_id,
                    "handoff_type": handoff.handoff_type,
                },
            )

        self.event_store.append(
            task_id=run.id,
            event_type=EventType.AGENT_REDUCE_STARTED,
            payload_json={
                "run_id": run.id,
                "reducer_assignment_id": reducer.id if reducer is not None else None,
            },
        )
        self.session.flush()
        return assignments, handoffs

    def routing_strategy(self, *, run: Task) -> str:
        decision = self.last_router_decision or self._router_decision_from_events(run)
        return decision.strategy if decision is not None else "parallel_fanout_reduce"

    def routing_reasoning(self, *, run: Task) -> str | None:
        decision = self.last_router_decision or self._router_decision_from_events(run)
        return decision.reasoning if decision is not None else None

    def _route_agents(
        self,
        *,
        run: Task,
        plan: ExecutionPlan | None,
        agents: list[Agent],
        entry_agent_id: str,
    ) -> AgentRouterDecision:
        fallback_ids = self._select_agents(run=run, plan=plan, entry_agent_id=entry_agent_id)
        try:
            response = AuditedModelGateway(session=self.session, task_id=run.id).complete(
                ModelRequest(
                    model_provider=run.model_provider,
                    model_name=run.model_name,
                    response_format="json_object",
                    messages=[
                        ModelMessage(
                            role="system",
                            content=(
                                "You are an Agent Router. Return strict JSON with "
                                "selected_agent_ids, strategy, and reasoning. Select only "
                                "agent IDs from the provided registry. Always include the "
                                "entry agent and include reviewer when reduce or review is useful."
                            ),
                        ),
                        ModelMessage(
                            role="user",
                            content=json.dumps(
                                {
                                    "prompt_version": AGENT_ROUTER_PROMPT_VERSION,
                                    "entry_agent_id": entry_agent_id,
                                    "goal": run.goal,
                                    "title": run.title,
                                    "plan": plan.plan_json if plan is not None else None,
                                    "available_agents": [
                                        {
                                            "id": agent.id,
                                            "role": agent.role,
                                            "description": agent.description,
                                            "routing_tags": agent.routing_tags,
                                            "tools": self._agent_capability_names(
                                                agent=agent,
                                                organization_id=run.organization_id,
                                            ),
                                            "max_parallel_assignments": (
                                                agent.max_parallel_assignments
                                            ),
                                        }
                                        for agent in agents
                                    ],
                                },
                                ensure_ascii=False,
                            ),
                        ),
                    ],
                )
            )
            decision = self._parse_router_decision(
                content=response.content,
                available_agent_ids={agent.id for agent in agents},
                entry_agent_id=entry_agent_id,
            )
            if decision.selected_agent_ids:
                return decision
        except Exception:
            pass
        return AgentRouterDecision(
            selected_agent_ids=fallback_ids,
            strategy="deterministic_fallback",
            reasoning="LLM router unavailable or returned no valid agent IDs.",
        )

    def _parse_router_decision(
        self,
        *,
        content: str,
        available_agent_ids: set[str],
        entry_agent_id: str,
    ) -> AgentRouterDecision:
        raw = json.loads(content)
        decision = AgentRouterDecision.model_validate(raw)
        if not decision.selected_agent_ids:
            return decision.model_copy(update={"selected_agent_ids": []})
        selected_agent_ids = [
            agent_id for agent_id in decision.selected_agent_ids if agent_id in available_agent_ids
        ]
        if entry_agent_id in available_agent_ids and entry_agent_id not in selected_agent_ids:
            selected_agent_ids.insert(0, entry_agent_id)
        if "reviewer" in available_agent_ids and "reviewer" not in selected_agent_ids:
            selected_agent_ids.append("reviewer")
        return decision.model_copy(
            update={
                "selected_agent_ids": list(dict.fromkeys(selected_agent_ids)),
                "strategy": decision.strategy or "llm_router",
                "reasoning": decision.reasoning or "LLM router selected agents.",
            }
        )

    def _router_decision_from_events(self, run: Task) -> AgentRouterDecision | None:
        event = self.session.execute(
            select(AgentEvent)
            .where(
                AgentEvent.task_id == run.id,
                AgentEvent.event_type == EventType.AGENT_SELECTED.value,
            )
            .order_by(AgentEvent.sequence.desc())
            .limit(1)
        ).scalar_one_or_none()
        if event is None:
            return None
        payload = event.payload_json
        return AgentRouterDecision(
            selected_agent_ids=list(payload.get("selected_agent_ids") or []),
            strategy=str(payload.get("strategy") or "parallel_fanout_reduce"),
            reasoning=str(payload.get("reasoning") or ""),
        )

    def execute_assignments(self, *, run: Task) -> tuple[list[AgentAssignment], list[AgentHandoff]]:
        assignments = list(
            self.session.execute(
                select(AgentAssignment)
                .where(AgentAssignment.run_id == run.id)
                .order_by(AgentAssignment.created_at.asc(), AgentAssignment.id.asc())
            ).scalars()
        )
        if not assignments:
            assignments, _ = self.orchestrate(run=run, entry_agent_id="default")
        handoffs = list(
            self.session.execute(
                select(AgentHandoff)
                .where(AgentHandoff.run_id == run.id)
                .order_by(AgentHandoff.created_at.asc(), AgentHandoff.id.asc())
            ).scalars()
        )

        for assignment in assignments:
            if assignment.status in {"SUCCESS", "FAILED", "CANCELLED"}:
                continue
            self.execute_assignment(run=run, assignment=assignment)

        self._reduce(run=run, assignments=assignments)
        self.session.flush()
        return assignments, handoffs

    def enqueue_assignments(self, *, run: Task) -> tuple[list[AgentAssignment], list[AgentHandoff]]:
        assignments = list(
            self.session.execute(
                select(AgentAssignment)
                .where(AgentAssignment.run_id == run.id)
                .order_by(AgentAssignment.created_at.asc(), AgentAssignment.id.asc())
            ).scalars()
        )
        if not assignments:
            assignments, _ = self.orchestrate(run=run, entry_agent_id="default")
        handoffs = list(
            self.session.execute(
                select(AgentHandoff)
                .where(AgentHandoff.run_id == run.id)
                .order_by(AgentHandoff.created_at.asc(), AgentHandoff.id.asc())
            ).scalars()
        )
        for assignment in assignments:
            if assignment.status not in {"PENDING", "QUEUED"}:
                continue
            assignment.status = "QUEUED"
            self.event_store.append(
                task_id=run.id,
                event_type=EventType.AGENT_ASSIGNMENT_QUEUED,
                payload_json={
                    "run_id": run.id,
                    "assignment_id": assignment.id,
                    "agent_id": assignment.agent_id,
                    "queue_name": "agent_assignments",
                },
            )
            self._enqueue_assignment(run=run, assignment=assignment)
        self.session.flush()
        return assignments, handoffs

    def execute_assignment(
        self,
        *,
        run: Task,
        assignment: AgentAssignment,
        runner: ToolRunner | None = None,
    ) -> AgentAssignment:
        if assignment.status == "SUCCESS":
            return assignment
        agent = self.session.get(Agent, assignment.agent_id)
        capability_registry = CapabilityRegistry(self.session, run.organization_id)
        if agent is None:
            allowed_tools = []
        else:
            registry, _snapshot = capability_registry.tool_registry_for_agent(agent.id)
            allowed_tools = sorted(registry.tools)
        runner = runner or ToolRunner(
            session=self.session,
            workspace_root=self.workspace_root,
            agent_id=assignment.agent_id,
            capability_registry=capability_registry,
        )
        tool_name, tool_input = self._assignment_tool(assignment)
        if tool_name not in allowed_tools:
            assignment.status = "FAILED"
            assignment.started_at = utc_now()
            assignment.completed_at = utc_now()
            assignment.output_json = {
                "summary": f"{assignment.agent_id} is not allowed to run {tool_name}.",
                "tool_name": tool_name,
                "allowed_tools": allowed_tools,
                "permission_boundary": "agent_capability_attachment",
            }
            self.event_store.append(
                task_id=run.id,
                event_type=EventType.AGENT_ASSIGNMENT_FAILED,
                payload_json={
                    "run_id": run.id,
                    "assignment_id": assignment.id,
                    "agent_id": assignment.agent_id,
                    "summary": assignment.output_json["summary"],
                    "permission_boundary": "agent_capability_attachment",
                    "allowed_tools": allowed_tools,
                    "requested_tool": tool_name,
                },
            )
            self.session.flush()
            return assignment
        assignment.status = "RUNNING"
        assignment.started_at = utc_now()
        agent_assignments_running.labels(
            agent_id=assignment.agent_id,
            role=assignment.role,
        ).inc()
        agent_parallel_branches_running.inc()
        self.event_store.append(
            task_id=run.id,
            event_type=EventType.AGENT_ASSIGNMENT_STARTED,
            payload_json={
                "run_id": run.id,
                "assignment_id": assignment.id,
                "agent_id": assignment.agent_id,
                "role": assignment.role,
            },
        )
        execution = runner.execute(
            task_id=run.id,
            tool_name=tool_name,
            input_json={
                **tool_input,
                "assignment_id": assignment.id,
                "agent_id": assignment.agent_id,
            },
            roles=["engineer"],
        )
        if not execution.allowed or execution.tool_call.status != "SUCCESS":
            assignment.status = "FAILED"
            assignment.completed_at = utc_now()
            self._record_assignment_metrics(assignment)
            assignment.output_json = {
                "summary": execution.tool_call.error_message or "Assignment failed",
                "tool_call_id": execution.tool_call.id,
                "tool_name": tool_name,
                "allowed_tools": allowed_tools,
                "permission_boundary": "agent_capability_attachment",
            }
            self.event_store.append(
                task_id=run.id,
                event_type=EventType.AGENT_ASSIGNMENT_FAILED,
                payload_json={
                    "run_id": run.id,
                    "assignment_id": assignment.id,
                    "agent_id": assignment.agent_id,
                    "summary": assignment.output_json["summary"],
                },
            )
            self.session.flush()
            return assignment

        assignment.status = "SUCCESS"
        assignment.completed_at = utc_now()
        self._record_assignment_metrics(assignment)
        assignment.output_json = {
            "summary": self._assignment_summary(assignment, execution.output),
            "tool_call_id": execution.tool_call.id,
            "tool_name": tool_name,
            "allowed_tools": allowed_tools,
            "permission_boundary": "agent_capability_attachment",
            "tool_output": execution.output,
        }
        self.event_store.append(
            task_id=run.id,
            event_type=EventType.AGENT_ASSIGNMENT_COMPLETED,
            payload_json={
                "run_id": run.id,
                "assignment_id": assignment.id,
                "agent_id": assignment.agent_id,
                "summary": assignment.output_json["summary"],
            },
        )
        self.event_store.append(
            task_id=run.id,
            event_type=EventType.AGENT_PARALLEL_BRANCH_COMPLETED,
            payload_json={
                "run_id": run.id,
                "assignment_id": assignment.id,
                "agent_id": assignment.agent_id,
            },
        )
        self.session.flush()
        return assignment

    def _latest_plan(self, run: Task) -> ExecutionPlan | None:
        return self.session.execute(
            select(ExecutionPlan)
            .where(ExecutionPlan.task_id == run.id)
            .order_by(ExecutionPlan.version.desc())
            .limit(1)
        ).scalar_one_or_none()

    def _select_agents(
        self,
        *,
        run: Task,
        plan: ExecutionPlan | None,
        entry_agent_id: str,
    ) -> list[str]:
        text = f"{run.title} {run.goal}".lower()
        steps = plan.plan_json.get("steps", []) if plan is not None else []
        tool_hints = {
            str(tool)
            for step in steps
            if isinstance(step, dict)
            for tool in step.get("tool_hints", [])
        }
        selected = [entry_agent_id]
        if any(marker in text for marker in ["研究", "分析", "research", "compare", "资料"]):
            selected.append("researcher")
        if tool_hints.intersection({"write_file", "run_shell", "run_tests", "git_command"}):
            selected.append("coder")
        risky_steps = (
            step.get("risk_level") in {"medium", "high", "critical"}
            for step in steps
            if isinstance(step, dict)
        )
        if any(risky_steps):
            selected.append("reviewer")
        if any(step.get("requires_sandbox") for step in steps if isinstance(step, dict)):
            selected.append("operator")
        if "reviewer" not in selected:
            selected.append("reviewer")
        return list(dict.fromkeys(selected))

    def _assignment_tool(self, assignment: AgentAssignment) -> tuple[str, dict]:
        if assignment.role in {"researcher", "operator"}:
            return "list_files", {"root": ".", "glob": "*"}
        return "read_file", {"path": "pyproject.toml"}

    def _agent_capability_names(self, *, agent: Agent, organization_id: str | None) -> list[str]:
        registry, _snapshot = CapabilityRegistry(
            self.session,
            organization_id,
        ).tool_registry_for_agent(agent.id)
        return sorted(registry.tools)

    def _assignment_summary(self, assignment: AgentAssignment, output: dict) -> str:
        if "files" in output:
            return f"{assignment.agent_id} listed {len(output['files'])} workspace entries."
        if "content" in output:
            return f"{assignment.agent_id} inspected pyproject.toml."
        return f"{assignment.agent_id} completed assignment."

    def _reduce(self, *, run: Task, assignments: list[AgentAssignment]) -> None:
        if not assignments or any(assignment.status != "SUCCESS" for assignment in assignments):
            return
        reducer = next(
            (assignment for assignment in assignments if assignment.agent_id == "reviewer"),
            assignments[-1] if assignments else None,
        )
        if reducer is None:
            return
        if reducer.output_json.get("reduced_summary"):
            return
        reduce_started_at = utc_now()
        summaries = [
            str(assignment.output_json.get("summary"))
            for assignment in assignments
            if assignment.output_json.get("summary")
        ]
        reducer.output_json = {
            **reducer.output_json,
            "reduced_summary": " | ".join(summaries),
            "reduced_assignment_ids": [assignment.id for assignment in assignments],
        }
        self.event_store.append(
            task_id=run.id,
            event_type=EventType.AGENT_REDUCE_COMPLETED,
            payload_json={
                "run_id": run.id,
                "reducer_assignment_id": reducer.id,
                "assignment_count": len(assignments),
                "summary": reducer.output_json["reduced_summary"],
            },
        )
        agent_reduce_duration_seconds.observe(_duration_seconds(reduce_started_at, utc_now()))

    def _enqueue_assignment(self, *, run: Task, assignment: AgentAssignment) -> None:
        from app.runtime_jobs.profile import is_local_runtime_profile

        if is_local_runtime_profile():
            from app.runtime_jobs.repository import RuntimeJobRepository

            RuntimeJobRepository(self.session).enqueue(
                kind="agent_assignment",
                payload={"assignment_id": assignment.id},
                dedupe_key=f"agent-assignment:{assignment.id}",
            )
            return

        from app.workers.agent_assignment_worker import run_agent_assignment

        try:
            run_agent_assignment.send(assignment.id)
        except Exception as exc:
            self.event_store.append(
                task_id=run.id,
                event_type=EventType.AGENT_ASSIGNMENT_QUEUED,
                payload_json={
                    "run_id": run.id,
                    "assignment_id": assignment.id,
                    "agent_id": assignment.agent_id,
                    "stage": "queue_deferred",
                    "summary": "Agent assignment queue unavailable; assignment remains queued",
                    "error": str(exc),
                },
            )

    def _record_assignment_metrics(self, assignment: AgentAssignment) -> None:
        agent_assignments_running.labels(
            agent_id=assignment.agent_id,
            role=assignment.role,
        ).dec()
        agent_parallel_branches_running.dec()
        agent_assignment_duration_seconds.labels(
            agent_id=assignment.agent_id,
            role=assignment.role,
            status=assignment.status,
        ).observe(_duration_seconds(assignment.started_at, assignment.completed_at))


def _duration_seconds(started_at, completed_at) -> float:
    if started_at is None or completed_at is None:
        return 0.0
    return max((completed_at - started_at).total_seconds(), 0.0)
