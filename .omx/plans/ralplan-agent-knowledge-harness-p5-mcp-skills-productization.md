# Ralplan: Agent Knowledge Harness P5 MCP And Skills Productization

Status: `APPROVED_PLAN`

Date: 2026-05-17

Task: 根据当前任务进度规划 P5。

## Context

Stage 07 and Agent Knowledge Harness P1-P3 are recorded as completed. P4 Memory and Context Router V2 is completed locally and verified. The next planned lane in `omx_wiki/project-handoff-current-state.md` and `omx_wiki/agent-knowledge-harness-roadmap.md` is P5 MCP and Skills productization.

Grounding snapshot:

- `.omx/context/agent-knowledge-harness-p5-mcp-skills-productization-20260517T135902Z.md`

## RALPLAN-DR Summary

### Principles

1. P5 delivers the minimal unified capability snapshot contract, not a full capability platform.
2. Runtime consumes persisted, immutable capability version snapshots; management and execution cannot diverge.
3. MCP and Skills are two capability types on the same version/hash/attachment contract.
4. Workspace chat, Agent Run, assignment, and test invocation share org scope, Agent attachment, allowed tools, PolicyEngine, and sandbox checks.
5. Secrets exist only as `secret_ref`, `secret_scope`, and redacted diagnostics; never as cleartext in API responses, ToolCall IO, ToolApproval request/decision, AdminAuditEvent, AgentEvent payloads, or Eval metadata.

### Decision Drivers

1. Current MCP is static and local: `ToolRegistry.default()` plus deterministic MCP adapter. P5 must productize it without inventing a parallel execution path.
2. Agent Knowledge Harness needs versioned, replayable evidence for active MCP/Skill versions on Run, ModelCall, ToolCall, and Eval records.
3. Current tool execution is reached through several code paths, not only the product-facing four entry points. P5 must classify every `ToolRunner` construction site as migrated, non-executing/admin-only, or explicitly blocked.
4. P5 must remain bounded: remote MCP transport, marketplace, complex RBAC, crawler/fetcher, full skill marketplace, and P6 dashboards stay out of scope.

### Viable Options

| Option | Pros | Cons | Verdict |
| --- | --- | --- | --- |
| A. Minimal unified CapabilityRegistry contract; instantiate MCP local/test and Skill pack only | Best balance; fixes runtime/management split; gives P6 stable evidence | Adds schema/API/migration work | Chosen |
| B. Build full MCP/Skill platform with remote transport and marketplace | More complete product vision | Expands security, secrets, RBAC, network, and delivery risk | Rejected for P5 |
| C. Extend static ToolRegistry only, keep Skills separate | Smaller backend change | MCP/Skill evidence diverges; Run/Eval cannot answer exact active versions | Rejected |
| D. UI-only productization | Fastest demo surface | Violates auditable/evaluable Harness target | Rejected |

## ADR

Decision:

P5 will introduce a unified CapabilityRegistry / persisted registry snapshot model. It will instantiate only:

- MCP local/test capabilities;
- Skill capability packs.

Runtime must resolve capabilities from enabled immutable Agent attachments through the unified resolver. `ToolRunner` must consume the resolved persisted snapshot, not a separate management-only registry.

Why chosen:

- It preserves the existing ToolRunner, PolicyEngine, Sandbox, ToolCall, EventStore, Run Detail, and Eval paths.
- It gives historical Runs and Evals stable capability version/hash evidence.
- It avoids premature remote MCP transport or marketplace design.

Consequences:

- Add capability/version/attachment/snapshot schema.
- Route all tool/capability entry points through the same resolver.
- Audit every `ToolRunner` construction site and every `ToolRegistry.default()` execution use before implementation is considered complete.
- Add redaction tests for every persisted or returned diagnostic surface.

## Scope

### In Scope

- Minimal `capability` and `capability_version` contract:
  - `capability_id`
  - `type`
  - `status`
  - `current_version_id`
  - `content_sha256`
  - `config_sha256`
  - `schema_version`
- Agent attachment contract:
  - `agent_id`
  - `capability_version_id`
  - `enabled`
  - `priority` / `order`
  - `attached_by`
  - `attached_at`
