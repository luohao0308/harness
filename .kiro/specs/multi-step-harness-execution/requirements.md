# Requirements Document

## Introduction

This specification covers four interconnected capabilities for Forge Harness (Model + Harness = Agent), advancing the platform from Stage 07 (private-deployable-harness-chain) into full multi-step execution, eval regression, broader e2e coverage, and improved workspace context management. Together these features close the gap between "Planner generates a plan" and "Executor actually runs the full DAG with real tool calls, sandbox isolation, and subagent delegation per step."

## Resolved Design Decisions

The following decisions were made during requirements analysis to resolve ambiguities and conflicts:

1. **Run final state rule:** FAILED if any step reached STEP_FAILED; COMPLETED if all steps reached STEP_COMPLETED or STEP_SKIPPED.
2. **Max parallel steps:** Default `max_parallel=3`, configurable per Agent.
3. **Subagent trigger condition:** Only `execution_mode=async` AND `can_spawn_subagent=true` triggers subagent delegation. Sync steps with `can_spawn_subagent=true` execute inline.
4. **Empty `depends_on` behavior:** When ALL steps have empty `depends_on`, execute linearly in plan order (backward compatible with current behavior).
5. **Token estimation:** Client-side approximation using `content.length / 4`. Truncation happens in `buildPayload` (payload-only, store data preserved).
6. **Default timeouts:** Tool call timeout = 60s, Subagent timeout = 300s, Subagent heartbeat interval = 30s.
7. **Step output size limit:** Maximum 64KB per step output passed as context to dependent steps.
8. **Regression threshold:** Absolute percentage points (e.g., 90% → 79% = 11pp drop = regression).
9. **Branch from here:** Creates a new child from the selected message's parent (sibling fork), not a child of the selected message.
10. **Pinned message overflow:** If total pinned message tokens exceed Context_Window, send all pinned messages but emit a warning; do not silently drop pinned content.

## Glossary

- **Executor**: The backend component (`app/agents/executor.py`) responsible for running plan steps sequentially or in parallel, invoking tools, sandboxes, and subagents.
- **Planner**: The backend component (`app/agents/planner.py`) that decomposes a user goal into a structured `ExecutionPlan` DAG of `PlanStep` objects.
- **ExecutionPlan**: A Pydantic model containing a summary, ordered list of `PlanStep` objects, quality metadata, and planner provenance.
- **PlanStep**: A single unit of work within an `ExecutionPlan`, with fields for `key`, `execution_mode` (sync/async), `requires_sandbox`, `can_spawn_subagent`, `tool_hints`, `risk_level`, and `acceptance_criteria`.
- **DAG**: Directed Acyclic Graph — the dependency structure between plan steps where edges represent "must complete before" relationships.
- **Step_Dependency**: An explicit edge in the DAG declaring that one step requires the output of another before it can begin.
- **Tool_Call**: A recorded invocation of a registered tool through the ToolRunner, subject to policy and audit.
- **Sandbox**: A Docker container providing isolated execution for high-risk commands, acquired from the WarmPool.
- **WarmPool**: A pre-allocated pool of ready Docker containers for low-latency sandbox acquisition.
- **Subagent**: An independently executing child agent spawned by the Executor for async or parallel work.
- **ReAct_Trace**: A Reason-Act-Observe cycle recorded per step for auditability.
- **Eval_Dataset**: A collection of Eval Cases used for regression testing.
- **Eval_Case**: A single test case within a Dataset, optionally derived from a completed Agent Run.
- **Eval_Run**: An execution of the Trace Grader against all Cases in a Dataset, producing regression metrics.
- **Baseline**: A historical Eval Run used as the reference point for regression comparison.
- **Regression_Delta**: The difference in metrics between the current Eval Run and the Baseline.
- **Workspace**: The chat-first frontend surface (`AgentWorkspacePage`) where users submit goals and observe Agent Run progress.
- **Context_Window**: The token budget available for conversation history sent to the model.
- **Pinned_Message**: A conversation node explicitly marked by the user to always be included in context regardless of truncation.
- **Conversation_Branch**: A fork in the conversation tree where the user explores an alternative path from a given node.
- **Active_Path**: The ordered sequence of conversation nodes from root to the current leaf, representing the visible conversation thread.
- **E2E_Test**: A Playwright browser-level test that validates user-facing behavior end-to-end.

