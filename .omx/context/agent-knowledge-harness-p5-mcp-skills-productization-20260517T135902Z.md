# Agent Knowledge Harness P5 MCP And Skills Productization Context

## Task Statement

Plan P5 based on current task progress.

## Desired Outcome

Produce a consensus-ready P5 plan for Agent Knowledge Harness that productizes MCP and Skills as manageable, auditable Harness capabilities after P4 Memory and Context Router V2.

## Known Facts / Evidence

- `docs/task-progress.md` records Stage 07 as completed and P3/P4 post-stage hardening as completed or verified.
- `docs/ai/task-progress.yaml` records P4 `p4-memory-context-router-v2` as `backend_context_assembly_verified` with backend, frontend, Alembic, docs, and diff validation evidence.
- `omx_wiki/project-handoff-current-state.md` states the latest completed Agent Knowledge Harness lane is P4 and the next planned lane is P5 MCP and Skills productization.
- `omx_wiki/agent-knowledge-harness-roadmap.md` defines P5 scope as MCP server/method registry, health checks, schema, secret binding, test invocation, skill manifest, attach/detach skills to Agents, Run metadata, and Eval regression by active skill version.
- `.omx/plans/prd-agent-knowledge-harness-p0-replan.md` frames P5 as treating MCP tools and Skills as controlled knowledge/action sources with manifests, audit events, source snapshots, and policy decisions.
- Existing MCP implementation is local/deterministic: `services/api-server/app/tools/registry.py` has static builtin and MCP-shaped `ToolMetadata`; `services/api-server/app/tools/mcp_adapter.py` preserves ToolCall/policy/trace/audit contracts without remote transport.
- Existing `/api/tools/registry` lists the static registry through `services/api-server/app/api/tools.py`.
- Existing Agent model stores `tools_json`, and Workspace extracts tool mentions into chat-stream payloads.
- Existing UI surfaces include `/tools` Tool Registry page, Agent Studio Tools/MCP card, Workspace header tools chip, and composer Plugins/MCP picker.

## Constraints

- Do not reopen Stage 07 or rewrite P1-P4 foundations.
- Keep P5 bounded to MCP/Skills capability management; do not absorb P6 groundedness dashboards or P7 release/demo hardening except for minimal validation evidence.
- Do not implement a full marketplace, remote untrusted plugin runner, enterprise RBAC, or general crawler.
- Preserve existing ToolRunner, PolicyEngine, sandbox, ToolCall, EventStore, Run Detail, Eval, and Agent Studio patterns.
- New user-facing web/external execution must stay policy-controlled, secret-safe, sandbox-aware, and auditable.
- The worktree currently contains local P4 changes and docs updates; future execution must avoid reverting unrelated edits.

## Unknowns / Open Questions

- Whether P5 should include real remote MCP transport in the first slice or keep transport as local/testable capability manifests with health/test invocation.
- Exact secret storage strategy for private deployment: environment-backed references, encrypted DB fields, or placeholder secret refs only.
- Whether Skills should be backend-enforced prompt/tool constraints first, or primarily an Agent Studio management surface first.
- How much Run Detail and Eval exposure belongs in P5 versus P6.

## Likely Codebase Touchpoints

- Backend:
  - `services/api-server/app/tools/registry.py`
  - `services/api-server/app/tools/mcp_adapter.py`
  - `services/api-server/app/tools/runner.py`
  - `services/api-server/app/api/tools.py`
  - `services/api-server/app/api/agents.py`
  - `services/api-server/app/api/schemas.py`
  - `services/api-server/app/db/models.py`
  - Alembic migration under `services/api-server/alembic/versions/`
  - Tests: `services/api-server/tests/test_tool_registry.py`, `test_tool_runner.py`, `test_agents.py`, `test_evals.py`
- Frontend:
  - `apps/agent-console/src/features/tools/pages/ToolRegistryPage.tsx`
  - `apps/agent-console/src/features/agents/pages/AgentListPage.tsx`
  - `apps/agent-console/src/features/agents/components/ChatSurface.tsx`
  - `apps/agent-console/src/features/agents/components/ComposerOptionsPopover.tsx`
  - `apps/agent-console/src/features/tasks/api.ts`
  - E2E: `apps/agent-console/e2e/tools-page.smoke.spec.ts`, `agent-studio.smoke.spec.ts`, `agent-workspace.smoke.spec.ts`
- Docs/progress:
  - `docs/ai/task-progress.yaml`
  - `docs/task-progress.md`
  - `omx_wiki/agent-knowledge-harness-roadmap.md`
  - `omx_wiki/project-handoff-current-state.md`

## Planning Bias

Prefer a thin vertical P5 slice:

1. Persist MCP capability and Skill manifests with org/agent scoping and immutable version records.
2. Keep execution on existing ToolRunner/Policy/Sandbox/Event paths.
3. Add a safe health/test invocation path that records ToolCall/Event evidence.
4. Attach skill versions to Agents and stamp active skill/tool versions onto Run/model/tool metadata.
5. Add focused UI management surfaces and regression tests.
