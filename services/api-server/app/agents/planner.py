from app.agents.schemas import ExecutionPlan, PlanStep
from app.db.models import Task
from app.tools.registry import ToolRegistry


class DeterministicPlanner:
    def __init__(self, tool_registry: ToolRegistry | None = None) -> None:
        self.tool_registry = tool_registry or ToolRegistry.default()

    def create_plan(self, task: Task) -> ExecutionPlan:
        plan = ExecutionPlan(
            summary=f"{task.goal}",
            steps=[
                PlanStep(
                    key="inspect_project",
                    description="Inspect project structure",
                    execution_mode="sync",
                    requires_sandbox=False,
                    can_spawn_subagent=False,
                ),
                PlanStep(
                    key="produce_report",
                    description="Produce final report",
                    execution_mode="sync",
                    requires_sandbox=False,
                    can_spawn_subagent=False,
                ),
            ],
        )
        return ExecutionPlan.model_validate(plan.model_dump())
