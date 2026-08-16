# Implementation Tasks

> Status: archived-complete. The implementation and regression coverage described below exist in the current repository; this checklist is historical evidence and is not an active task board. Current work is tracked in `docs/TASKS.md`.

## Phase 1: Multi-Step DAG Execution (Backend)

- [x] 1.1 Add `depends_on` and `timeout_seconds` fields to PlanStep schema
  - File: `services/api-server/app/agents/planner.py` (PlanStep model)
  - Add `depends_on: list[str] = Field(default_factory=list)`
  - Add `timeout_seconds: int = Field(default=60)`
  - Ensure backward compatibility (empty list = no dependencies = linear execution)
  - Requirements: Req 2.1

- [x] 1.2 Create DAG Scheduler module
  - File: `services/api-server/app/agents/dag_scheduler.py` (NEW)
  - Implement `DAGScheduler.validate()` — detect cycles (DFS), check all `depends_on` refs exist, enforce depth ≤ 20 and fan-out ≤ 10
  - Implement `DAGScheduler.resolve()` — topological sort via Kahn's algorithm, group independent steps into `ExecutionGroup`s (max group size = `max_parallel`, default 3)
  - Special case: all empty `depends_on` → one step per group (linear execution)
  - Define `StepResult` dataclass for inter-step context passing (output truncated to 64KB)
  - Requirements: Req 1.1, 1.2, 1.9, 2.6

- [x] 1.3 Update Planner to generate and validate dependencies
  - File: `services/api-server/app/agents/planner.py`
  - Update `PLANNER_SYSTEM_PROMPT` to instruct model to declare `depends_on` per step
  - Add `depends_on` normalization in `_normalize_plan` (validate refs, strip invalid)
  - Update `_deterministic_plan` to generate linear chain dependencies (step N depends on step N-1)
  - Add DAG validation to `_with_quality_report` (call `DAGScheduler.validate()`)
  - On validation failure: reject model plan, fall back to deterministic
  - Requirements: Req 2.2, 2.3, 2.4, 2.5

- [x] 1.4 Refactor Executor for DAG-driven execution
  - File: `services/api-server/app/agents/executor.py`
  - Replace linear `for step in plan.steps` with DAG Scheduler group iteration
  - For each `ExecutionGroup`: execute steps concurrently using `asyncio.gather` with semaphore (max_parallel=3)
  - Each concurrent step gets its own DB session to avoid SQLAlchemy conflicts
  - Pass completed step outputs as context via `step_context: dict[str, StepResult]` accumulator
  - On step failure: emit STEP_FAILED, mark all downstream dependents as STEP_SKIPPED
  - Run final state: FAILED if any STEP_FAILED; COMPLETED if all STEP_COMPLETED/STEP_SKIPPED
  - Requirements: Req 1.1, 1.2, 1.6, 1.7, 1.8, 1.9, 1.10

- [x] 1.5 Implement model-driven tool selection and parameter generation
  - File: `services/api-server/app/agents/executor.py`
  - In `_execute_step`: invoke Model Gateway with step description + `tool_hints` + accumulated `step_context` to select tools and generate parameters
  - Record MODEL_CALL event with `purpose=tool_parameter_generation`
  - Invoke selected tools through ToolRunner with full policy/audit
  - Pass tool output (truncated to 64KB) to `StepResult`
  - Requirements: Req 3.1, 3.2, 3.4

- [x] 1.6 Add timeout and failure handling
  - File: `services/api-server/app/agents/executor.py`
  - Tool call timeout: 60s default (configurable via Tool Registry `timeout_seconds`)
  - Subagent timeout: 300s default (configurable via task `max_runtime_seconds`)
  - Subagent heartbeat: emit event every 30s while subagent is executing
  - On timeout: emit TOOL_TIMEOUT / SUBAGENT_TIMEOUT event, mark step STEP_FAILED
  - Subagent delegation: only when `execution_mode=async` AND `can_spawn_subagent=true`
  - Subagent inherits parent task's policy constraints
  - Requirements: Req 1.4, 3.3, 3.5, 4.2, 4.4, 5.1, 5.3, 5.4, 5.5