## Requirements

### Requirement 1: Multi-Step DAG Execution

**User Story:** As a platform operator, I want the Executor to run all steps in a generated plan with real tool calls and proper dependency ordering, so that complex multi-step goals are completed autonomously.

#### Acceptance Criteria

1. WHEN the Planner generates an ExecutionPlan with step dependencies, THE Executor SHALL resolve the DAG topologically and execute steps in dependency order.
2. WHEN two or more PlanSteps have no mutual dependency, THE Executor SHALL execute those steps concurrently using async workers, up to a maximum of `max_parallel` (default 3) concurrent steps.
3. WHEN a PlanStep declares `requires_sandbox=true`, THE Executor SHALL acquire a Sandbox from the WarmPool before executing the step's tool calls.
4. WHEN a PlanStep has `execution_mode=async` AND `can_spawn_subagent=true`, THE Executor SHALL delegate execution to a Subagent and track its lifecycle through the Event Store. Sync steps with `can_spawn_subagent=true` SHALL execute inline without spawning a subagent.
5. WHEN a sync PlanStep completes successfully, THE Executor SHALL record a ReAct_Trace containing the Reason, Act, and Observe phases with tool call evidence.
6. WHEN a PlanStep fails, THE Executor SHALL mark the step as STEP_FAILED, mark all dependent downstream steps as STEP_SKIPPED, and allow independent branches to continue execution.
7. WHEN all PlanSteps in the DAG reach a terminal state (STEP_COMPLETED, STEP_FAILED, or STEP_SKIPPED), THE Executor SHALL transition the Agent Run to FAILED if any step reached STEP_FAILED, or COMPLETED if all steps reached STEP_COMPLETED or STEP_SKIPPED.
8. THE Executor SHALL emit Event Store records for STEP_STARTED, STEP_COMPLETED, STEP_FAILED, and STEP_SKIPPED for every step in the plan.
9. WHEN all steps in a plan have empty `depends_on` lists, THE Executor SHALL execute them linearly in plan order (backward compatible with current single-step behavior).
10. Concurrent steps SHALL have overlapping STEP_STARTED/STEP_COMPLETED time windows as observable evidence of parallelism.

### Requirement 2: Step Dependency Declaration in Plans

**User Story:** As a platform operator, I want the Planner to declare explicit dependencies between steps, so that the Executor can determine safe parallelism and correct ordering.

#### Acceptance Criteria

1. THE PlanStep schema SHALL include a `depends_on` field containing a list of step keys that must complete before this step begins. Default value is an empty list.
2. WHEN the Planner generates a plan, THE Planner SHALL populate `depends_on` for each step based on data-flow and ordering constraints inferred from the goal and step descriptions.
3. WHEN the `depends_on` field references a step key not present in the plan, THE Planner SHALL reject the plan and fall back to deterministic planning.
4. WHEN a cycle is detected in the dependency graph, THE Planner SHALL reject the plan and fall back to deterministic planning.
5. THE DeterministicPlanner SHALL generate plans with linear dependencies (each step N depends on step N-1) as the safe default.
6. THE DAG SHALL have a maximum depth of 20 steps and maximum fan-out of 10 concurrent branches to prevent resource exhaustion.

### Requirement 3: Real Tool Execution Per Step

**User Story:** As a platform operator, I want each plan step to invoke the actual tools declared in its `tool_hints`, so that execution produces real artifacts and auditable evidence.

#### Acceptance Criteria

