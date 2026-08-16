# PRD: Agent Knowledge Harness P5 MCP And Skills Productization

## Status

- Workflow: `$ralplan` followed by `$ralph`
- Source plan: `.omx/plans/ralplan-agent-knowledge-harness-p5-mcp-skills-productization.md`
- Companion test spec: `.omx/plans/test-spec-agent-knowledge-harness-p5-mcp-skills-productization.md`
- Context snapshot: `.omx/context/agent-knowledge-harness-p5-mcp-skills-productization-20260517T135902Z.md`
- Decision state: approved plan; locally implemented and verified.

## Requirements Summary

Deliver the P5 thin slice of **Agent Knowledge Harness**: productize MCP tools and Skills as
versioned, attachable, auditable Harness capabilities instead of hidden static implementation
details.

The product signal is:

```text
Capability definition/version
-> Agent attachment
-> runtime resolver
-> ToolRunner execution
-> ToolCall/Event evidence
-> Run/ModelCall/Eval snapshot refs and hashes
```

The critical security and correctness requirement is that runtime authorization has exactly one
authority chain:

```text
CapabilityRegistry
-> agent_capability_attachment
-> immutable capability_version
-> ToolRunner metadata snapshot
```

`Agent.tools_json` is legacy metadata and one-way migration input only. It must not authorize,
filter, union, intersect, or implicitly expand runtime capabilities after migration/seed backfill.

## RALPLAN-DR Summary

### Principles

1. Runtime authority is persisted capability attachment state, not static registry membership.
2. MCP and Skills share the same capability version/hash/attachment contract.
3. Historical Run/Eval evidence must remain replayable after capability disablement or version
   change.
4. Test/admin validation must be separate from execution.
5. Secrets are represented only as `secret_ref`, `secret_scope`, and redacted diagnostics.

### Decision Drivers

1. Existing MCP behavior is static and local through `ToolRegistry.default()` and the MCP adapter.
2. Tool execution reaches multiple runtime paths; any unclassified `ToolRunner` construction site
   is a bypass risk.
3. P6 groundedness and observability need exact active capability version evidence.
4. P5 must stay bounded: no remote MCP transport, marketplace, crawler/fetcher, complex RBAC, or
   full skill marketplace.

### Viable Options

| Option | Pros | Cons | Verdict |
| --- | --- | --- | --- |
| A. Unified persisted CapabilityRegistry with builtin MCP/local tools and Skill pack types | Fixes management/runtime split; supports snapshots; bounded | Adds schema, resolver, and migration work | **Chosen** |
| B. Full MCP/Skill platform with remote transport and marketplace | More complete product vision | Expands security, secrets, RBAC, network, and delivery risk | Rejected |
| C. Extend static ToolRegistry and keep Skills separate | Smaller change | Keeps MCP/Skill evidence divergent and unauditable | Rejected |
| D. UI-only productization | Fast demo | Violates auditable/evaluable Harness target | Rejected |

## Architecture Decisions

### ADR

Decision: introduce persisted capability, capability version, Agent attachment, and capability
snapshot records. `ToolRunner` resolves executable tool metadata through `CapabilityRegistry`
for an Agent-scoped attachment. If no Agent scope or enabled attachment exists, execution fails
closed and records denial evidence.

Drivers:

- runtime and management cannot be separate sources of truth;
- existing `ToolRunner`, `PolicyEngine`, sandbox, ToolCall, EventStore, Run Detail, and Eval
  paths should be preserved rather than replaced;
- historical evidence requires version ids and hashes, not only names;
- compatibility paths must be explicitly migrated or blocked.

Alternatives considered:

- Bridge resolver that unions `Agent.tools_json` and attachments: rejected because it silently
  widens permissions.
- Bridge resolver that intersects `Agent.tools_json` and attachments: rejected because it creates
  a second mutable authority and makes snapshots dependent on legacy state.
- Entry-point-local parsing: rejected because each path can drift and become a bypass.

Consequences:

- P5 adds schema and migration work.
- Runtime entry points must supply `agent_id` or deterministically deny.
- Backfill from `Agent.tools_json` must be explicit migration/seed work only.
- Tests must prove that `Agent.tools_json` alone cannot authorize execution and does not trigger
  lazy runtime backfill.

## Backend Contract

### Records

`capabilities`

- `id`, `organization_id nullable`, `capability_key`
- `type`: `builtin_tool | mcp_tool | skill`
- `status`: `active | disabled | archived`
- `current_version_id nullable`
- `schema_version`, `created_by`, `created_at`, `updated_at`

`capability_versions`

- `id`, `capability_id`, `version`, `type`, `status`
- `content_json`, `config_json`
- `content_sha256`, `config_sha256`
- `schema_version`, `created_by`, `created_at`
- rows are immutable after insert

`agent_capability_attachments`

- `id`, `organization_id nullable`, `agent_id`
- `capability_id`, `capability_version_id`
- `enabled`, `priority`, `attached_by`, `attached_at`

