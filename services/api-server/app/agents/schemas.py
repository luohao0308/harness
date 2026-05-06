from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PlanStep(BaseModel):
    key: str = Field(min_length=1, pattern=r"^[a-z0-9_]+$")
    description: str = Field(min_length=1)
    execution_mode: Literal["sync", "async"]
    requires_sandbox: bool
    can_spawn_subagent: bool
    expected_events: list[str] = Field(default_factory=lambda: ["STEP_STARTED", "STEP_COMPLETED"])
    tool_hints: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    risk_level: Literal["low", "medium", "high", "critical"] = "low"
    artifact_expectations: list[str] = Field(default_factory=list)


class ExecutionPlan(BaseModel):
    summary: str = Field(min_length=1)
    steps: list[PlanStep] = Field(min_length=1)
    planner_source: Literal["llm", "llm_repaired", "deterministic"] = "deterministic"
    planner_attempts: int = Field(default=1, ge=1)

    model_config = ConfigDict(extra="forbid")


class StepResult(BaseModel):
    step_key: str
    status: Literal["STEP_COMPLETED", "STEP_FAILED"]
    summary: str
    tool_calls: list[dict] = Field(default_factory=list)
    next_action: Literal["continue", "stop", "spawn_subagent"] = "continue"
