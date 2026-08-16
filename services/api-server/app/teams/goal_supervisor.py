from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.db.models import TeamGoal, TeamMailboxMessage, TeamTask, utc_now

if TYPE_CHECKING:
    from app.teams.service import TeamSessionService


CURRENT_GOAL_STATUSES = frozenset({"active", "paused"})
AUTO_SUPERVISED_GOAL_STATUSES = frozenset({"active"})
TERMINAL_GOAL_STATUSES = {"completed", "failed", "blocked"}
GOAL_DRIFT_EVENT = "TEAM_GOAL_DRIFT_DETECTED"
GOAL_INTERVENTION_EVENT = "TEAM_GOAL_INTERVENTION_SENT"


@dataclass(slots=True)
class DriftDecision:
    drift_class: str
    severity: str
    reason: str
    intervention_level: int
    slot_id: str | None = None
    task_id: str | None = None
    message_id: str | None = None


def default_progress() -> dict:
    return {
        "phase": "running",
        "open_task_count": 0,
        "completed_task_count": 0,
        "drift_count": 0,
        "intervention_count": 0,
        "blocked_reason": None,
        "budget_remaining": 0,
        "last_event_sequence": None,
    }


def default_supervisor_state() -> dict:
    return {
        "processed_source_keys": [],
        "processed_results": {},
        "last_tick_id": None,
        "last_source_key": None,
        "drift_levels_by_slot": {},
        "budget_counters": {
            "drift_count": 0,
            "intervention_count": 0,
            "pause_count": 0,
            "reassign_count": 0,
        },
    }


def normalize_goal_json(goal: TeamGoal) -> None:
    goal.non_goals_json = list(goal.non_goals_json or [])
    goal.acceptance_criteria_json = list(goal.acceptance_criteria_json or [])
    goal.supervision_policy_json = dict(goal.supervision_policy_json or {})
    goal.correction_budget_json = dict(goal.correction_budget_json or {})
    goal.progress_json = {**default_progress(), **dict(goal.progress_json or {})}
    goal.supervisor_state_json = {
        **default_supervisor_state(),
        **dict(goal.supervisor_state_json or {}),
    }


