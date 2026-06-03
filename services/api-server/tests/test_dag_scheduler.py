"""Unit tests for DAG Scheduler module."""

from app.agents.dag_scheduler import (
    MAX_DAG_DEPTH,
    MAX_DAG_FANOUT,
    MAX_STEP_OUTPUT_BYTES,
    DAGScheduler,
    StepResult,
)
from app.agents.schemas import ExecutionPlan, PlanStep


def _make_step(key: str, depends_on: list[str] | None = None, **kwargs) -> PlanStep:
    """Helper to create a PlanStep with minimal required fields."""
    return PlanStep(
        key=key,
        description=f"Step {key}",
        execution_mode=kwargs.get("execution_mode", "sync"),
        requires_sandbox=kwargs.get("requires_sandbox", False),
        can_spawn_subagent=kwargs.get("can_spawn_subagent", False),
        depends_on=depends_on or [],
        tool_hints=kwargs.get("tool_hints", ["read_file"]),
        acceptance_criteria=[f"Step {key} completes."],
        risk_level="low",
    )


def _make_plan(steps: list[PlanStep]) -> ExecutionPlan:
    """Helper to create an ExecutionPlan from steps."""
    return ExecutionPlan(
        summary="Test plan",
        steps=steps,
        planner_source="deterministic",
        planner_attempts=1,
    )


class TestDAGSchedulerValidate:
    """Tests for DAGScheduler.validate()."""

    def test_valid_linear_chain(self):
        steps = [
            _make_step("a"),
            _make_step("b", depends_on=["a"]),
            _make_step("c", depends_on=["b"]),
        ]
        plan = _make_plan(steps)
        scheduler = DAGScheduler()

        valid, error = scheduler.validate(plan)

        assert valid is True
        assert error is None

    def test_valid_diamond_pattern(self):
        """A→B, A→C, B→D, C→D (diamond)."""
        steps = [
            _make_step("a"),
            _make_step("b", depends_on=["a"]),
            _make_step("c", depends_on=["a"]),
            _make_step("d", depends_on=["b", "c"]),
        ]
        plan = _make_plan(steps)
        scheduler = DAGScheduler()

        valid, error = scheduler.validate(plan)

        assert valid is True
        assert error is None

    def test_langgraph_node_steps_are_valid_dag_nodes(self):
        """LangGraph workflow nodes participate in the DAG like sync/async steps."""
        steps = [
            _make_step("prepare"),
            _make_step(
                "workflow",
                depends_on=["prepare"],
                execution_mode="langgraph_node",
                tool_hints=["langgraph:main"],
            ),
            _make_step("summarize", depends_on=["workflow"]),
        ]
        plan = _make_plan(steps)
        scheduler = DAGScheduler()

        valid, error = scheduler.validate(plan)
        groups = scheduler.resolve(plan)

        assert valid is True
        assert error is None
        assert [group.steps[0].key for group in groups] == ["prepare", "workflow", "summarize"]
        assert groups[1].steps[0].execution_mode == "langgraph_node"

    def test_simple_cycle_detected(self):
        """A→B→A cycle."""
        steps = [
            _make_step("a", depends_on=["b"]),
            _make_step("b", depends_on=["a"]),
        ]
        plan = _make_plan(steps)
        scheduler = DAGScheduler()

        valid, error = scheduler.validate(plan)

        assert valid is False
        assert "Cycle" in error or "cycle" in error.lower()

    def test_complex_cycle_detected(self):
        """A→B→C→A cycle."""
        steps = [
            _make_step("a"),
            _make_step("b", depends_on=["a"]),
            _make_step("c", depends_on=["b"]),
            _make_step("d", depends_on=["c", "a"]),
        ]
        # Add a cycle: make a depend on d
        steps[0] = _make_step("a", depends_on=["d"])
        plan = _make_plan(steps)
        scheduler = DAGScheduler()

        valid, error = scheduler.validate(plan)

        assert valid is False
        assert error is not None

    def test_self_reference_detected(self):
        """Step depends on itself."""
        steps = [
            _make_step("a", depends_on=["a"]),
        ]
        plan = _make_plan(steps)
        scheduler = DAGScheduler()

        valid, error = scheduler.validate(plan)

        assert valid is False
        assert "self-dependency" in error.lower() or "self" in error.lower()

    def test_missing_dependency_reference(self):
        """Step references a non-existent step."""
        steps = [
            _make_step("a"),
            _make_step("b", depends_on=["nonexistent"]),
        ]
        plan = _make_plan(steps)
        scheduler = DAGScheduler()

        valid, error = scheduler.validate(plan)

        assert valid is False
        assert "unknown" in error.lower() or "nonexistent" in error.lower()

    def test_depth_exceeds_maximum(self):
        """Chain longer than MAX_DAG_DEPTH."""
        steps = [_make_step("step_0")]
        for i in range(1, MAX_DAG_DEPTH + 2):
            steps.append(_make_step(f"step_{i}", depends_on=[f"step_{i - 1}"]))
        plan = _make_plan(steps)
        scheduler = DAGScheduler()

        valid, error = scheduler.validate(plan)

        assert valid is False
        assert "depth" in error.lower()

    def test_fanout_exceeds_maximum(self):
        """Single step with more than MAX_DAG_FANOUT dependents."""
        steps = [_make_step("root")]
        for i in range(MAX_DAG_FANOUT + 1):
            steps.append(_make_step(f"child_{i}", depends_on=["root"]))
        plan = _make_plan(steps)
        scheduler = DAGScheduler()

        valid, error = scheduler.validate(plan)

        assert valid is False
        assert "fan-out" in error.lower() or "fanout" in error.lower()

    def test_empty_depends_on_is_valid(self):
        """All steps with empty depends_on is valid."""
        steps = [
            _make_step("a"),
            _make_step("b"),
            _make_step("c"),
        ]
        plan = _make_plan(steps)
        scheduler = DAGScheduler()

        valid, error = scheduler.validate(plan)

        assert valid is True
        assert error is None

    def test_single_step_plan(self):
        """Trivial single-step plan."""
        steps = [_make_step("only_step")]
        plan = _make_plan(steps)
        scheduler = DAGScheduler()

        valid, error = scheduler.validate(plan)

        assert valid is True
        assert error is None