1. WHEN a PlanStep has `tool_hints` referencing registered tools, THE Executor SHALL invoke the Model Gateway to select which tools to call and generate their parameters, then invoke those tools through the ToolRunner with full policy and audit enforcement.
2. THE Executor SHALL record a MODEL_CALL event with `purpose=tool_parameter_generation` when invoking the Model Gateway for tool argument generation.
3. WHEN a tool call is denied by policy, THE Executor SHALL record the denial in the Event Store and mark the step as STEP_FAILED with `next_action=await_approval`.
4. WHEN a tool call succeeds, THE Executor SHALL pass the tool output (truncated to 64KB maximum) as context to subsequent steps that depend on this step.
5. IF a tool call exceeds 60 seconds (configurable per tool via `timeout_seconds` in the Tool Registry), THEN THE Executor SHALL terminate the call, record a TOOL_TIMEOUT event, and mark the step as STEP_FAILED.

### Requirement 4: Sandbox Isolation Per Step

**User Story:** As a platform operator, I want steps requiring sandbox isolation to execute inside a dedicated Docker container, so that high-risk commands cannot affect the host system.

#### Acceptance Criteria

1. WHEN a PlanStep has `requires_sandbox=true` and the task has `enable_sandbox=true`, THE Executor SHALL acquire a container from the WarmPool before executing tool calls.
2. WHEN the WarmPool has no available containers, THE Executor SHALL wait up to 30 seconds for a container to become available before marking the step as STEP_FAILED with a WARMPOOL_TIMEOUT event.
3. WHEN sandbox execution completes, THE Executor SHALL release the container back to the WarmPool.
4. WHEN a sandbox container exceeds its memory limit (default 512MB) or CPU limit (default 1 core), THE Executor SHALL terminate the container, record a SANDBOX_OOM event, and mark the step as STEP_FAILED.
5. THE Executor SHALL pass step-specific environment variables and mounted volumes to the sandbox container based on the step's tool requirements.

### Requirement 5: Subagent Delegation Per Step

**User Story:** As a platform operator, I want async steps to be delegated to independent subagents that execute concurrently, so that long-running or parallel work does not block the main execution thread.

#### Acceptance Criteria

1. WHEN a PlanStep has `execution_mode=async` AND `can_spawn_subagent=true`, THE Executor SHALL create a Subagent via the SubagentManager with the step's description and tool hints. The Subagent SHALL inherit the parent task's policy constraints.
2. WHEN a Subagent completes its work, THE Executor SHALL collect its results (truncated to 64KB) and make them available to downstream dependent steps.
3. WHEN a Subagent fails, THE Executor SHALL record the failure in the Event Store and mark the parent step as STEP_FAILED.
4. WHILE a Subagent is executing, THE Executor SHALL emit heartbeat events to the Event Store at least once every 30 seconds for observability.
5. IF a Subagent exceeds 300 seconds (configurable per task via `max_runtime_seconds`), THEN THE Executor SHALL terminate the Subagent, record a SUBAGENT_TIMEOUT event, and mark the step as STEP_FAILED.

### Requirement 6: Save Run as Eval Case

**User Story:** As a QA engineer, I want to save a completed Agent Run as an Eval Case in a Dataset, so that I can use it as a regression baseline.

#### Acceptance Criteria

1. WHEN a user requests to save a completed Run (status COMPLETED or FAILED) as an Eval Case, THE Eval_Service SHALL create an Eval Case with the Run's goal, model configuration, plan, tool calls, and final status as the expected output.
2. WHEN saving a Run as an Eval Case, THE Eval_Service SHALL capture the full execution trace including step results, tool call sequences, and model call counts.
3. THE Run Detail page SHALL display a "Save as Eval Case" action on Runs with status COMPLETED or FAILED.
4. WHEN the Eval Case is created from a Run, THE Eval_Service SHALL link the case to the source Run via `source_task_id` for traceability.

### Requirement 7: Eval Regression Comparison

**User Story:** As a QA engineer, I want to compare Eval Run results against a historical baseline, so that I can detect regressions in agent behavior.

#### Acceptance Criteria