class TeamGoalSupervisor:
    def __init__(self, service: TeamSessionService) -> None:
        self.service = service

    def create_goal(
        self,
        *,
        goal: TeamGoal,
    ) -> TeamGoal:
        normalize_goal_json(goal)
        goal.progress_json["budget_remaining"] = self._budget_remaining(goal)
        goal.progress_json = self.reconcile_progress(goal=goal)
        return goal

    def reconcile_progress(self, *, goal: TeamGoal) -> dict:
        normalize_goal_json(goal)
        tasks = self.service.list_tasks(goal.team_id)
        open_count = sum(1 for task in tasks if task.status in {"pending", "in_progress"})
        completed_count = sum(1 for task in tasks if task.status == "completed")
        state = dict(goal.supervisor_state_json or {})
        counters = dict(state.get("budget_counters") or {})
        progress = {
            **dict(goal.progress_json or {}),
            "open_task_count": open_count,
            "completed_task_count": completed_count,
            "drift_count": int(counters.get("drift_count") or 0),
            "intervention_count": int(counters.get("intervention_count") or 0),
            "budget_remaining": self._budget_remaining(goal),
        }
        return {**default_progress(), **progress}

    def evaluate(
        self,
        *,
        goal: TeamGoal,
        source_key: str,
        tick_id: str,
        slot_id: str | None = None,
        message: TeamMailboxMessage | None = None,
        task: TeamTask | None = None,
        force: bool = False,
    ) -> TeamGoal:
        normalize_goal_json(goal)
        state = dict(goal.supervisor_state_json or {})
        processed = dict(state.get("processed_results") or {})
        if not force and source_key in processed:
            state["last_tick_id"] = tick_id
            state["last_source_key"] = source_key
            goal.supervisor_state_json = state
            goal.progress_json = self.reconcile_progress(goal=goal)
            goal.updated_at = utc_now()
            return goal

        decision = self._detect_drift(goal=goal, slot_id=slot_id, message=message, task=task)
        if decision is None:
            processed[source_key] = {"result": "no_drift", "tick_id": tick_id}
            state["processed_results"] = processed
            state["processed_source_keys"] = list(processed.keys())[-200:]
            state["last_tick_id"] = tick_id
            state["last_source_key"] = source_key
            goal.supervisor_state_json = state
            goal.progress_json = self.reconcile_progress(goal=goal)
            goal.updated_at = utc_now()
            return goal

        self._record_drift(goal=goal, decision=decision, source_key=source_key, tick_id=tick_id)
        self._apply_intervention(goal=goal, decision=decision, tick_id=tick_id)
        state = dict(goal.supervisor_state_json or {})
        processed = dict(state.get("processed_results") or {})
        processed[source_key] = {
            "result": "drift",
            "tick_id": tick_id,
            "drift_class": decision.drift_class,
            "intervention_level": decision.intervention_level,
        }
        state["processed_results"] = processed
        state["processed_source_keys"] = list(processed.keys())[-200:]
        state["last_tick_id"] = tick_id
        state["last_source_key"] = source_key
        goal.supervisor_state_json = state
        goal.progress_json = self.reconcile_progress(goal=goal)
        goal.updated_at = utc_now()
        return goal

    def _detect_drift(
        self,
        *,
        goal: TeamGoal,
        slot_id: str | None,
        message: TeamMailboxMessage | None,
        task: TeamTask | None,
    ) -> DriftDecision | None:
        if task is not None and task.status == "completed":
            owner_slot = task.owner_slot_id
            if owner_slot:
                session_agent = self.service.get_agent(goal.team_id, owner_slot)
                latest_messages = self.service.session_messages(session_agent)
                has_evidence = any(
                    self._contains_evidence_marker(candidate.content)
                    for candidate in latest_messages[-4:]
                    if candidate.role == "assistant"
                )
                requires_evidence = any(
                    self._contains_evidence_marker(str(item))
                    for item in goal.acceptance_criteria_json
                )
                if requires_evidence and not has_evidence:
                    return DriftDecision(
                        drift_class="quality_evidence",
                        severity="medium",
                        reason=(
                            "Task completed without verification evidence required "
                            "by acceptance criteria."
                        ),
                        intervention_level=max(2, self._next_level(goal, owner_slot)),
                        slot_id=owner_slot,
                        task_id=task.id,
                    )

        if message is not None:
            content = message.content.strip()
            lowered = content.lower()
            scope_markers = (
                "npm install",
                "pip install",
                "commit",
                "deploy",
                "reset --hard",
                "rm -rf",
                "重构整个",
                "新库",
            )
            if any(token in lowered for token in scope_markers):
                return DriftDecision(
                    drift_class="scope",
                    severity="high",
                    reason=(
                        "Message proposed dependency, scope, or destructive action "
                        "outside goal policy."
                    ),
                    intervention_level=self._next_level(goal, message.from_agent_slot_id),
                    slot_id=message.from_agent_slot_id,
                    message_id=message.id,
                )
            if content in {"我先等待下一步", "先等待", "waiting", "stand by", "standby"}:
                owner_slot = message.from_agent_slot_id
                if owner_slot and self._has_open_assigned_tasks(goal.team_id, owner_slot):
                    return DriftDecision(
                        drift_class="collaboration",
                        severity="medium",
                        reason=(
                            "Assigned teammate returned standby/no-op while work "
                            "remained unblocked."
                        ),
                        intervention_level=self._next_level(goal, owner_slot),
                        slot_id=owner_slot,
                        message_id=message.id,
                    )
            completion_markers = ("完成了", "done", "finished")
            if any(token in lowered for token in completion_markers) and message.from_agent_slot_id:
                if self._has_open_assigned_tasks(goal.team_id, message.from_agent_slot_id):
                    has_completed_update = self._has_recent_completed_task(
                        goal.team_id,
                        message.from_agent_slot_id,
                    )
                    if not has_completed_update:
                        return DriftDecision(
                            drift_class="task",
                            severity="medium",
                            reason=(
                                "Teammate claimed completion without matching "
                                "team task completion update."
                            ),
                            intervention_level=self._next_level(goal, message.from_agent_slot_id),
                            slot_id=message.from_agent_slot_id,
                            message_id=message.id,
                        )
        return None

    def _record_drift(
        self,
        *,
        goal: TeamGoal,
        decision: DriftDecision,
        source_key: str,
        tick_id: str,
    ) -> None:
        state = dict(goal.supervisor_state_json or {})
        counters = dict(state.get("budget_counters") or {})
        counters["drift_count"] = int(counters.get("drift_count") or 0) + 1
        state["budget_counters"] = counters
        drift_levels = dict(state.get("drift_levels_by_slot") or {})
        if decision.slot_id:
            drift_levels[decision.slot_id] = max(
                int(drift_levels.get(decision.slot_id) or 0),
                decision.intervention_level,
            )
        state["drift_levels_by_slot"] = drift_levels
        goal.supervisor_state_json = state
        self.service.append_event(
            team_id=goal.team_id,
            event_type=GOAL_DRIFT_EVENT,
            payload={
                "team_goal_id": goal.id,
                "tick_id": tick_id,
                "source_key": source_key,
                "drift_class": decision.drift_class,
                "severity": decision.severity,
                "reason": decision.reason,
                "slot_id": decision.slot_id,
                "team_task_id": decision.task_id,
                "source_message_id": decision.message_id,
                "budget_remaining": self._budget_remaining(goal) - 1,
            },
            actor_type="system",
            actor_id="team_goal_supervisor",
        )

    def _apply_intervention(self, *, goal: TeamGoal, decision: DriftDecision, tick_id: str) -> None:
        state = dict(goal.supervisor_state_json or {})
        counters = dict(state.get("budget_counters") or {})
        counters["intervention_count"] = int(counters.get("intervention_count") or 0) + 1
        state["budget_counters"] = counters
        goal.supervisor_state_json = state

        if self._budget_remaining(goal) <= 0:
            goal.status = "blocked"
            goal.progress_json = {
                **dict(goal.progress_json or {}),
                "blocked_reason": "Correction budget exhausted.",
            }
            self.service.append_event(
                team_id=goal.team_id,
                event_type="TEAM_GOAL_BLOCKED",
                payload={
                    "team_goal_id": goal.id,
                    "tick_id": tick_id,
                    "reason": "Correction budget exhausted.",
                    "slot_id": decision.slot_id,
                },
                actor_type="system",
                actor_id="team_goal_supervisor",
            )
            return

        if decision.intervention_level == 1 and decision.slot_id:
            self.service.write_message(
                team_id=goal.team_id,
                target=decision.slot_id,
                content=(
                    f"Goal correction: {decision.reason} "
                    f"Objective: {goal.objective}. "
                    f"Non-goals: {', '.join(str(item) for item in goal.non_goals_json) or 'none'}."
                ),
                from_agent_slot_id="leader",
                message_type="message",
                wake_recipient=False,
            )
        elif decision.intervention_level == 2 and decision.task_id:
            task = self.service.get_task(goal.team_id, decision.task_id)
            task.metadata_json = {
                **dict(task.metadata_json or {}),
                "needs_correction": True,
                "goal_intervention_level": 2,
                "goal_intervention_reason": decision.reason,
            }
            if "evidence" not in task.description.lower():
                task.description = (
                    f"{task.description}\n\nEvidence required before completion.".strip()
                )
            task.updated_at = utc_now()
            self.service.append_event(
                team_id=goal.team_id,
                event_type="TEAM_TASK_UPDATED",
                payload={"task": self.service.task_summary(task)},
                actor_type="system",
                actor_id="team_goal_supervisor",
            )
        elif decision.intervention_level >= 3 and decision.task_id:
            task = self.service.get_task(goal.team_id, decision.task_id)
            teammates = [
                agent
                for agent in self.service._agents(goal.team_id)
                if agent.role != "leader" and agent.slot_id != task.owner_slot_id
            ]
            if teammates:
                task.owner_slot_id = teammates[0].slot_id
                task.metadata_json = {
                    **dict(task.metadata_json or {}),
                    "needs_correction": True,
                    "goal_intervention_level": 3,
                    "goal_intervention_reason": decision.reason,
                }
                task.updated_at = utc_now()
                self.service.append_event(
                    team_id=goal.team_id,
                    event_type="TEAM_TASK_UPDATED",
                    payload={"task": self.service.task_summary(task)},
                    actor_type="system",
                    actor_id="team_goal_supervisor",
                )
                self.service.append_event(
                    team_id=goal.team_id,
                    event_type="TEAM_GOAL_TASK_REASSIGNED",
                    payload={
                        "team_goal_id": goal.id,
                        "tick_id": tick_id,
                        "team_task_id": task.id,
                        "slot_id": task.owner_slot_id,
                        "drift_class": decision.drift_class,
                        "budget_remaining": self._budget_remaining(goal),
                    },
                    actor_type="system",
                    actor_id="team_goal_supervisor",
                )
            else:
                goal.status = "blocked"
                goal.progress_json = {
                    **dict(goal.progress_json or {}),
                    "blocked_reason": "No safe reassignment target available.",
                }
                self.service.append_event(
                    team_id=goal.team_id,
                    event_type="TEAM_GOAL_BLOCKED",
                    payload={
                        "team_goal_id": goal.id,
                        "tick_id": tick_id,
                        "reason": "No safe reassignment target available.",
                        "team_task_id": decision.task_id,
                    },
                    actor_type="system",
                    actor_id="team_goal_supervisor",
                )
                return

        self.service.append_event(
            team_id=goal.team_id,
            event_type=GOAL_INTERVENTION_EVENT,
            payload={
                "team_goal_id": goal.id,
                "tick_id": tick_id,
                "drift_class": decision.drift_class,
                "severity": decision.severity,
                "intervention_level": decision.intervention_level,
                "slot_id": decision.slot_id,
                "team_task_id": decision.task_id,
                "source_message_id": decision.message_id,
                "budget_remaining": self._budget_remaining(goal),
            },
            actor_type="system",
            actor_id="team_goal_supervisor",
        )

    def _next_level(self, goal: TeamGoal, slot_id: str | None) -> int:
        if not slot_id:
            return 1
        state = dict(goal.supervisor_state_json or {})
        levels = dict(state.get("drift_levels_by_slot") or {})
        return min(int(levels.get(slot_id) or 0) + 1, 3)

    def _budget_remaining(self, goal: TeamGoal) -> int:
        budget = dict(goal.correction_budget_json or {})
        raw_max_interventions = budget.get("max_interventions", 3)
        if raw_max_interventions in {None, ""}:
            raw_max_interventions = 3
        max_interventions = int(raw_max_interventions)
        state = dict(goal.supervisor_state_json or {})
        counters = dict(state.get("budget_counters") or {})
        used = int(counters.get("intervention_count") or 0)
        return max(max_interventions - used, 0)

    @staticmethod
    def _contains_evidence_marker(value: str) -> bool:
        lowered = value.lower()
        return any(
            token in lowered
            for token in (
                "test",
                "pytest",
                "vitest",
                "evidence",
                "proof",
                "verified",
                "验证",
                "测试",
                ".tsx",
                ".py",
            )
        )

    def _has_open_assigned_tasks(self, team_id: str, slot_id: str) -> bool:
        return any(
            task.owner_slot_id == slot_id and task.status in {"pending", "in_progress"}
            for task in self.service.list_tasks(team_id)
        )

    def _has_recent_completed_task(self, team_id: str, slot_id: str) -> bool:
        return any(
            task.owner_slot_id == slot_id and task.status == "completed"
            for task in self.service.list_tasks(team_id)
        )