- [x] 1.7 Write unit tests for DAG Scheduler
  - File: `services/api-server/tests/test_dag_scheduler.py` (NEW)
  - Test cycle detection (simple cycle, complex cycle, self-reference)
  - Test missing dependency reference detection
  - Test topological sort correctness (verify order respects dependencies)
  - Test grouping of independent steps (verify group size ≤ max_parallel)
  - Test single-step plan (trivial case)
  - Test linear chain (all sequential, one step per group)
  - Test diamond dependency pattern (A→B, A→C, B→D, C→D)
  - Test all-empty depends_on → linear execution
  - Test depth > 20 rejection
  - Test fan-out > 10 rejection
  - Requirements: Req 1, 2

- [x] 1.8 Write unit tests for multi-step Executor
  - File: `services/api-server/tests/test_executor_multistep.py` (NEW)
  - Test DAG execution with parallel groups (verify overlapping STEP_STARTED timestamps)
  - Test step output passing to dependent steps (verify context received)
  - Test 64KB output truncation
  - Test failure propagation (downstream steps get STEP_SKIPPED)
  - Test independent branch continues after sibling failure
  - Test tool timeout handling (60s)
  - Test subagent timeout handling (300s)
  - Test subagent heartbeat emission (30s interval)
  - Test subagent delegation trigger (async + can_spawn only)
  - Test Run final state (FAILED if any STEP_FAILED, COMPLETED otherwise)
  - Test MODEL_CALL event with purpose=tool_parameter_generation
  - Requirements: Req 1, 3, 4, 5

## Phase 2: Eval Regression Flow (Backend + Frontend)

- [x] 2.1 Add `baseline_run_id` column to EvalDataset
  - File: `services/api-server/app/db/models.py`
  - Add nullable `baseline_run_id` column (String, FK to eval_runs.id)
  - File: `services/api-server/alembic/versions/` (NEW migration)
  - Create Alembic migration for the new column
  - Requirements: Req 7.1

- [x] 2.2 Implement set-baseline endpoint
  - File: `services/api-server/app/api/evals.py`
  - Add `PATCH /api/evals/datasets/{dataset_id}/baseline` endpoint
  - Validate that the eval_run_id belongs to the dataset
  - Update dataset's `baseline_run_id`
  - Return 404 if dataset/run not found, 409 if run doesn't belong to dataset
  - Emit audit event
  - Requirements: Req 7.1

- [x] 2.3 Implement regression delta computation
  - File: `services/api-server/app/api/evals.py`
  - Add `GET /api/evals/runs/{eval_run_id}/regression` endpoint
  - Load baseline run results and current run results
  - Compute per-metric deltas (task_success_rate, tool_selection_accuracy, avg_latency_ms)
  - Identify newly failing and newly passing cases
  - Flag as regression if task_success_rate drops > 10 absolute percentage points
  - Return null when no baseline set
  - Requirements: Req 7.2, 7.3, 7.4, 7.6

- [x] 2.4 Enhance Eval Case creation from Run
  - File: `services/api-server/app/api/evals.py`
  - Extend `create_eval_case_from_run` to capture full execution trace (step results, tool call sequences, model call counts) in `expected_json`
  - Accept Runs with status COMPLETED or FAILED
  - Include plan summary and step count in captured data
  - Requirements: Req 6.1, 6.2, 6.4

- [x] 2.5 Write unit tests for eval regression
  - File: `services/api-server/tests/test_eval_regression.py` (NEW)
  - Test baseline setting (happy path, invalid run_id, run not in dataset)
  - Test regression delta computation (improvement, regression, no change)
  - Test newly failing/passing case identification
  - Test regression flagging threshold (10pp drop)
  - Test null delta when no baseline set
  - Requirements: Req 7

- [x] 2.6 Build Eval UI — Dataset list and creation
  - File: `apps/agent-console/src/features/evals/pages/EvalHarnessPage.tsx` (modify)
  - Display dataset list with case counts, last-run status, baseline indicator badge
  - Add "Create Dataset" form (name, description)
  - Wire to existing `GET /api/evals/datasets` and `POST /api/evals/datasets`
  - Requirements: Req 8.1, 8.2