1. WHEN an Eval Run completes, THE Eval_Service SHALL allow the user to designate it as a Baseline for future comparisons.
2. WHEN a new Eval Run is executed against a Dataset that has a Baseline, THE Eval_Service SHALL compute a Regression_Delta comparing current metrics to the Baseline metrics.
3. THE Regression_Delta SHALL include per-case pass/fail changes, aggregate metric differences (task_success_rate, tool_selection_accuracy, avg_latency_ms), and newly failing cases.
4. WHEN the Regression_Delta shows a decrease in task_success_rate exceeding 10 absolute percentage points (e.g., 90% → 79%), THE Eval_Service SHALL flag the run as a regression.
5. THE Eval UI SHALL display the Regression_Delta alongside the current Eval Run metrics, using CSS classes `data-regression="true"` (red) and `data-improvement="true"` (green) for testability.
6. WHEN no Baseline is set for a Dataset, THE Eval_Service SHALL return a null Regression_Delta and the UI SHALL display "No baseline set" instead of delta metrics.

### Requirement 8: Eval UI End-to-End Flow

**User Story:** As a QA engineer, I want a complete UI flow for creating datasets, saving cases from runs, executing eval runs, and viewing regression results, so that I can manage the eval lifecycle without using the API directly.

#### Acceptance Criteria

1. THE Eval_Page SHALL display a list of Eval Datasets with case counts and last-run status.
2. THE Eval_Page SHALL provide a form to create a new Eval Dataset with name and description.
3. THE Eval_Page SHALL display Eval Cases within a selected Dataset, showing source run link, input summary, and expected output.
4. THE Eval_Page SHALL provide a button to trigger an Eval Run against a selected Dataset.
5. WHEN an Eval Run completes, THE Eval_Page SHALL display the run metrics, per-case results, and regression delta if a baseline exists.
6. THE Eval_Page SHALL allow the user to set a completed Eval Run as the Baseline for its Dataset.

### Requirement 9: Browser E2E Tests for Eval Page

**User Story:** As a developer, I want Playwright browser tests covering the Eval page flows, so that UI regressions are caught automatically.

#### Acceptance Criteria

1. THE E2E_Test suite SHALL include mocked tests for the Eval Dataset list, case list, and Eval Run results display.
2. THE E2E_Test suite SHALL include a mocked test for the "Save Run as Eval Case" flow from Run Detail.
3. THE E2E_Test suite SHALL include a mocked test for triggering an Eval Run and viewing regression metrics.
4. WHEN the Eval E2E tests run, THE test runner SHALL complete within 30 seconds using mocked API responses on CI.

### Requirement 10: Browser E2E Tests for Observability Page

**User Story:** As a developer, I want Playwright browser tests covering the Observability page, so that monitoring UI regressions are caught automatically.

#### Acceptance Criteria

1. THE E2E_Test suite SHALL include mocked tests verifying the Observability page renders service health indicators.
2. THE E2E_Test suite SHALL include mocked tests verifying the Observability page renders queue depth, active runs, sandbox utilization, and model call latency panels.
3. THE E2E_Test suite SHALL include a mocked test verifying that clicking a Run link in Observability navigates to the Run Detail page.

### Requirement 11: Browser E2E Tests for Tools Page

**User Story:** As a developer, I want Playwright browser tests covering the Tools page, so that tool registry UI regressions are caught automatically.

#### Acceptance Criteria

1. THE E2E_Test suite SHALL include mocked tests verifying the Tools page renders the Tool Registry list with tool names, risk levels, and policy status.
2. THE E2E_Test suite SHALL include a mocked test verifying the MCP adapter section renders registered MCP tools.
3. THE E2E_Test suite SHALL include a mocked test verifying that tool policy toggles update the displayed state.

### Requirement 12: Browser E2E Tests for Sandboxes Page

**User Story:** As a developer, I want Playwright browser tests covering the Sandboxes page, so that infrastructure UI regressions are caught automatically.

#### Acceptance Criteria

1. THE E2E_Test suite SHALL include mocked tests verifying the Sandboxes page renders WarmPool status (min_ready, max_ready, available count).
2. THE E2E_Test suite SHALL include a mocked test verifying the Sandboxes page renders active sandbox instances with their lifecycle state.
3. THE E2E_Test suite SHALL include a mocked test verifying the Tenant Isolation section displays isolation policy.

