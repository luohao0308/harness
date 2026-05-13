# Design Document: Multi-Step Harness Execution

## Overview

This design covers four interconnected feature areas that advance the AI Harness Platform from single-step execution to full multi-step DAG execution with eval regression, broader e2e coverage, and improved workspace context management.

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Agent Console (React)                         │
├──────────┬──────────┬──────────┬──────────┬──────────┬─────────────┤
│Workspace │ Eval UI  │Observ.   │ Tools    │Sandboxes │Agent Studio │
│(Context  │(Dataset, │(Health,  │(Registry,│(WarmPool,│(Config,     │
│ Mgmt,    │ Cases,   │ Metrics, │ MCP,     │ Instances│ Model,      │
│ Pinning, │ Runs,    │ Links)   │ Policy)  │ Isolation│ Prompt)     │
│ Branch)  │ Regress) │          │          │          │             │
├──────────┴──────────┴──────────┴──────────┴──────────┴─────────────┤
│                     Playwright E2E Test Layer                        │
└─────────────────────────────────────────────────────────────────────┘
                              │ HTTP/SSE
┌─────────────────────────────────────────────────────────────────────┐
│                        FastAPI Backend                                │
├──────────────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────────┐  ┌───────────┐  ┌───────────────┐  │
│  │ Planner  │→ │DAG Scheduler │→ │ Executor  │→ │ Event Store   │  │
│  │(+depends │  │(validate,    │  │(per-step  │  │(audit trail)  │  │
│  │  _on)    │  │ topo sort,   │  │ ReAct,    │  │               │  │
│  │          │  │ group,       │  │ model-    │  │               │  │
│  │          │  │ max_par=3)   │  │ driven)   │  │               │  │
│  └──────────┘  └──────────────┘  └─────┬─────┘  └───────────────┘  │
│                                         │                            │
│                    ┌────────────────────┼────────────────────┐       │
│                    │                    │                    │       │
│              ┌─────▼─────┐  ┌──────────▼──┐  ┌─────────────▼──┐   │
│              │ToolRunner │  │ WarmPool/   │  │ SubagentManager│   │
│              │(policy,   │  │ Sandbox     │  │ (async, 300s   │   │
│              │ audit,    │  │ (512MB/1c,  │  │  timeout,      │   │
│              │ 60s tmout)│  │  30s wait)  │  │  30s heartbeat)│   │
│              └───────────┘  └─────────────┘  └────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Eval Service (Dataset, Case, Run, Grader, Baseline, Delta)   │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Multi-Step Execution Flow:**
   - User submits goal → Planner generates ExecutionPlan with `depends_on` edges
   - DAG Scheduler validates (no cycles, refs exist, depth ≤ 20, fan-out ≤ 10)
   - DAG Scheduler resolves topological order → groups independent steps into ExecutionGroups
   - Executor processes groups sequentially; within each group, up to `max_parallel=3` steps run concurrently
   - Per step: Model Gateway selects tools + generates params → acquire sandbox if needed → invoke tools via ToolRunner → record ReAct trace → emit events
   - Step outputs (≤ 64KB) flow to dependent steps as context via `step_context` accumulator
   - On step failure: mark STEP_FAILED, mark all downstream dependents STEP_SKIPPED
   - Run transitions to FAILED if any step STEP_FAILED; COMPLETED if all STEP_COMPLETED/STEP_SKIPPED
   - Empty `depends_on` on all steps → linear execution in plan order (backward compatible)

2. **Eval Regression Flow:**
   - User saves completed Run (COMPLETED or FAILED) as Eval Case → captures goal, plan, trace, expected output
   - User triggers Eval Run against Dataset → Trace Grader scores each case
   - If Baseline exists → compute Regression Delta (metric diffs, newly failing cases)
   - Regression flagged if task_success_rate drops > 10 absolute percentage points
   - No baseline → UI shows "No baseline set" instead of delta

3. **Workspace Context Management Flow:**
   - Active Path tokens tracked via `content.length / 4` approximation
   - Context usage bar: amber at 80%, red at 95%
   - On send: if exceeds Context Window, truncate whole messages from oldest (payload-only, store preserved)
   - Always preserve: system messages + pinned messages + most recent user/assistant pair
   - If pinned messages alone exceed Context Window → send anyway + show overflow warning
   - Truncation notification shows count of excluded messages
   - Branching creates sibling fork; branch switcher shows "N of M" with arrows

## Data Models

### PlanStep Schema Extension

```python
class PlanStep(BaseModel):
    key: str = Field(min_length=1, pattern=r"^[a-z0-9_]+$")
    description: str = Field(min_length=1)
    execution_mode: Literal["sync", "async"]
    requires_sandbox: bool
    can_spawn_subagent: bool
    depends_on: list[str] = Field(default_factory=list)  # step keys this step depends on
    expected_events: list[str] = Field(default_factory=lambda: ["STEP_STARTED", "STEP_COMPLETED"])
    tool_hints: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    risk_level: Literal["low", "medium", "high", "critical"] = "low"
    artifact_expectations: list[str] = Field(default_factory=list)
    quality_notes: list[str] = Field(default_factory=list)
    timeout_seconds: int = Field(default=60)  # per-step timeout (sync default 60, async default 300)
```

### DAG Scheduler

```python
MAX_DAG_DEPTH = 20
MAX_DAG_FANOUT = 10
DEFAULT_MAX_PARALLEL = 3

@dataclass
class ExecutionGroup:
    """A set of steps that can execute concurrently (no mutual dependencies)."""
    steps: list[PlanStep]
    group_index: int

@dataclass
class StepResult:
    """Output from a completed step, passed as context to dependents."""
    step_key: str
    status: Literal["COMPLETED", "FAILED", "SKIPPED"]
    output: str  # truncated to 64KB
    tool_calls: list[dict]
    duration_ms: int

class DAGScheduler:
    def __init__(self, max_parallel: int = DEFAULT_MAX_PARALLEL):
        self.max_parallel = max_parallel

    def validate(self, plan: ExecutionPlan) -> tuple[bool, str | None]:
        """
        Check for:
        - Cycles (DFS-based detection)
        - Missing dependency references
        - Depth > MAX_DAG_DEPTH
        - Fan-out > MAX_DAG_FANOUT
        Returns (valid, error_msg).
        """
        ...

    def resolve(self, plan: ExecutionPlan) -> list[ExecutionGroup]:
        """
        Topologically sort steps via Kahn's algorithm.
        Group independent steps into ExecutionGroups (max group size = max_parallel).
        If all steps have empty depends_on, return one step per group (linear execution).
        """
        ...
```

### Eval Baseline and Regression Delta

```python
# New column on EvalDataset
class EvalDataset:
    baseline_run_id: str | None  # FK to EvalRun designated as baseline

# New response model
class RegressionDelta(BaseModel):
    baseline_run_id: str
    current_run_id: str
    task_success_rate_delta: float  # current - baseline (absolute pp)
    tool_selection_accuracy_delta: float
    avg_latency_ms_delta: int
    newly_failing_case_ids: list[str]
    newly_passing_case_ids: list[str]
    is_regression: bool  # True if task_success_rate_delta < -0.10
    total_cases: int
    passed_cases: int
    failed_cases: int
```

### Workspace Context Truncation

```typescript
// New utility: apps/agent-console/src/features/agents/lib/contextTruncation.ts

export interface TruncationResult {
  /** Messages to include in the API payload */
  messages: ConversationNode[];
  /** Number of messages excluded */
  excludedCount: number;
  /** Whether pinned messages alone exceed the budget */
  pinnedOverflow: boolean;
}

/**
 * Truncate messages for the API payload while preserving:
 * 1. System messages (always)
 * 2. Pinned messages (always)
 * 3. Most recent user/assistant pair (always)
 *
 * Estimation: content.length / 4 ≈ tokens
 * Removes whole messages from oldest end until within budget.
 */
export function truncateForContext(
  nodes: ConversationNode[],
  pinnedIds: string[],
  maxTokens: number,
): TruncationResult;
```

## API Changes

### New Endpoints

```
PATCH /api/evals/datasets/{dataset_id}/baseline
  Body: { "eval_run_id": "..." }
  Response: EvalDatasetResponse (with baseline_run_id set)
  Errors: 404 if dataset/run not found, 409 if run doesn't belong to dataset

GET /api/evals/runs/{eval_run_id}/regression
  Response: RegressionDelta | null (null when no baseline set)
  Errors: 404 if run not found
```

### Modified Endpoints

```
POST /api/agents/{agent_id}/runs
  No change to request/response schema
  Behavior change: execution now uses DAG scheduler instead of linear iteration

POST /api/agents/runs/{run_id}/execute
  No change to request/response schema
  Behavior change: executes full DAG with parallel groups

GET /api/evals/datasets/{dataset_id}
  Response now includes baseline_run_id field (nullable)
```

## Component Design

### Backend Components

#### 1. `app/agents/dag_scheduler.py` (NEW)

Responsibilities:
- Validate DAG (no cycles via DFS, all `depends_on` references exist, depth ≤ 20, fan-out ≤ 10)
- Topological sort via Kahn's algorithm
- Group independent steps into `ExecutionGroup`s (max group size = `max_parallel`)
- Special case: all empty `depends_on` → one step per group (linear)

#### 2. `app/agents/executor.py` (MODIFIED)

Changes:
- Replace linear `for step in plan.steps` with DAG Scheduler group iteration
- For each `ExecutionGroup`: execute steps concurrently (up to `max_parallel`)
- Per step: invoke Model Gateway with `purpose=tool_parameter_generation` to select tools and generate args
- Pass step outputs (≤ 64KB) as context to dependent steps via `step_context: dict[str, StepResult]`
- On step failure: emit STEP_FAILED, mark all downstream dependents as STEP_SKIPPED
- Timeout handling: 60s for tool calls, 300s for subagents
- Subagent delegation: only when `execution_mode=async` AND `can_spawn_subagent=true`
- Subagent inherits parent task's policy constraints
- Subagent heartbeat every 30s

#### 3. `app/agents/planner.py` (MODIFIED)

Changes:
- Add `depends_on` to PlanStep schema (default empty list)
- Update `PLANNER_SYSTEM_PROMPT` to instruct model to declare `depends_on` per step
- Add `depends_on` normalization in `_normalize_plan` (validate refs, strip invalid)
- Update `_deterministic_plan` to generate linear chain (step N depends on step N-1)
- Add DAG validation to `_with_quality_report` (cycle detection, depth/fan-out check)
- On validation failure: reject model plan, fall back to deterministic

#### 4. `app/api/evals.py` (MODIFIED)

Changes:
- Add `PATCH /api/evals/datasets/{dataset_id}/baseline` endpoint
- Add `GET /api/evals/runs/{eval_run_id}/regression` endpoint
- Regression delta computation: compare per-case results, compute metric diffs
- Regression flag: `is_regression = task_success_rate_delta < -0.10`
- Null delta when no baseline set

#### 5. `app/db/models.py` (MODIFIED)

Changes:
- Add `baseline_run_id` column to `EvalDataset` (nullable String FK)
- Alembic migration for the new column

### Frontend Components

#### 6. Eval Page Enhancement (`features/evals/`)

- Dataset list with case counts, last-run status, baseline indicator badge
- Create Dataset form (name, description)
- Case list within dataset (source run link, input summary, expected output)
- "Save as Eval Case" button on Run Detail page (visible for COMPLETED/FAILED runs)
- Eval Run trigger button on dataset view
- Eval Run results: metrics table, per-case pass/fail, regression delta with `data-regression`/`data-improvement` attributes
- Set Baseline button on completed Eval Runs

#### 7. Workspace Context Management

**Context Usage Bar** (`features/agents/components/ContextUsageBar.tsx`):
- Progress bar showing `estimatedTokens / contextMaxTokens`
- Amber at 80%, red at 95%
- Wired to `useWorkspaceStore.contextMaxTokens` and Active Path content

**Context Truncation** (`features/agents/lib/contextTruncation.ts`):
- `truncateForContext()` — sliding window, preserves system + pinned + latest pair
- Integrated into `useChatStream.buildPayload()` — payload-only, store untouched
- Returns `excludedCount` for notification display

**Pin Toggle** (modify `ChatMessage.tsx`):
- Pin/unpin icon button on hover (📌)
- Wired to existing `useWorkspaceStore.togglePinned`
- Visual indicator on pinned messages

**Branch UI** (modify `ChatMessage.tsx` + new `BranchSwitcher.tsx`):
- "Branch from here" in message actions menu (assistant messages)
- Creates sibling fork via existing store `appendNode` with same `parent_id`
- Branch count badge ("2/3") on nodes with siblings
- Left/right arrows to switch via existing `switchToBranch`
- Persisted via existing 300ms debounced localStorage write-through

#### 8. E2E Test Files (NEW)

- `e2e/eval-page.smoke.spec.ts` — Eval datasets, cases, runs, regression display
- `e2e/observability.smoke.spec.ts` — Health, metrics, run links
- `e2e/tools-page.smoke.spec.ts` — Registry, MCP, policy
- `e2e/sandboxes-page.smoke.spec.ts` — WarmPool, instances, isolation
- `e2e/agent-studio.smoke.spec.ts` — Config surfaces, persistence, disabled states

All use mocked API responses via Playwright `page.route()`, following patterns from existing `run-detail.smoke.spec.ts`.

## Error Handling

| Scenario | Handling | Event Emitted |
|----------|----------|---------------|
| DAG cycle detected | Planner rejects, falls back to deterministic linear plan | PLAN_VALIDATION_FAILED |
| Missing dependency reference | Planner rejects, falls back to deterministic linear plan | PLAN_VALIDATION_FAILED |
| DAG depth > 20 or fan-out > 10 | Planner rejects, falls back to deterministic linear plan | PLAN_VALIDATION_FAILED |
| WarmPool exhausted (30s timeout) | Step STEP_FAILED, downstream STEP_SKIPPED | WARMPOOL_TIMEOUT |
| Tool call timeout (60s) | Step STEP_FAILED, downstream STEP_SKIPPED | TOOL_TIMEOUT |
| Subagent timeout (300s) | Step STEP_FAILED, downstream STEP_SKIPPED | SUBAGENT_TIMEOUT |
| Sandbox OOM (512MB) | Container terminated, step STEP_FAILED | SANDBOX_OOM |
| Tool denied by policy | Step STEP_FAILED with next_action=await_approval | TOOL_DENIED |
| Step output > 64KB | Truncate to 64KB, log warning | (none, truncation is silent) |
| Context window exceeded | Truncate oldest non-pinned messages in payload | (frontend notification) |
| Pinned messages exceed Context Window | Send all pinned anyway, show overflow warning | (frontend notification) |
| Eval Run with no cases | HTTP 409 (existing behavior) | (none) |
| Baseline not set for regression | Return null delta, UI shows "No baseline set" | (none) |
| All steps empty depends_on | Execute linearly in plan order | (none, backward compat) |

## Testing Strategy

### Unit Tests (Pytest)

- `test_dag_scheduler.py` — cycle detection, topological sort, grouping, missing refs, depth/fan-out limits, empty depends_on linear fallback
- `test_executor_multistep.py` — DAG execution, parallel groups (verify overlapping timestamps), step output passing (64KB limit), failure propagation (downstream SKIPPED), timeout handling, subagent delegation trigger conditions
- `test_planner_depends_on.py` — dependency normalization, validation, quality gates, deterministic linear chain
- `test_eval_regression.py` — baseline setting, delta computation, regression flagging (10pp threshold), null baseline case, newly failing/passing identification

### Unit Tests (Vitest)

- `contextTruncation.test.ts` — sliding window, pin preservation, system message preservation, latest pair preservation, pinned overflow, no truncation within budget
- `contextUsageBar.test.ts` — amber/red thresholds, progress calculation
- `branchSwitcher.test.ts` — branch count, switching, sibling detection

### E2E Tests (Playwright)

- 5 new spec files covering Eval, Observability, Tools, Sandboxes, Agent Studio
- All use mocked API responses for speed (< 30s total on CI)
- Follow existing patterns from `run-detail.smoke.spec.ts`

### Integration Tests

- Full multi-step execution with real tool calls (backend, requires running API)
- Eval Run with baseline comparison (backend, requires running API)
- Live Workspace context truncation (frontend + backend, manual verification)

## Performance Considerations

- DAG Scheduler: Kahn's algorithm O(V+E), negligible for plans ≤ 20 steps
- Parallel execution: Python `asyncio.gather` with semaphore (max_parallel=3) for concurrent steps; each step gets its own DB session to avoid SQLAlchemy session conflicts
- WarmPool acquisition: 30s timeout prevents indefinite blocking
- Step output passing: 64KB cap prevents memory bloat in step_context accumulator
- Context truncation: O(n) over Active Path nodes, runs on every send (< 1ms for typical conversations)
- E2E tests: mocked responses, no network latency, < 30s total

## Migration Plan

1. **PlanStep `depends_on`** — Additive field, defaults to empty list. Stored in `plan_json` (JSON column), no Alembic migration needed. Existing plans without `depends_on` execute linearly (backward compatible).
2. **EvalDataset `baseline_run_id`** — New nullable column. Requires Alembic migration. No data migration (all existing datasets start with null baseline).
3. **Frontend ConversationNode** — No schema change needed. Pinning already tracked via `pinnedNodeIds` array in store. Branching already supported via `children_ids` tree structure.
4. **Executor behavior** — The DAG Scheduler wraps the existing `_execute_step` method. Per-step logic (tool invocation, sandbox, events) is preserved; only the iteration order changes.
5. **All changes are additive** — No breaking changes to existing API contracts, database schemas, or frontend state shapes.