`capability_snapshots`

- `id`, `organization_id`, `agent_id`, `task_id`
- `source`: e.g. `registry_listing`, `tool_execute`, `tool_approval`, `eval_run`
- `schema_version`, `snapshot_json`, `snapshot_sha256`, `created_at`

Existing evidence records get capability fields:

- `tasks.capability_snapshot_json`
- `agent_runs.capability_snapshot_json`
- `model_calls.capability_snapshot_json`
- `tool_calls.capability_id`, `capability_version_id`, `capability_type`,
  `capability_content_sha256`, `capability_config_sha256`, `capability_schema_version`,
  `capability_snapshot_json`
- `eval_cases.capability_snapshot_json`
- `eval_runs.capability_snapshot_json`

### Runtime Authority

New execution follows:

1. The runtime supplies `agent_id`.
2. `CapabilityRegistry.resolve_tool(agent_id, tool_name)` reads enabled attachments only.
3. The resolved immutable `CapabilityVersion` yields executable `ToolMetadata`.
4. `ToolRunner` performs policy/sandbox checks and records ToolCall/Event evidence.
5. ToolCall stores version ids/hashes/schema refs and the normalized snapshot.

Forbidden:

- authorizing by `Agent.tools_json`;
- lazy runtime backfill from `Agent.tools_json`;
- union/intersection with `Agent.tools_json`;
- executing directly from `ToolRegistry.default()` in runtime paths;
- admin validation creating ToolCall rows.

Allowed:

- static registry listing as advisory metadata;
- deterministic migration/seed/test setup that converts legacy `tools_json` to attachments before
  runtime;
- planner/preset code using static metadata only when it cannot authorize execution.

## ToolRunner Construction-Site Contract

Every execution-capable `ToolRunner` construction site is classified:

- Workspace chat tool mentions in `app/api/agents.py`: migrated to Agent-scoped
  `CapabilityRegistry`.
- Full Agent Run step execution in `app/agents/executor.py`: migrated; compatibility runs are
  upgraded to default Agent scope before execution.
- Assignment execution in `app/agents/orchestrator.py`: migrated and guarded by attached
  capability names.
- Subagent tool batch execution in `app/workers/subagent_worker.py`: migrated; unattached tools
  return deterministic denied results.
- Compatibility `/tasks/{id}/tools/execute` in `app/api/tasks.py`: blocked until a task has
  Agent scope; bare tasks deny with capability attachment policy evidence.
- Agent-scoped test invocation in `app/api/tools.py`: migrated and requires `agent_id`.
- Tool registry listing in `app/api/tools.py`: non-executing advisory listing.
- Planner registry and Agent preset seeding: non-executing advisory/seed data only.

## MCP And Skill Capability Contract

### MCP Local/Test Capabilities

P5 models existing local/test MCP-shaped tools as capability versions:

- `source = mcp`
- `mcp_server`
- `mcp_method`
- input schema and risk metadata from existing `ToolMetadata`
- execution through existing MCP adapter only after attachment resolution

Remote MCP transport is out of scope.

### Skill Capability Packs

P5 reserves `type = skill` and the same version/hash/attachment shape for Skill packs:

- instructions, allowed tools, constraints, examples, and eval refs are versioned content;
- secret-bearing config is stored as refs/scopes only;
- prompt/model-call evidence stores refs/hashes only, not raw skill instructions;
- full marketplace and rich skill authoring remain out of scope.

## API Contract

### Admin Validation

`POST /api/tools/capabilities/admin-validate`

- validates schema/shape/redaction metadata;
- returns redacted hashes and payload;
- does not require Agent attachment;
- does not execute tools;
- does not create ToolCall rows.

### Agent-Scoped Test Invocation

`POST /api/tools/capabilities/test-invoke`

- requires `agent_id`, `tool_name`, and input;
- creates a short-lived Task for evidence;
- resolves only enabled attachments through `CapabilityRegistry`;
- executes through `ToolRunner`;
- records ToolCall/Event evidence;
- denies missing attachment.

## Snapshot Field Contract

Run/AgentRun snapshot:

- `capability_snapshot_id`
- `agent_id`
- ordered active `capability_version_ids`
- ordered active `content_sha256` values
- ordered active `config_sha256` values
- `schema_version`

ModelCall snapshot:

- `capability_snapshot_id`
- active Skill version ids/hashes used for prompt assembly
- active MCP/tool capability version ids/hashes available to the call

ToolCall snapshot:

- executed `capability_version_id`
- `capability_id`
- `capability_type`
- `content_sha256`
- `config_sha256`
- `schema_version`

EvalCase/EvalRun snapshot:

- snapshot refs or normalized ids/hashes only;
- no skill instructions;
- no secret-bound config;
- no ToolCall IO;
- no raw prompts.

## Secret And Audit Contract

Secret-like keys such as token, password, credential, authorization, api key, and apikey are
redacted recursively from:

