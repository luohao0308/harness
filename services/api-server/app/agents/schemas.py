from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PlanStep(BaseModel):
    key: str = Field(min_length=1, pattern=r"^[a-z0-9_]+$")
    description: str = Field(min_length=1)
    execution_mode: Literal["sync", "async", "langgraph_node"]
    requires_sandbox: bool
    can_spawn_subagent: bool
    recommended_specialist_slug: str | None = None
    fanout_specialist_slugs: list[str] = Field(default_factory=list)
    fanout_aggregation: Literal["synthesizer_chain", "concat", "first_success"] = (
        "synthesizer_chain"
    )
    depends_on: list[str] = Field(default_factory=list)
    expected_events: list[str] = Field(default_factory=lambda: ["STEP_STARTED", "STEP_COMPLETED"])
    tool_hints: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    risk_level: Literal["low", "medium", "high", "critical"] = "low"
    artifact_expectations: list[str] = Field(default_factory=list)
    quality_notes: list[str] = Field(default_factory=list)
    timeout_seconds: int = Field(default=60)


class ExecutionPlan(BaseModel):
    summary: str = Field(min_length=1)
    steps: list[PlanStep] = Field(min_length=1)
    planner_source: Literal["llm", "llm_repaired", "deterministic"] = "deterministic"
    planner_attempts: int = Field(default=1, ge=1)
    planner_prompt_version: str = "1.1.0"
    quality_score: int = Field(default=100, ge=0, le=100)
    validation_warnings: list[str] = Field(default_factory=list)
    quality_gates: dict[str, bool] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class StepResult(BaseModel):
    step_key: str
    status: Literal["STEP_COMPLETED", "STEP_FAILED", "STEP_SKIPPED"]
    summary: str
    output: str = Field(default="")
    tool_calls: list[dict] = Field(default_factory=list)
    duration_ms: int = Field(default=0)
    next_action: Literal["continue", "stop", "spawn_subagent", "await_approval"] = "continue"