- [x] 2.7 Build Eval UI — Case list and "Save from Run"
  - File: `apps/agent-console/src/features/evals/components/EvalCaseList.tsx` (NEW)
  - Display cases within selected dataset (source run link, input summary, expected output)
  - File: `apps/agent-console/src/features/runs/pages/RunDetailPage.tsx` (modify)
  - Add "Save as Eval Case" button (visible for COMPLETED/FAILED runs)
  - Wire to `POST /api/evals/datasets/{id}/cases/from-run/{task_id}`
  - Requirements: Req 6.3, 8.3

- [x] 2.8 Build Eval UI — Run trigger and regression display
  - File: `apps/agent-console/src/features/evals/components/EvalRunResults.tsx` (NEW)
  - Add "Run Eval" button on dataset view
  - Display run metrics (task_success_rate, tool_selection_accuracy, etc.)
  - Display per-case results (pass/fail, scores)
  - Display regression delta with `data-regression="true"` / `data-improvement="true"` attributes
  - Add "Set as Baseline" button on completed runs
  - Show "No baseline set" when delta is null
  - Requirements: Req 7.5, 7.6, 8.4, 8.5, 8.6

## Phase 3: Browser E2E Tests

- [x] 3.1 Create Eval page e2e tests
  - File: `apps/agent-console/e2e/eval-page.smoke.spec.ts` (NEW)
  - Mock API responses for datasets, cases, runs, regression delta
  - Test: Dataset list renders with case counts and baseline badge
  - Test: "Save Run as Eval Case" flow from Run Detail
  - Test: Trigger Eval Run and view regression metrics with color coding
  - All tests use mocked responses, complete within 30s
  - Requirements: Req 9.1, 9.2, 9.3, 9.4

- [x] 3.2 Create Observability page e2e tests
  - File: `apps/agent-console/e2e/observability.smoke.spec.ts` (NEW)
  - Mock API responses for health, metrics, summary
  - Test: Service health indicators render
  - Test: Queue depth, active runs, sandbox utilization, model call latency panels render
  - Test: Clicking Run link navigates to Run Detail
  - Requirements: Req 10.1, 10.2, 10.3

- [x] 3.3 Create Tools page e2e tests
  - File: `apps/agent-console/e2e/tools-page.smoke.spec.ts` (NEW)
  - Mock API responses for tool registry
  - Test: Tool Registry list renders with names, risk levels, policy status
  - Test: MCP adapter section renders registered MCP tools
  - Test: Policy toggle updates displayed state
  - Requirements: Req 11.1, 11.2, 11.3

- [x] 3.4 Create Sandboxes page e2e tests
  - File: `apps/agent-console/e2e/sandboxes-page.smoke.spec.ts` (NEW)
  - Mock API responses for sandbox/warmpool data
  - Test: WarmPool status renders (min_ready, max_ready, available count)
  - Test: Active sandbox instances render with lifecycle state
  - Test: Tenant Isolation section displays isolation policy
  - Requirements: Req 12.1, 12.2, 12.3

- [x] 3.5 Create Agent Studio page e2e tests
  - File: `apps/agent-console/e2e/agent-studio.smoke.spec.ts` (NEW)
  - Mock API responses for agent config, model settings
  - Test: Model, Tools/MCP, Prompt, RAG, Templates, Orchestration surfaces render
  - Test: Model provider selection persists through settings API
  - Test: Disabled surfaces (RAG, Templates) display API-pending state
  - Requirements: Req 13.1, 13.2, 13.3

## Phase 4: Workspace Context Management (Frontend)

- [x] 4.1 Implement context truncation logic
  - File: `apps/agent-console/src/features/agents/lib/contextTruncation.ts` (NEW)
  - Implement `truncateForContext(nodes, pinnedIds, maxTokens)` → `TruncationResult`
  - Token estimation: `content.length / 4`
  - Always preserve: system messages, pinned messages, most recent user/assistant pair
  - Remove whole messages from oldest end until within budget
  - Handle pinned overflow: if pinned alone exceed budget, include all + set `pinnedOverflow=true`
  - Return `excludedCount` for notification
  - Requirements: Req 14.1, 14.3, 14.5, 14.6