- Immutable version enforcement.
- Disable semantics: affects new runs only; historical run snapshots remain unchanged.
- `CapabilityRegistry` backed by persisted capability/version/attachment rows as the single runtime source.
- MCP local/test capability management, schema validation, health/test invocation.
- Skill capability pack management, allowed tools, constraints, examples, eval case refs.
- Run/ModelCall/ToolCall active capability version ids and hashes.
- EvalCase/EvalRun capability snapshot refs or `capability_snapshot_json` storing only refs/hashes.
- Explicit capability snapshot minimum fields for each runtime artifact.
- A `ToolRunner` construction-site inventory with migration status.
- Secret-safe API/event/audit behavior.

### Out Of Scope

- Remote MCP transport.
- General plugin marketplace.
- Complex enterprise RBAC.
- Crawler/fetcher or webpage body fetching.
- Full skill marketplace.
- P6 groundedness/observability dashboards.
- Reopening Stage 07 or P1-P4.

## Authority Resolution Contract

P5 has one runtime authority:

```text
CapabilityRegistry -> agent_capability_attachment -> immutable capability_version -> ToolRunner metadata snapshot
```

`Agent.tools_json` is not a runtime authority after P5 migration begins. It is only a legacy migration input for a deterministic backfill:

1. Seed builtin capability versions for existing static registry tools.
2. For each existing Agent, create attachments that exactly match its pre-P5 `tools_json` allowlist.
3. Mark the migration/backfill version in a migration audit note or test fixture evidence.
4. After backfill, Workspace chat, Agent Run, assignment, and test invocation must not read `Agent.tools_json` for authorization or resolution.

There is no union mode and no intersection mode:

- Union with `tools_json` is forbidden because it can silently widen permissions.
- Intersection with `tools_json` is forbidden because it creates a second authority and makes snapshots depend on mutable legacy state.
- Entry-point-local parsing is forbidden because it creates bypass paths.

Resolution precedence is fixed:

1. Historical replay / Eval replay uses the capability snapshot already recorded on the Run/Eval artifact.
2. New Workspace chat, Agent Run, assignment, and agent-scoped test invocation resolve from enabled attachments only.
3. A requested tool/capability missing from the resolved attachment set is denied before ToolRunner execution.
4. Static builtins are executable only when represented as seeded capability versions and attached to the Agent, except for explicit internal migration/admin inspection paths that do not execute tools.

### ToolRunner Construction-Site Contract

P5 must inventory every runtime path that can construct or receive a `ToolRunner`. Each site must be assigned exactly one status:

- `migrated`: uses `CapabilityRegistry` / resolved persisted snapshots and enforces Agent attachment before execution.
- `non_executing_admin`: may inspect registry/capability metadata but cannot execute tools.
- `blocked_until_migrated`: returns a deterministic denial instead of executing until an Agent/capability snapshot can be supplied.

Known sites to classify:

- Workspace chat tool mentions in `services/api-server/app/api/agents.py`.
- Full Agent Run step execution in `services/api-server/app/agents/executor.py`.
- Assignment execution in `services/api-server/app/agents/orchestrator.py`.
- Subagent tool batch execution in `services/api-server/app/workers/subagent_worker.py`.
- Compatibility tool execution in `services/api-server/app/api/tasks.py`.
- Tool registry listing in `services/api-server/app/api/tools.py`.
- Planner registry use in `services/api-server/app/agents/planner.py`.
- Agent preset/registry seeding in `services/api-server/app/agents/registry.py`.

Execution-capable sites cannot stay on raw `ToolRegistry.default()`. Planner, registry listing, and preset seeding may remain non-executing only if their output is explicitly marked as advisory/seed data and cannot authorize execution.

### Test Invocation Contract

P5 has two different test surfaces:

1. `admin_validation`: validates schema, health metadata, redaction, and static capability shape. It does not execute tools and does not require Agent attachment.
2. `agent_scoped_test_invocation`: executes through `ToolRunner`, requires an `agent_id`, resolves enabled attachments through `CapabilityRegistry`, records ToolCall/Event evidence, and denies missing attachments.

No executing test invocation may fall back to principal roles, task ownership, static registry membership, or `Agent.tools_json` alone.

### Snapshot Field Contract

Snapshot fields must be concrete, not a generic JSON dumping ground. The minimum stored fields are:

