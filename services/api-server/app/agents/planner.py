from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from app.agents.schemas import ExecutionPlan, PlanStep
from app.db.models import Task
from app.tools.registry import ToolRegistry

PLANNER_PROMPT_VERSION = "1.1.0"
ALLOWED_RISK_LEVELS = {"low", "medium", "high", "critical"}


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
                tool_hints=["list_files", "read_file"],
                acceptance_criteria=["识别项目结构和关键入口文件。"],
                risk_level="low",
                artifact_expectations=["项目结构摘要"],
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
                    tool_hints=["read_file", "list_files"],
                    acceptance_criteria=["子 Agent 返回可供父任务汇总的调研结果。"],
                    risk_level="medium",
                    artifact_expectations=["子 Agent 调研摘要"],
                )
            )
        steps.append(
            PlanStep(
                key="produce_report",
                description="Produce final report",
                execution_mode="sync",
                requires_sandbox=False,
                can_spawn_subagent=False,
                tool_hints=["read_file"],
                acceptance_criteria=["输出任务结果摘要和后续动作。"],
                risk_level="low",
                artifact_expectations=["任务结果摘要"],
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
            tool_hints = self._normalize_tool_hints(raw_step.get("tool_hints"))
            risk_level = self._normalize_risk_level(raw_step.get("risk_level"), tool_hints)
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
                    "tool_hints": tool_hints,
                    "acceptance_criteria": self._normalize_string_list(
                        raw_step.get("acceptance_criteria"),
                        default=[f"步骤 {key} 达到可审计的完成状态。"],
                    ),
                    "risk_level": risk_level,
                    "artifact_expectations": self._normalize_string_list(
                        raw_step.get("artifact_expectations"),
                        default=[],
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

    def _normalize_tool_hints(self, value: object) -> list[str]:
        names = self._normalize_string_list(value, default=[])
        registered = set(self.tool_registry.tools)
        return [name for name in names if name in registered]

    def _normalize_risk_level(self, value: object, tool_hints: list[str]) -> str:
        raw_risk = str(value or "").lower()
        if raw_risk in ALLOWED_RISK_LEVELS:
            return raw_risk
        tool_risks = [
            self.tool_registry.tools[name].risk_level
            for name in tool_hints
            if name in self.tool_registry.tools
        ]
        if any(risk in {"high", "critical"} for risk in tool_risks):
            return "high"
        if any(risk == "medium" for risk in tool_risks):
            return "medium"
        return "low"

    def _normalize_string_list(self, value: object, *, default: list[str]) -> list[str]:
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        if not isinstance(value, list):
            return default
        normalized = [str(item).strip() for item in value if str(item).strip()]
        return normalized or default
