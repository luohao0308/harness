"""DAG Scheduler for multi-step execution plan resolution.

Validates dependency graphs and resolves topological execution order,
grouping independent steps into ExecutionGroups for parallel execution.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from app.agents.schemas import ExecutionPlan, PlanStep

MAX_DAG_DEPTH = 20
MAX_DAG_FANOUT = 10
DEFAULT_MAX_PARALLEL = 3
MAX_STEP_OUTPUT_BYTES = 64 * 1024  # 64KB


@dataclass
class ExecutionGroup:
    """A set of steps that can execute concurrently (no mutual dependencies)."""

    steps: list[PlanStep]
    group_index: int


@dataclass
class StepResult:
    """Output from a completed step, passed as context to dependents."""

    step_key: str
    status: str  # "COMPLETED", "FAILED", "SKIPPED"
    output: str = ""  # truncated to 64KB
    tool_calls: list[dict] = field(default_factory=list)
    duration_ms: int = 0

    def __post_init__(self) -> None:
        if len(self.output) > MAX_STEP_OUTPUT_BYTES:
            self.output = self.output[:MAX_STEP_OUTPUT_BYTES]


class DAGScheduler:
    """Validates and resolves execution plan DAGs into ordered groups."""

    def __init__(self, max_parallel: int = DEFAULT_MAX_PARALLEL) -> None:
        self.max_parallel = max_parallel

    def validate(self, plan: ExecutionPlan) -> tuple[bool, str | None]:
        """Validate the DAG structure of a plan.

        Checks for:
        - Cycles (DFS-based detection)
        - Missing dependency references
        - Depth > MAX_DAG_DEPTH
        - Fan-out > MAX_DAG_FANOUT

        Returns (valid, error_msg). If valid is True, error_msg is None.
        """
        step_keys = {step.key for step in plan.steps}

        # Check for missing dependency references
        for step in plan.steps:
            for dep in step.depends_on:
                if dep not in step_keys:
                    return False, f"Step '{step.key}' depends on unknown step '{dep}'"

        # Check for self-references
        for step in plan.steps:
            if step.key in step.depends_on:
                return False, f"Step '{step.key}' has a self-dependency"

        # Build adjacency list (step -> list of steps that depend on it)
        adjacency: dict[str, list[str]] = {step.key: [] for step in plan.steps}
        for step in plan.steps:
            for dep in step.depends_on:
                adjacency[dep].append(step.key)

        # Cycle detection using DFS with coloring
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {key: WHITE for key in step_keys}

        def has_cycle(node: str) -> bool:
            color[node] = GRAY
            for neighbor in adjacency[node]:
                if color[neighbor] == GRAY:
                    return True
                if color[neighbor] == WHITE and has_cycle(neighbor):
                    return True
            color[node] = BLACK
            return False

        for key in step_keys:
            if color[key] == WHITE:
                if has_cycle(key):
                    return False, "Cycle detected in dependency graph"

        # Check depth (longest path in DAG)
        depth = self._compute_depth(plan)
        if depth > MAX_DAG_DEPTH:
            return False, f"DAG depth {depth} exceeds maximum of {MAX_DAG_DEPTH}"

        # Check fan-out (max number of direct dependents for any step)
        for step_key, dependents in adjacency.items():
            if len(dependents) > MAX_DAG_FANOUT:
                return (
                    False,
                    f"Step '{step_key}' has fan-out {len(dependents)} "
                    f"exceeding maximum of {MAX_DAG_FANOUT}",
                )

        return True, None

    def resolve(self, plan: ExecutionPlan) -> list[ExecutionGroup]:
        """Topologically sort steps via Kahn's algorithm and group into ExecutionGroups.

        Groups independent steps together (max group size = max_parallel).
        Special case: if all steps have empty depends_on, execute linearly
        (one step per group) for backward compatibility.
        """
        # Special case: all empty depends_on → linear execution
        if all(len(step.depends_on) == 0 for step in plan.steps):
            return [
                ExecutionGroup(steps=[step], group_index=i) for i, step in enumerate(plan.steps)
            ]

        # Build in-degree map and adjacency list
        step_map = {step.key: step for step in plan.steps}
        in_degree: dict[str, int] = {step.key: 0 for step in plan.steps}
        dependents: dict[str, list[str]] = {step.key: [] for step in plan.steps}

        for step in plan.steps:
            in_degree[step.key] = len(step.depends_on)
            for dep in step.depends_on:
                dependents[dep].append(step.key)

        # Kahn's algorithm with level-based grouping
        groups: list[ExecutionGroup] = []
        queue: deque[str] = deque(key for key, degree in in_degree.items() if degree == 0)

        group_index = 0
        while queue:
            # All items currently in queue are at the same "level" (can run in parallel)
            level_steps: list[str] = list(queue)
            queue.clear()

            # Split level into chunks of max_parallel
            for i in range(0, len(level_steps), self.max_parallel):
                chunk = level_steps[i : i + self.max_parallel]
                groups.append(
                    ExecutionGroup(
                        steps=[step_map[key] for key in chunk],
                        group_index=group_index,
                    )
                )
                group_index += 1

            # Reduce in-degree for dependents of completed level
            for key in level_steps:
                for dep_key in dependents[key]:
                    in_degree[dep_key] -= 1
                    if in_degree[dep_key] == 0:
                        queue.append(dep_key)

        return groups

    def get_downstream_dependents(self, plan: ExecutionPlan, step_key: str) -> set[str]:
        """Get all steps that transitively depend on the given step."""
        dependents: dict[str, list[str]] = {step.key: [] for step in plan.steps}
        for step in plan.steps:
            for dep in step.depends_on:
                dependents[dep].append(step.key)

        # BFS to find all transitive dependents
        visited: set[str] = set()
        queue: deque[str] = deque([step_key])
        while queue:
            current = queue.popleft()
            for dep_key in dependents.get(current, []):
                if dep_key not in visited:
                    visited.add(dep_key)
                    queue.append(dep_key)

        return visited

    def _compute_depth(self, plan: ExecutionPlan) -> int:
        """Compute the longest path (depth) in the DAG."""
        step_keys = {step.key for step in plan.steps}
        if not step_keys:
            return 0

        # Build dependency map: step -> its dependencies
        deps_map: dict[str, list[str]] = {step.key: list(step.depends_on) for step in plan.steps}

        # Compute depth via memoized DFS
        depth_cache: dict[str, int] = {}

        def get_depth(key: str) -> int:
            if key in depth_cache:
                return depth_cache[key]
            if not deps_map[key]:
                depth_cache[key] = 1
                return 1
            max_dep_depth = max(get_depth(dep) for dep in deps_map[key])
            depth_cache[key] = max_dep_depth + 1
            return depth_cache[key]

        return max(get_depth(key) for key in step_keys)