- [x] 4.2 Add context usage indicator component
  - File: `apps/agent-console/src/features/agents/components/ContextUsageBar.tsx` (NEW)
  - Display progress bar: `estimatedTokens / contextMaxTokens`
  - Amber state at 80% usage
  - Red/critical state at 95% usage
  - Wire to `useWorkspaceStore.contextMaxTokens` and Active Path content length
  - Requirements: Req 14.1, 14.2

- [x] 4.3 Integrate truncation into chat payload builder
  - File: `apps/agent-console/src/features/agents/hooks/useChatStream.ts` (modify)
  - In `buildPayload`: apply `truncateForContext` before serializing messages
  - Pass `pinnedNodeIds` and `contextMaxTokens` from store
  - Truncated messages excluded from API payload only (store data preserved)
  - Show notification with excluded count when truncation occurs
  - Show overflow warning when pinned messages exceed budget
  - Requirements: Req 14.3, 14.5, 14.6, 14.7

- [x] 4.4 Add pin toggle UI to messages
  - File: `apps/agent-console/src/features/agents/components/ChatMessageBubble.tsx` (modify)
  - Add pin/unpin icon button (📌) on hover for user and assistant messages
  - Display persistent visual indicator on pinned messages
  - Wire to existing `useWorkspaceStore.togglePinned`
  - Persist via existing conversation snapshot mechanism
  - Requirements: Req 15.1, 15.2, 15.4, 15.5

- [x] 4.5 Add "Branch from here" action
  - File: `apps/agent-console/src/features/agents/components/MessageActions.tsx` (modify)
  - Add "Branch" action in message actions menu on assistant messages
  - On click: create new child node from the message's parent (sibling fork) via `appendNode` with same `parent_id`
  - New branch starts with empty composer ready for input
  - Requirements: Req 16.1, 16.2

- [x] 4.6 Add branch switcher UI
  - File: `apps/agent-console/src/features/agents/components/BranchSwitcher.tsx` (NEW)
  - Display when a node has siblings (multiple children on parent)
  - Show "Branch N of M" with left/right arrows
  - Wire to existing `useWorkspaceStore.getSiblings` and `switchToBranch`
  - Persist branch selection via existing 300ms debounced localStorage write-through
  - Requirements: Req 16.3, 16.4, 16.5, 16.6

- [x] 4.7 Write unit tests for context truncation
  - File: `apps/agent-console/src/features/agents/__tests__/contextTruncation.test.ts` (NEW)
  - Test: Messages truncated from oldest when exceeding limit
  - Test: Pinned messages always preserved regardless of position
  - Test: System messages always preserved
  - Test: Most recent user/assistant pair always preserved
  - Test: No truncation when within limit
  - Test: Pinned overflow detected when pinned alone exceed budget
  - Test: excludedCount correctly reported
  - Test: Token estimation uses content.length / 4
  - Requirements: Req 14, 15

## Phase 5: Integration and Verification

- [x] 5.1 Run full backend test suite
  - Command: `services/api-server/.venv/bin/python -m pytest services/api-server/tests`
  - Verify all existing tests still pass with schema changes
  - Verify new tests pass (dag_scheduler, executor_multistep, eval_regression)
  - Command: `services/api-server/.venv/bin/python -m ruff check services/api-server/app services/api-server/tests`

- [x] 5.2 Run frontend build, lint, and tests
  - Command: `cd apps/agent-console && npm run lint && npm run build`
  - Command: `cd apps/agent-console && npm test`
  - Command: `cd apps/agent-console && npm run e2e:smoke`
  - Verify no TypeScript errors from new components
  - Verify existing 13 mocked e2e tests still pass
  - Verify new 5 e2e spec files pass
  - Total expected: 96+ unit tests, 18+ e2e tests

- [x] 5.3 Update progress documentation
  - File: `docs/development/ai/task-progress.yaml` — Add multi-step-harness-execution entry
  - File: `docs/工作日志/archive/task-progress-legacy.md` — Document new capabilities and verification commands
  - File: `omx_wiki/project-handoff-current-state.md` — Update "Next Known Work" section