### Requirement 13: Browser E2E Tests for Agent Studio Page

**User Story:** As a developer, I want Playwright browser tests covering the Agent Studio page, so that configuration UI regressions are caught automatically.

#### Acceptance Criteria

1. THE E2E_Test suite SHALL include mocked tests verifying the Agent Studio page renders Model, Tools/MCP, Prompt, RAG, Templates, and Orchestration configuration surfaces.
2. THE E2E_Test suite SHALL include a mocked test verifying that model provider selection persists through the settings API.
3. THE E2E_Test suite SHALL include a mocked test verifying that disabled surfaces (RAG, Templates) display their API-pending state.

### Requirement 14: Workspace Context Window Management

**User Story:** As a user, I want the Workspace to manage my conversation context intelligently within the model's token budget, so that long conversations remain coherent without exceeding limits.

#### Acceptance Criteria

1. THE Workspace SHALL track estimated token usage for the Active_Path using `content.length / 4` approximation and display a context usage indicator (progress bar) showing current usage relative to the Context_Window limit.
2. WHEN the Active_Path exceeds 80% of the Context_Window, THE Workspace SHALL display an amber warning indicator. WHEN it exceeds 95%, THE Workspace SHALL display a red critical indicator.
3. WHEN sending a message would exceed the Context_Window, THE Workspace SHALL truncate whole messages from the oldest end of the Active_Path (excluding pinned messages and system messages) in the API payload only — store data is never deleted.
4. THE Workspace SHALL allow the user to configure the Context_Window size through the existing context max tokens slider (already wired to `useWorkspaceStore.contextMaxTokens`).
5. WHEN context is truncated, THE Workspace SHALL always preserve: (a) system messages, (b) all pinned messages, (c) the most recent user/assistant exchange pair.
6. WHEN total pinned message tokens exceed the Context_Window, THE Workspace SHALL send all pinned messages anyway but display a warning notification indicating context overflow.
7. WHEN truncation occurs on send, THE Workspace SHALL display a brief notification showing how many messages were excluded from context.

### Requirement 15: Workspace Message Pinning

**User Story:** As a user, I want to pin important messages so they are always included in context even when older messages are truncated, so that critical instructions persist across long conversations.

#### Acceptance Criteria

1. THE Workspace SHALL display a pin/unpin icon button on hover for each conversation message (user and assistant roles).
2. WHEN a user pins a message, THE Workspace SHALL add the node ID to `pinnedNodeIds` in the store and persist this state via the existing conversation snapshot mechanism.
3. WHILE building the context payload for the model, THE Workspace SHALL include all pinned messages regardless of truncation position.
4. THE Workspace SHALL display a 📌 visual indicator on pinned messages, distinguishing them from unpinned messages.
5. WHEN a user unpins a message, THE Workspace SHALL remove the node ID from `pinnedNodeIds` and allow the message to be subject to normal truncation rules.

### Requirement 16: Workspace Conversation Branching

**User Story:** As a user, I want to branch a conversation from any message to explore alternative approaches, so that I can compare different solution paths without losing previous context.

#### Acceptance Criteria

1. THE Workspace SHALL display a "Branch from here" action on each assistant message (via the existing message actions menu).
2. WHEN a user creates a branch, THE Workspace SHALL create a new child node from the selected message's parent (sibling fork), forming a fork in the conversation tree. The new branch starts with an empty composer ready for input.
3. THE Workspace SHALL display a branch count badge (e.g., "2/3") on nodes that have multiple children (siblings).
4. THE Workspace SHALL allow the user to switch between branches using left/right arrows on the branch indicator, updating the Active_Path to reflect the selected branch via the existing `switchToBranch` store action.
5. WHEN switching branches, THE Workspace SHALL preserve the content of all branches and restore the selected branch's full conversation state including message content, metadata, and tool call evidence.
6. THE Workspace SHALL persist branch state across page navigation and browser refresh via the existing conversation snapshot persistence (300ms debounced write-through to localStorage).