class TestDAGSchedulerResolve:
    """Tests for DAGScheduler.resolve()."""

    def test_linear_chain_one_step_per_group(self):
        """Linear chain: each step in its own group."""
        steps = [
            _make_step("a"),
            _make_step("b", depends_on=["a"]),
            _make_step("c", depends_on=["b"]),
        ]
        plan = _make_plan(steps)
        scheduler = DAGScheduler()

        groups = scheduler.resolve(plan)

        assert len(groups) == 3
        assert [g.steps[0].key for g in groups] == ["a", "b", "c"]
        assert all(len(g.steps) == 1 for g in groups)

    def test_all_empty_depends_on_linear_execution(self):
        """All empty depends_on → one step per group (linear)."""
        steps = [
            _make_step("a"),
            _make_step("b"),
            _make_step("c"),
        ]
        plan = _make_plan(steps)
        scheduler = DAGScheduler()

        groups = scheduler.resolve(plan)

        assert len(groups) == 3
        assert [g.steps[0].key for g in groups] == ["a", "b", "c"]
        assert all(len(g.steps) == 1 for g in groups)

    def test_independent_steps_grouped_together(self):
        """Independent steps are grouped for parallel execution."""
        steps = [
            _make_step("root"),
            _make_step("b", depends_on=["root"]),
            _make_step("c", depends_on=["root"]),
            _make_step("d", depends_on=["root"]),
        ]
        plan = _make_plan(steps)
        scheduler = DAGScheduler(max_parallel=3)

        groups = scheduler.resolve(plan)

        # First group: root (only step with no deps)
        assert groups[0].steps[0].key == "root"
        # Second group: b, c, d (all depend only on root, can run in parallel)
        parallel_keys = {s.key for g in groups[1:] for s in g.steps}
        assert parallel_keys == {"b", "c", "d"}

    def test_group_size_respects_max_parallel(self):
        """Groups are split when exceeding max_parallel."""
        steps = [
            _make_step("root"),
            _make_step("b", depends_on=["root"]),
            _make_step("c", depends_on=["root"]),
            _make_step("d", depends_on=["root"]),
            _make_step("e", depends_on=["root"]),
        ]
        plan = _make_plan(steps)
        scheduler = DAGScheduler(max_parallel=2)

        groups = scheduler.resolve(plan)

        # root in first group
        assert groups[0].steps[0].key == "root"
        # Remaining 4 steps split into groups of 2
        remaining_groups = groups[1:]
        assert all(len(g.steps) <= 2 for g in remaining_groups)
        all_keys = {s.key for g in remaining_groups for s in g.steps}
        assert all_keys == {"b", "c", "d", "e"}

    def test_diamond_dependency_pattern(self):
        """A→B, A→C, B→D, C→D (diamond)."""
        steps = [
            _make_step("a"),
            _make_step("b", depends_on=["a"]),
            _make_step("c", depends_on=["a"]),
            _make_step("d", depends_on=["b", "c"]),
        ]
        plan = _make_plan(steps)
        scheduler = DAGScheduler(max_parallel=3)

        groups = scheduler.resolve(plan)

        # Group 0: a
        assert groups[0].steps[0].key == "a"
        # Group 1: b, c (parallel)
        parallel_keys = {s.key for s in groups[1].steps}
        assert parallel_keys == {"b", "c"}
        # Group 2: d (depends on both b and c)
        assert groups[2].steps[0].key == "d"

    def test_single_step_plan(self):
        """Single step plan produces one group."""
        steps = [_make_step("only")]
        plan = _make_plan(steps)
        scheduler = DAGScheduler()

        groups = scheduler.resolve(plan)

        assert len(groups) == 1
        assert groups[0].steps[0].key == "only"

    def test_group_indices_are_sequential(self):
        """Group indices are assigned sequentially."""
        steps = [
            _make_step("a"),
            _make_step("b", depends_on=["a"]),
            _make_step("c", depends_on=["a"]),
        ]
        plan = _make_plan(steps)
        scheduler = DAGScheduler()

        groups = scheduler.resolve(plan)

        assert [g.group_index for g in groups] == list(range(len(groups)))