- API responses;
- ToolCall input/output;
- ToolApproval request/decision JSON;
- AgentEvent payloads;
- Admin validation diagnostics;
- Eval metadata.

Allowed cleartext fields:

- `secret_ref`
- `secret_scope`

## Implementation Steps

### Phase 0: Boundary Lock

- Record the single authority chain.
- Classify every `ToolRunner` construction site.
- Forbid runtime `tools_json` union/intersection/lazy backfill.

### Phase 1: Persistence And Migration

- Add capability/version/attachment/snapshot schema.
- Seed builtin tool capabilities.
- Backfill existing Agents from `tools_json` into attachments during migration/seed only.
- Enforce immutable capability versions.

### Phase 2: Runtime Resolver

- Implement `CapabilityRegistry`.
- Make `ToolRunner` fail closed without Agent scope or enabled attachment.
- Stamp ToolCall capability version/hash/schema fields.

### Phase 3: Entry-Point Migration

- Migrate Workspace chat, Agent Run, assignment, subagent, and test invocation.
- Block bare compatibility tool execution.
- Keep registry listing/planner/preset surfaces non-executing.

### Phase 4: Evidence And Redaction

- Add Run/ModelCall/AgentRun/Eval snapshot fields.
- Redact input/output/approval/admin validation payloads.
- Add denial and redaction tests.

### Phase 5: Handoff

- Update roadmap/current-state wiki.
- Record verification evidence.
- Leave P6 groundedness/observability as next lane.

## Acceptance Criteria

1. Capability versions are immutable and hash-addressed.
2. Migration/seed backfilled attachments exactly match pre-P5 `Agent.tools_json`.
3. Runtime resolver never reads `Agent.tools_json` for authorization.
4. `Agent.tools_json` alone cannot execute and does not create lazy attachments.
5. Every execution-capable `ToolRunner` path resolves through `CapabilityRegistry` or denies.
6. Admin validation cannot execute tools or create ToolCall rows.
7. Agent-scoped test invocation requires `agent_id` and enabled attachment.
8. ToolCall, Run, ModelCall, AgentRun, EvalCase, and EvalRun evidence includes ids/hashes/schema
   refs.
9. Snapshot JSON stores refs/hashes only, not raw secrets, raw prompts, ToolCall IO, or skill
   instructions.
10. Secret values are redacted from all persisted/returned diagnostic surfaces.
11. Existing P1-P4 and Stage 07 backend regressions continue to pass.

## Risks And Mitigations

- Risk: hidden static-registry execution path remains.
  Mitigation: repo-wide `ToolRunner(` inventory and targeted tests for each runtime entry point.

- Risk: `tools_json` becomes a second authority.
  Mitigation: resolver does not lazy backfill; tests prove `tools_json` alone denies.

- Risk: admin validation becomes an execution bypass.
  Mitigation: separate endpoint and test that no ToolCall row is created.

- Risk: snapshots become raw JSON dumping grounds.
  Mitigation: contract limits snapshots to ids/hashes/schema refs and tests redaction surfaces.

- Risk: compatibility `/api/tasks` paths break old tests.
  Mitigation: start/resume execution upgrades to default Agent scope, while bare tool execution still
  denies without Agent/capability scope.

## Verification Steps

Required backend verification:

```bash
cd services/api-server
uv run pytest tests/test_tool_registry.py tests/test_tool_runner.py tests/test_tool_approvals.py tests/test_agents.py tests/test_subagents.py -q
uv run pytest -q
uv run ruff check app tests alembic/versions/20260517_0018_create_capability_registry.py
rm -f /tmp/harness-p5-alembic.sqlite
DATABASE_URL=sqlite:////tmp/harness-p5-alembic.sqlite uv run alembic upgrade head
git diff --check
```

Optional broader verification when frontend capability surfaces are expanded:

```bash
cd apps/agent-console && npm test
cd apps/agent-console && npm run lint
cd apps/agent-console && npm run build
python3 scripts/validate-docs.py
```

Current local evidence:

- `uv run pytest -q` -> `272 passed`
- `uv run ruff check app tests alembic/versions/20260517_0018_create_capability_registry.py`
  -> passed
- `DATABASE_URL=sqlite:////tmp/harness-p5-alembic.sqlite uv run alembic upgrade head`
  -> reached `20260517_0018`
- `git diff --check` -> passed

## Available Agent Types And Staffing Guidance

- `explore`: map runtime entry points and static registry references.
- `executor`: implement schema, resolver, ToolRunner, and API changes.
- `test-engineer`: add authority, denial, redaction, and migration tests.
- `architect` / `code-reviewer`: verify no dual-authority or bypass remains.
- `writer`: update handoff/wiki/progress evidence after verification.

## Handoff

P5 is a backend-first vertical slice. It deliberately stops before full remote MCP, marketplace,
complex RBAC, and P6 dashboards. The next lane should build groundedness/citation/unsupported-claim
Eval and Observability on top of the capability snapshot evidence delivered here.
