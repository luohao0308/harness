from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from app.agents.schemas import ExecutionPlan, PlanStep
from app.db.models import Task
from app.tools.registry import ToolRegistry


class DeterministicPlanner:
    def __init__(self, tool_registry: ToolRegistry | None = None) -> None:
        self.tool_registry = tool_registry or ToolRegistry.default()

    def create_plan(self, task: Task, model_content: str | None = None) -> ExecutionPlan:
        if model_content:
            plan = self.parse_model_plan(model_content, planner_source="llm", planner_attempts=1)
            if plan is not None:
                return plan
        return self._deterministic_plan(task)

    def parse_model_plan(
        self,
        model_content: str,
        *,
        planner_source: str,
        planner_attempts: int,
    ) -> ExecutionPlan | None:
        return self._plan_from_model_content(
            model_content,
            planner_source=planner_source,
            planner_attempts=planner_attempts,
        )

    def _deterministic_plan(self, task: Task) -> ExecutionPlan:
        goal_text = f"{task.title} {task.goal}".lower()
        needs_subagent = any(
            marker in goal_text
            for marker in [
                "subagent",
                "sub-agent",
                "子 agent",
                "子agent",
                "并发",
                "异步",
                "长时间",
                "long running",
            ]
        )
        steps = [
            PlanStep(
                key="inspect_project",
                description="Inspect project structure",
                execution_mode="sync",
                requires_sandbox=False,
                can_spawn_subagent=False,
            )
        ]
        if needs_subagent and task.max_subagents > 0:
            steps.append(
                PlanStep(
                    key="subagent_research",
                    description="Spawn a subagent for concurrent research",
                    execution_mode="async",
                    requires_sandbox=False,
                    can_spawn_subagent=True,
                )
            )
        steps.append(
            PlanStep(
                key="produce_report",
                description="Produce final report",
                execution_mode="sync",
                requires_sandbox=False,
                can_spawn_subagent=False,
            )
        )
        plan = ExecutionPlan(
            summary=f"{task.goal}",
            steps=steps,
            planner_source="deterministic",
            planner_attempts=1,
        )
        return ExecutionPlan.model_validate(plan.model_dump())

    def _plan_from_model_content(
        self,
        model_content: str,
        *,
        planner_source: str,
        planner_attempts: int,
    ) -> ExecutionPlan | None:
        parsed = self._parse_model_json(model_content)
        if parsed is None:
            return None
        candidate = parsed.get("plan") if isinstance(parsed.get("plan"), dict) else parsed
        if not isinstance(candidate, dict):
            return None
        normalized = self._normalize_plan(
            candidate,
            planner_source=planner_source,
            planner_attempts=planner_attempts,
        )
        try:
            return ExecutionPlan.model_validate(normalized)
        except ValidationError:
            return None

    def _parse_model_json(self, model_content: str) -> dict[str, Any] | None:
        text = model_content.strip()
        if not text or text == "{}":
            return None
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fenced is not None:
            text = fenced.group(1)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start < 0 or end <= start:
                return None
            try:
                parsed = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
        return parsed if isinstance(parsed, dict) else None

    def _normalize_plan(
        self,
        candidate: dict[str, Any],
        *,
        planner_source: str,
        planner_attempts: int,
    ) -> dict[str, Any]:
        steps = candidate.get("steps")
        if not isinstance(steps, list):
            steps = []
        normalized_steps = []
        for index, raw_step in enumerate(steps, start=1):
            if not isinstance(raw_step, dict):
                continue
            mode = str(raw_step.get("execution_mode") or raw_step.get("mode") or "sync").lower()
            execution_mode = "async" if mode == "async" else "sync"
            key = str(raw_step.get("key") or raw_step.get("step_key") or f"step_{index}")
            key = self._normalize_step_key(key, index)
            can_spawn_subagent = bool(raw_step.get("can_spawn_subagent"))
            if execution_mode == "async":
                can_spawn_subagent = True
            normalized_steps.append(
                {
                    "key": key,
                    "description": str(raw_step.get("description") or key),
                    "execution_mode": execution_mode,
                    "requires_sandbox": bool(raw_step.get("requires_sandbox", False)),
                    "can_spawn_subagent": can_spawn_subagent,
                    "expected_events": raw_step.get(
                        "expected_events",
                        ["STEP_STARTED", "STEP_COMPLETED"],
                    ),
                }
            )
        return {
            "summary": str(candidate.get("summary") or "LLM generated execution plan"),
            "steps": normalized_steps,
            "planner_source": planner_source,
            "planner_attempts": planner_attempts,
        }

    def _normalize_step_key(self, value: str, index: int) -> str:
        key = re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")
        if not key:
            key = f"step_{index}"
        if not re.match(r"^[a-z0-9_]+$", key):
            key = f"step_{index}"
        return key