- Run / AgentRun snapshot:
  - `capability_snapshot_id`
  - `agent_id`
  - ordered active `capability_version_ids`
  - ordered active `content_sha256` values
  - ordered active `config_sha256` values
  - `schema_version`
- ModelCall snapshot:
  - `capability_snapshot_id`
  - active Skill version ids/hashes used for prompt assembly
  - active MCP capability version ids/hashes available to the call
- ToolCall snapshot:
  - executed `capability_version_id`
  - `capability_id`
  - `capability_type`
  - `content_sha256`
  - `config_sha256`
  - `schema_version`
- EvalCase / EvalRun snapshot:
  - snapshot ref or normalized ids/hashes only;
  - no skill instructions;
  - no secret-bound config;
  - no ToolCall IO;
  - no raw prompts.

## Phased Plan

### Phase 0: Boundary Lock

- Record P5 as a capability management lane, not an execution-chain rewrite.
- Keep existing static builtins compatible by seeding builtin capability versions and Agent attachments from legacy `tools_json`.
- Freeze runtime authority on `CapabilityRegistry`; `Agent.tools_json` must not be consulted by new execution paths after backfill.
- Produce the `ToolRunner` construction-site inventory before implementation starts; unclassified execution sites are blockers.

### Phase 1: Shared Contract And Persistence

- Add capability, capability version, and Agent attachment persistence.
- Store content/config hashes and schema version.
- Enforce immutable version rows and append-only historical snapshots.
- Add deterministic compatibility backfill from `Agent.tools_json` to attachments. This is a one-way migration input, not a bridge resolver.
- Add a regression guard that fails if Workspace chat, Agent Run, assignment, or test invocation authorizes a capability by reading `Agent.tools_json`.

Likely files:

- `services/api-server/app/db/models.py`
- `services/api-server/app/api/schemas.py`
- `services/api-server/alembic/versions/*`
- `services/api-server/tests/test_tool_registry.py`
- `services/api-server/tests/test_agents.py`

### Phase 2: CapabilityRegistry Runtime Resolver

- Implement a single resolver for org scope, Agent attachment, enabled version, priority/order, allowed tools, PolicyEngine, and sandbox requirement.
- Make `ToolRunner` consume a registry built from resolved persisted snapshots.
- Ensure Workspace chat, Agent Run, assignment, and test invocation cannot bypass attachment checks.
- Migrate or block every execution-capable `ToolRunner` construction site in the construction-site inventory.
- Define and test entry-point precedence:
  - replay uses recorded snapshot;
  - new invocation uses enabled attachments;
  - missing attachment denies;
  - no fallback to `Agent.tools_json`.

Likely files:

- `services/api-server/app/tools/registry.py`
- `services/api-server/app/tools/runner.py`
- `services/api-server/app/tools/mcp_adapter.py`
- `services/api-server/app/api/agents.py`
- `services/api-server/app/agents/orchestrator.py`
- `services/api-server/app/agents/executor.py`

### Phase 3: MCP Local/Test And Skill Pack Instantiation

- Model MCP local/test server methods as capability versions.
- Model Skill packs as capability versions with instructions, allowed tools, constraints, examples, and eval case refs.
- Accept only `secret_ref` / `secret_scope`; redact all diagnostics.
- Add non-executing admin validation for schema/health/redaction.
- Add agent-scoped executing test invocation through existing ToolRunner, ToolCall, Policy, Sandbox, and Event paths.

Likely files:

- `services/api-server/app/api/tools.py`
- `services/api-server/app/api/agents.py`
- `services/api-server/app/sandbox/policies.py`
- `services/api-server/tests/test_tool_runner.py`
- `services/api-server/tests/test_tool_approvals.py`

### Phase 4: Runtime Evidence And Eval Snapshots

- Stamp active MCP/Skill version ids and hashes onto Run, ModelCall, and ToolCall evidence.
- Add EvalCase/EvalRun snapshot fields or references that store only capability ids/version ids/hashes/schema versions.
- Use the Snapshot Field Contract minimum fields; generic JSON is allowed only as a normalized envelope for those fields, not as permission to store raw instructions/config/IO.
- Do not store skill instructions, secret-bound config, ToolCall IO, or raw prompts in Eval snapshot metadata.
- Keep historical runs stable after disable, reattach, or version updates.

