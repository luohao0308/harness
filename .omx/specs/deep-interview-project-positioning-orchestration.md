# Deep Interview Spec: Project Positioning And Execution Orchestration

## Metadata

- Profile: standard
- Context type: brownfield
- Final ambiguity: 16%
- Threshold: 20%
- Context snapshot: `.omx/context/project-positioning-orchestration-20260510T201421Z.md`
- Transcript: `.omx/interviews/project-positioning-orchestration-20260510T201421Z.md`

## Product Positioning

The project should be treated as a production enterprise AI Agent Harness platform:

```text
Model + Harness = Agent
```

It is not a generic chatbot, a task tracker, or a static product showcase. The next phase should optimize for a real privately deployable enterprise internal-test platform with a complete first-phase Harness chain.

## Desired Outcome

Deliver an internal-test version that can be deployed in a private enterprise environment and prove the complete Harness chain end to end.

The first-phase product does not need every module fully commercialized. It must prove that each critical Harness node is real, API-backed where applicable, auditable, replayable, and deployable.

## In Scope

- Docker Compose based private deployment.
- Agent configuration and model/provider settings.
- Agent Workspace as the user entry point.
- Agent Run creation from a real user goal.
- Planner generating a structured plan or DAG.
- Executor executing at least one meaningful step.
- Tool/MCP runtime with policy and audit evidence.
- Docker Sandbox execution for high-risk commands.
- WarmPool acquire/release path and lifecycle evidence.
- At least one Subagent asynchronous task path.
- Event Store records for critical state changes.
- Workspace live visibility into run state, events, tools, model calls, and outputs.
- Run Detail replay or diagnosis path.
- Eval Case saving or basic regression path.
- Observability for service health, queue/task/sandbox/model-call signals.
- Deployment and internal-test operation documentation.

## Out Of Scope / Non-Goals

- Kubernetes.
- Full multi-tenant RBAC.
- Polished marketing website.
- Full SaaS commercialization.

## Binding Harness Chain Acceptance Standard

The first-phase internal-test platform succeeds when this chain is demonstrably true:

```text
Private deployment
-> Agent configuration
-> User goal in Agent Workspace
-> Agent Run
-> Planner
-> Executor
-> Tool/MCP call
-> Sandbox/WarmPool isolation
-> Subagent asynchronous work
-> Event Store audit trail
-> Workspace live visibility
-> Run Detail replay/diagnosis
-> Eval Case/regression
-> Observability evidence
```

## Testable Acceptance Criteria

1. A developer/operator can start the platform with Docker Compose in a private internal-test environment.
2. The system exposes usable model/provider configuration and default Agent configuration.
3. A user can enter a real engineering goal in Agent Workspace and create an Agent Run.
4. The Agent Run receives a structured plan or DAG from Planner.
5. Executor runs at least one meaningful step and records its state.
6. At least one tool or MCP-shaped call is executed through policy/audit paths.
7. High-risk command execution uses Docker Sandbox, preferably through WarmPool acquisition.
8. At least one Subagent can be created, executed, tracked, and returned to the parent run.
9. Event Store records critical actions: planning, execution, tool calls, model calls, approvals, sandbox lifecycle, and Subagent state.
10. Console UI can show run state, events, tool/model call evidence, and relevant outputs.
11. Run Detail can replay or diagnose a run/failure point.
12. A successful run can be saved or represented as an Eval Case and used for a basic regression signal.
13. Observability surfaces can show service health plus task/queue/sandbox/model-call signals.
14. Documentation explains deployment, operation, validation commands, and first-phase limitations.

## Decision Boundaries

OMX may decide and execute autonomously:

- Documentation structure and governance cleanup.
- Stage decomposition.
- Test additions.
- Localized refactors.
- Bug fixes.
- API/frontend alignment work.
- Deployment script fixes.
- Progress and status document updates that follow evidence.

OMX must pause and ask before:

- Adding significant new dependencies.
- Performing destructive database migrations.
- Expanding authentication or RBAC scope.
- Changing deployment topology from Docker Compose to Kubernetes.
- Changing product positioning.
- Deleting large functional areas.