class TestDAGSchedulerDownstreamDependents:
    """Tests for DAGScheduler.get_downstream_dependents()."""

    def test_no_dependents(self):
        steps = [_make_step("a"), _make_step("b")]
        plan = _make_plan(steps)
        scheduler = DAGScheduler()

        result = scheduler.get_downstream_dependents(plan, "a")

        assert result == set()

    def test_direct_dependents(self):
        steps = [
            _make_step("a"),
            _make_step("b", depends_on=["a"]),
            _make_step("c", depends_on=["a"]),
        ]
        plan = _make_plan(steps)
        scheduler = DAGScheduler()

        result = scheduler.get_downstream_dependents(plan, "a")

        assert result == {"b", "c"}

    def test_transitive_dependents(self):
        steps = [
            _make_step("a"),
            _make_step("b", depends_on=["a"]),
            _make_step("c", depends_on=["b"]),
            _make_step("d", depends_on=["c"]),
        ]
        plan = _make_plan(steps)
        scheduler = DAGScheduler()

        result = scheduler.get_downstream_dependents(plan, "a")

        assert result == {"b", "c", "d"}


class TestStepResult:
    """Tests for StepResult dataclass."""

    def test_output_truncated_to_64kb(self):
        large_output = "x" * (MAX_STEP_OUTPUT_BYTES + 1000)
        result = StepResult(
            step_key="test",
            status="COMPLETED",
            output=large_output,
        )

        assert len(result.output) == MAX_STEP_OUTPUT_BYTES

    def test_output_within_limit_not_truncated(self):
        small_output = "hello world"
        result = StepResult(
            step_key="test",
            status="COMPLETED",
            output=small_output,
        )

        assert result.output == small_output

    def test_default_values(self):
        result = StepResult(step_key="test", status="COMPLETED")

        assert result.output == ""
        assert result.tool_calls == []
        assert result.duration_ms == 0
