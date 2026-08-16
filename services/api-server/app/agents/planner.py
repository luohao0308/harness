from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from app.agents.dag_scheduler import DAGScheduler
from app.agents.schemas import ExecutionPlan, PlanStep
from app.db.models import Task
from app.tools.registry import ToolRegistry

PLANNER_PROMPT_VERSION = "1.1.0"
ALLOWED_RISK_LEVELS = {"low", "medium", "high", "critical"}
ALLOWED_FANOUT_AGGREGATIONS = {"synthesizer_chain", "concat", "first_success"}
ALLOWED_EXECUTION_MODES = {"sync", "async", "langgraph_node"}
EXPERT_REVIEW_MARKERS = {
    "review",
    "audit",
    "expert",
    "risk",
    "compliance",
    "safety",
    "logic",
    "session",
    "conversation",
    "审查",
    "评审",
    "审核",
    "专家",
    "风险",
    "合规",
    "安全",
    "逻辑",
    "会话",
}
SPECIALIST_PLAN_REPAIR_WARNING = (
    "计划目标需要专家证据但模型未包含异步子 Agent 步骤，已自动补充专家审查步骤。"
)


class DeterministicPlanner:
    def __init__(self, tool_registry: ToolRegistry | None = None) -> None:
        self.tool_registry = tool_registry or ToolRegistry.default()

    def create_plan(self, task: Task, model_content: str | None = None) -> ExecutionPlan:
        if model_content:
            plan = self.parse_model_plan(
                model_content,
                planner_source="llm",
                planner_attempts=1,
                task=task,
            )
            if plan is not None:
                return plan
        return self._deterministic_plan(task)

    def parse_model_plan(
        self,
        model_content: str,
        *,
        planner_source: str,
        planner_attempts: int,
        task: Task | None = None,
    ) -> ExecutionPlan | None:
        plan = self._plan_from_model_content(
            model_content,
            planner_source=planner_source,
            planner_attempts=planner_attempts,
        )
        if plan is None:
            return None
        return self._finalize_plan(task, plan)

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
                depends_on=[],
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
                    recommended_specialist_slug="researcher",
                    depends_on=[steps[-1].key],
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
                depends_on=[steps[-1].key],
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
        return self._finalize_plan(task, plan)

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
            plan = ExecutionPlan.model_validate(normalized)
        except ValidationError:
            return None
        return plan

    def _finalize_plan(self, task: Task | None, plan: ExecutionPlan) -> ExecutionPlan:
        if task is not None:
            plan = self._with_required_specialist_steps(task, plan)
        return self._with_quality_report(plan)

    def _with_required_specialist_steps(self, task: Task, plan: ExecutionPlan) -> ExecutionPlan:
        if task.max_subagents <= 0:
            return plan
        if not self._task_requires_specialist_evidence(task):
            return plan
        if any(
            step.execution_mode == "async"
            and (
                step.can_spawn_subagent
                or step.recommended_specialist_slug
                or step.fanout_specialist_slugs
            )
            for step in plan.steps
        ):
            return plan

        existing_keys = {step.key for step in plan.steps}
        step_key = self._deduplicate_step_key(key="expert_review", seen_keys=set(existing_keys))
        fanout_slugs = (
            ["code-reviewer", "safety-checker"] if task.max_subagents >= 2 else []
        )
        specialist_step = PlanStep(
            key=step_key,
            description=(
                "Run an independent expert subagent review for the requested session logic, "
                "risks, and acceptance evidence."
            ),
            execution_mode="async",
            requires_sandbox=False,
            can_spawn_subagent=True,
            recommended_specialist_slug="code-reviewer",
            fanout_specialist_slugs=fanout_slugs,
            fanout_aggregation="synthesizer_chain",
            depends_on=[],
            expected_events=["STEP_STARTED", "SUBAGENT_SPAWNED", "STEP_COMPLETED"],
            tool_hints=[],
            acceptance_criteria=["专家子 Agent 写入结构化审查证据。"],
            risk_level="medium",
            artifact_expectations=["专家审查证据"],
            quality_notes=["由 Harness 规划约束自动补充，避免专家证据为空。"],
            timeout_seconds=300,
        )
        payload = plan.model_dump()
        payload["steps"] = [*payload["steps"], specialist_step.model_dump()]
        warnings = list(payload.get("validation_warnings") or [])
        if SPECIALIST_PLAN_REPAIR_WARNING not in warnings:
            warnings.append(SPECIALIST_PLAN_REPAIR_WARNING)
        payload["validation_warnings"] = warnings
        return ExecutionPlan.model_validate(payload)

    def _task_requires_specialist_evidence(self, task: Task) -> bool:
        task_text = f"{task.title or ''} {task.goal or ''}".casefold()
        return any(marker.casefold() in task_text for marker in EXPERT_REVIEW_MARKERS)

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
        seen_keys: set[str] = set()
        for index, raw_step in enumerate(steps, start=1):
            if not isinstance(raw_step, dict):
                continue
            mode = str(raw_step.get("execution_mode") or raw_step.get("mode") or "sync").lower()
            execution_mode = mode if mode in ALLOWED_EXECUTION_MODES else "sync"
            key = str(raw_step.get("key") or raw_step.get("step_key") or f"step_{index}")
            key = self._normalize_step_key(key, index)
            key = self._deduplicate_step_key(key=key, seen_keys=seen_keys)
            seen_keys.add(key)
            can_spawn_subagent = bool(raw_step.get("can_spawn_subagent"))
            if execution_mode == "async":
                can_spawn_subagent = True
            if execution_mode == "langgraph_node":
                can_spawn_subagent = False
            recommended_specialist_slug = raw_step.get("recommended_specialist_slug")
            if not isinstance(recommended_specialist_slug, str):
                recommended_specialist_slug = raw_step.get("specialist_slug")
            if not isinstance(recommended_specialist_slug, str):
                recommended_specialist_slug = None
            fanout_specialist_slugs = self._normalize_string_list(
                raw_step.get("fanout_specialist_slugs"),
                default=[],
            )
            if len(fanout_specialist_slugs) == 1 and recommended_specialist_slug is None:
                recommended_specialist_slug = fanout_specialist_slugs[0]
            if len(fanout_specialist_slugs) > 1:
                execution_mode = "async"
                can_spawn_subagent = True
            fanout_aggregation = str(
                raw_step.get("fanout_aggregation") or "synthesizer_chain"
            )
            if fanout_aggregation not in ALLOWED_FANOUT_AGGREGATIONS:
                fanout_aggregation = "synthesizer_chain"
            tool_hints = self._normalize_tool_hints(raw_step.get("tool_hints"))
            risk_level = self._normalize_risk_level(raw_step.get("risk_level"), tool_hints)
            quality_notes = self._step_quality_notes(
                raw_step=raw_step,
                execution_mode=execution_mode,
                can_spawn_subagent=can_spawn_subagent,
                tool_hints=tool_hints,
            )
            # Normalize depends_on: keep only valid references to known step keys
            raw_depends_on = raw_step.get("depends_on", [])
            if not isinstance(raw_depends_on, list):
                raw_depends_on = []
            depends_on = [
                str(dep)
                for dep in raw_depends_on
                if isinstance(dep, str) and dep in seen_keys and dep != key
            ]
            normalized_steps.append(
                {
                    "key": key,
                    "description": str(raw_step.get("description") or key),
                    "execution_mode": execution_mode,
                    "requires_sandbox": bool(raw_step.get("requires_sandbox", False)),
                    "can_spawn_subagent": can_spawn_subagent,
                    "recommended_specialist_slug": recommended_specialist_slug,
                    "fanout_specialist_slugs": fanout_specialist_slugs,
                    "fanout_aggregation": fanout_aggregation,
                    "depends_on": depends_on,
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
                    "quality_notes": quality_notes,
                    "timeout_seconds": int(raw_step.get("timeout_seconds", 60)),
                }
            )
        return {
            "summary": str(candidate.get("summary") or "LLM generated execution plan"),
            "steps": normalized_steps,
            "planner_source": planner_source,
            "planner_attempts": planner_attempts,
            "planner_prompt_version": PLANNER_PROMPT_VERSION,
        }

    def _with_quality_report(self, plan: ExecutionPlan) -> ExecutionPlan:
        warnings: list[str] = list(plan.validation_warnings)
        steps = plan.steps
        step_count = len(steps)
        async_steps = [step for step in steps if step.execution_mode == "async"]
        langgraph_steps = [step for step in steps if step.execution_mode == "langgraph_node"]
        tool_steps = [step for step in steps if step.tool_hints]
        high_risk_without_sandbox = [
            step.key
            for step in steps
            if step.risk_level in {"high", "critical"} and not step.requires_sandbox
        ]
        missing_acceptance = [step.key for step in steps if not step.acceptance_criteria]
        missing_artifacts = [
            step.key
            for step in steps
            if step.execution_mode == "async" and not step.artifact_expectations
        ]
        duplicate_keys = step_count != len({step.key for step in steps})

        # DAG validation
        dag_valid, dag_error = DAGScheduler().validate(plan)
        if not dag_valid:
            warnings.append(f"DAG validation failed: {dag_error}")

        if step_count < 3:
            warnings.append("计划步骤少于 3 个，复杂任务拆解粒度可能不足。")
        if step_count > 8:
            warnings.append("计划步骤超过 8 个，执行链路需要拆分为更小批次。")
        if not tool_steps:
            warnings.append("计划未声明工具意图，Executor 审计细节会减少。")
        if not async_steps:
            warnings.append("计划未包含异步步骤，长任务并发能力未被使用。")
        if langgraph_steps:
            warnings.append(
                "计划包含 LangGraph workflow 节点，执行将受 Harness capability gate 约束。"
            )
        if high_risk_without_sandbox:
            warnings.append("高风险步骤缺少沙箱约束：" + "、".join(high_risk_without_sandbox))
        if missing_acceptance:
            warnings.append("步骤缺少验收标准：" + "、".join(missing_acceptance))
        if missing_artifacts:
            warnings.append("异步步骤缺少预期产物：" + "、".join(missing_artifacts))
        if duplicate_keys:
            warnings.append("计划存在重复步骤键，已在规范化阶段处理。")
        gates = {
            "step_count_in_range": 3 <= step_count <= 8,
            "has_tool_intent": bool(tool_steps),
            "has_acceptance_criteria": not missing_acceptance,
            "async_steps_have_artifacts": not missing_artifacts,
            "high_risk_requires_sandbox": not high_risk_without_sandbox,
            "unique_step_keys": not duplicate_keys,
            "dag_valid": dag_valid,
        }
        score = 100
        score -= 12 * sum(1 for passed in gates.values() if not passed)
        score -= min(12, len(warnings) * 2)
        payload = plan.model_dump()
        payload.update(
            {
                "planner_prompt_version": PLANNER_PROMPT_VERSION,
                "quality_score": max(score, 0),
                "validation_warnings": warnings,
                "quality_gates": gates,
            }
        )
        return ExecutionPlan.model_validate(payload)

    def _deduplicate_step_key(self, *, key: str, seen_keys: set[str]) -> str:
        if key not in seen_keys:
            return key
        index = 2
        while f"{key}_{index}" in seen_keys:
            index += 1
        return f"{key}_{index}"

    def _step_quality_notes(
        self,
        *,
        raw_step: dict[str, Any],
        execution_mode: str,
        can_spawn_subagent: bool,
        tool_hints: list[str],
    ) -> list[str]:
        notes: list[str] = []
        if execution_mode == "async" and not can_spawn_subagent:
            notes.append("异步步骤已自动允许派生子 Agent。")
        if raw_step.get("tool_hints") and not tool_hints:
            notes.append("模型给出的工具意图未命中 Tool Registry。")
        if not raw_step.get("acceptance_criteria"):
            notes.append("已补充默认验收标准。")
        return notes

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