## Constraints

- Preserve the current product positioning: AI Harness Platform, not chatbot or generic task tracker.
- Treat `docs/00-product-spec.md`, `docs/SPEC-INDEX.md`, `docs/ai/00-execution-protocol.md`, `docs/ai/task-progress.yaml`, and current stage/plan artifacts as source-of-truth anchors.
- Do not treat the public website as the product center.
- Do not claim completion without fresh verification evidence.
- Existing worktree changes are active project state and must not be reverted without explicit instruction.

## Recommended Execution Orchestration

### Default Pipeline

```text
deep-interview -> ralplan -> ultragoal/autopilot -> ralph/team as needed -> ultraqa
```

### Stage 1: Stabilize The Mission With This Spec

Use this file as the clarified requirements source of truth. Do not repeat broad positioning interviews unless the user changes the target.

### Stage 2: `$ralplan` For Project-Level Plan And Test Spec

Recommended next invocation:

```text
$plan --consensus --direct .omx/specs/deep-interview-project-positioning-orchestration.md
```

Expected output:

- `.omx/plans/prd-private-deployable-harness-chain.md`
- `.omx/plans/test-spec-private-deployable-harness-chain.md`
- A gap map from the current repo state to the binding Harness chain.
- A stage sequence that preserves deployability and verification gates.

### Stage 3: Goal Or Execution Mode

Use `$ultragoal` when the work should be durable across many sessions with explicit goal tracking.

Use `$autopilot` when the PRD/test spec is clear enough and the next slice can proceed through plan, execution, code review, and QA.

Use `$ralph` when a single owner should persist on one vertical slice until verified complete.

Use `$team` when a slice has independent lanes, such as backend API, frontend Workspace, deployment/observability, and docs/verification.

Use `$ultraqa` after substantial implementation to cycle tests, fixes, and verification until the stage evidence is clean.

## Start / Pause / Resume Protocol

### Start

1. Read this spec.
2. Read `docs/SPEC-INDEX.md`.
3. Read `docs/ai/00-execution-protocol.md`.
4. Read `docs/ai/task-progress.yaml` and `docs/task-progress.md`.
5. Inspect current git status.
6. Create or update a PRD plus test spec before broad implementation.

### Pause

Before pausing, update:

- Current plan artifact.
- `docs/ai/task-progress.yaml` when stage status changes.
- `docs/task-progress.md` for human-readable current state.
- Any `.omx/context/` snapshot if the next step depends on fresh decisions.

### Resume

1. Read this spec and latest `.omx/context/` snapshot.
2. Read latest `.omx/plans/prd-*.md` and `.omx/plans/test-spec-*.md` for the active phase.
3. Read current progress docs.
4. Run the smallest relevant validation before editing if the worktree is dirty.
5. Continue from the next unchecked acceptance criterion rather than inventing a new direction.

## Anti-Drift Rules

- Every feature change must map to a row in `docs/SPEC-INDEX.md` or add/update that row first.
- Every implementation stage must have a PRD and test spec before broad edits.
- Every state-changing runtime path should emit event/audit evidence.
- Frontend state should be backend-driven for product-critical surfaces.
- Progress docs must distinguish completed vertical slices from full product completion.
- Website changes must not redefine console product behavior.
- If a proposal does not advance the binding Harness chain, defer it unless explicitly requested.

## Recommended Immediate Next Step

Run `$ralplan` against this spec to produce the project-level PRD and test spec for the privately deployable Harness chain. After that, execute the plan in vertical slices.

Preferred first implementation slice after planning:

```text
Private deployment smoke + one real Agent Run path + event/replay/eval/observability evidence
```

This slice proves whether the platform is truly deployable and chain-complete before spending effort on deeper polish.

## Residual Risk

The target is clear enough for planning and execution orchestration. Remaining risk is empirical: the repository may already implement parts of the chain, but current active worktree changes must be audited before deciding exact implementation gaps.