Likely files:

- `services/api-server/app/db/models.py`
- `services/api-server/app/api/schemas.py`
- `services/api-server/app/api/evals.py`
- `services/api-server/tests/test_evals.py`
- `apps/agent-console/src/features/runs/pages/RunDetailPage.tsx`
- `apps/agent-console/src/features/tasks/components/ModelCallPanel.tsx`

### Phase 5: Frontend Productization

- Upgrade `/tools` from static registry display to MCP capability management:
  - status
  - schema
  - secret ref
  - health/test invocation
  - audit link
- Add Agent Studio Skills/Capability Packs:
  - attach/detach
  - version
  - allowed tools
  - eval case refs
- Make Workspace Plugins/MCP picker show only currently enabled Agent capabilities.

Likely files:

- `apps/agent-console/src/features/tools/pages/ToolRegistryPage.tsx`
- `apps/agent-console/src/features/agents/pages/AgentListPage.tsx`
- `apps/agent-console/src/features/agents/components/ChatSurface.tsx`
- `apps/agent-console/src/features/agents/components/ComposerOptionsPopover.tsx`
- `apps/agent-console/src/features/tasks/api.ts`
- `apps/agent-console/e2e/tools-page.smoke.spec.ts`
- `apps/agent-console/e2e/agent-studio.smoke.spec.ts`

### Phase 6: Docs, Progress, And Verification

- Update progress docs and wiki.
- Add or update runbook/security notes for capability secrets and resolver failures.
- Verify no P6 dashboard, marketplace, or remote transport leaked into P5.

Likely files:

- `docs/ai/task-progress.yaml`
- `docs/task-progress.md`
- `omx_wiki/agent-knowledge-harness-roadmap.md`
- `omx_wiki/project-handoff-current-state.md`
- optional: `docs/reports/p5-mcp-skills-productization-2026-05-17.html`

## Acceptance Criteria

1. MCP local/test and Skill packs are represented by the same capability/version/attachment contract.
2. Capability versions are immutable and identified by content/config hashes.
3. Agent attachments resolve enabled immutable version ids with deterministic priority/order.
4. `ToolRunner` executes only metadata produced from resolved persisted capability snapshots; builtins are executable only through seeded builtin capability versions attached to the Agent.
5. Workspace chat, Agent Run, assignment, and test invocation all enforce org scope, Agent attachment, allowed tools, PolicyEngine, and sandbox requirement.
6. Disabling a capability/attachment affects only new runs; old runs retain their active version ids and hashes.
7. Run, ModelCall, ToolCall, EvalCase, and EvalRun expose capability evidence using refs/hashes only.
8. API responses, ToolCall IO, ToolApproval request/decision, AdminAuditEvent, AgentEvent, and Eval metadata never contain secret values.
9. `Agent.tools_json` is used only as deterministic backfill input. After backfill, tests prove every execution-capable site in the construction-site inventory denies a tool that exists in `tools_json` but lacks an enabled attachment.
10. Backfilled attachments exactly match pre-P5 `Agent.tools_json`: no union, no intersection, no implicit default tool expansion. A mismatch is a migration failure.
11. Every `ToolRunner` construction site is classified as `migrated`, `non_executing_admin`, or `blocked_until_migrated`; any unclassified execution-capable site is a release blocker.
12. Full Agent Run step execution, subagent tool batch execution, compatibility tool execution, Workspace chat, assignment execution, and agent-scoped test invocation all resolve through `CapabilityRegistry` or deterministically deny.
13. Non-executing admin validation cannot create `ToolCall`, cannot execute tools, and cannot be used as authorization evidence.
14. Snapshot records contain the Snapshot Field Contract minimum ids/hashes/schema fields and do not store raw skill instructions, secret-bound config, ToolCall IO, or raw prompts.
15. P1-P4 grounding/context evidence, Stage 07 smoke, and existing tool tests continue to pass.

## Verification Plan

Targeted backend:

```bash
cd services/api-server && uv run pytest tests/test_tool_registry.py tests/test_tool_runner.py tests/test_tool_approvals.py tests/test_agents.py tests/test_evals.py -q
```

Full backend:

```bash
cd services/api-server && uv run pytest tests -q
cd services/api-server && uv run ruff check app tests
DATABASE_URL=sqlite:////tmp/harness-p5-alembic.sqlite uv run alembic upgrade head
```

Frontend:

```bash
cd apps/agent-console && npm test
cd apps/agent-console && npm run lint
cd apps/agent-console && npm run build
cd apps/agent-console && npm run e2e:smoke:release
```

Docs/static:

```bash
python3 scripts/validate-docs.py
git diff --check
```

Required focused test cases:

- Hash calculation and immutable version enforcement.
- Attachment enable/disable and deterministic ordering.
- Workspace chat rejects unattached tool/capability mentions.
- Backfill creates attachments that exactly match existing `Agent.tools_json`.
- Workspace chat, Agent Run, assignment, and test invocation deny `tools_json`-only capabilities after backfill.
- Every `ToolRunner` construction site has a test or static assertion showing migrated/non-executing/blocked status.
- Executor step, subagent worker, and compatibility `/tasks/{id}/tools/execute` cannot execute from static registry alone.
- Admin validation of MCP/Skill capabilities does not create ToolCall rows.
- Agent-scoped test invocation requires `agent_id` plus enabled attachment and records ToolCall/Event evidence.
- Run, ModelCall, ToolCall, EvalCase, and EvalRun snapshots include the minimum ids/hashes/schema fields and exclude raw instructions/config/IO.
- Test invocation records ToolCall/Event evidence through existing runner.
- Eval snapshots remain replayable after capability update/disable.
- Secret values are absent from API responses, ToolCall IO, ToolApproval JSON, AdminAuditEvent, AgentEvent payloads, and Eval metadata.

## Critic Gate

Verdict: `APPROVE`

Rationale:

- Principles and chosen option align: the plan chooses the smallest unified contract that satisfies MCP/Skill productization without expanding into remote transport or marketplace scope.
- Alternatives are fair and explicitly rejected for delivery/security/audit reasons.
- Architect residual risks are now acceptance criteria and focused tests:
  - ToolApproval/AdminAuditEvent redaction.
  - `Agent.tools_json` is a one-way deterministic backfill input only, never a runtime authority.
  - Eval snapshots store only refs/hashes, not instructions/config/IO.
- Verification is concrete and maps to backend, frontend, migration, e2e, docs, and diff checks.

Residual risk:

- Schema and resolver changes cross several runtime paths; execution should keep migrations and resolver changes small, then wire UI after backend invariants are proven.

## Available Agent Types

- `explore`: fast repo lookup and call-path mapping.
- `architect`: contract and runtime boundary review.
- `executor`: implementation.
- `test-engineer`: focused regression and redaction coverage.
- `code-reviewer`: final review.
- `verifier`: evidence and completion validation.
- `writer`: docs/progress/report updates.

## Execution Handoff

### Ralph

Use `$ralph` for a single-owner implementation and verification loop.

Suggested sequence:

1. Generate PRD and test spec from this plan.
2. Implement backend contract and resolver first.
3. Add tests for immutability, redaction, and all runtime entry points.
4. Wire frontend management surfaces.
5. Update docs/progress and run full verification.

Suggested reasoning:

- Architecture/schema/resolver: high.
- Runtime integration: high.
- Frontend: medium.
- Verification: high.

### Team

Use `$team` if parallel execution is desired.

Suggested lanes:

1. Backend schema/migration.
2. CapabilityRegistry and ToolRunner integration.
3. MCP local/test and Skill pack APIs.
4. Run/Eval snapshot evidence.
5. Frontend Tools/Agent Studio/Workspace capability surfaces.
6. Security/redaction tests and docs/progress.

Team verification path:

- Merge backend schema/resolver before frontend depends on new API fields.
- Run targeted backend tests after lanes 1-4.
- Run frontend tests/e2e after lane 5.
- Run full verification commands before marking P5 complete.

### Goal Mode

Recommended durable follow-up: `$ultragoal`.

Use `$ultragoal` if P5 should become a tracked multi-stage goal with checkpoint evidence. Combine with `$team` if parallel lanes are needed under a durable goal ledger.

Use `$performance-goal` only for later resolver latency/snapshot-size optimization.

Use `$autoresearch-goal` only for a separate research track on remote MCP ecosystems, marketplace design, or external skill-pack formats.
