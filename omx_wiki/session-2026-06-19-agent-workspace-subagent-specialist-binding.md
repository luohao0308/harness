# Agent Workspace Subagent Specialist Binding

Category: session-log
Tags: `agent-console`, `workspace`, `subagent`, `specialist`, `orchestration`

## Summary

Agent Workspace `subagent` orchestration now creates specialist-bound subagents. The shortcut path no longer produces an untyped ordinary subagent when the user asks for a subagent/expert.

## Root Cause

`_apply_workspace_orchestration(... mode == "subagent")` called `SubagentManager.spawn(...)` without a `specialist` argument. `SubagentManager` only snapshots `specialist_id`, `specialist_slug`, role, prompt override, schema, capabilities, and budget when a specialist object is passed.

That meant the Workspace shortcut could create inspectable subagent evidence, but the subagent had no expert binding.

## Changes

- `services/api-server/app/api/agents/_workspace_chat_helpers.py`
  - selects a `SubagentSpecialist` for Workspace subagent orchestration;
  - honors optional request `specialist_slug`;
  - falls back to existing registry keyword matching;
  - uses deterministic Workspace heuristics/defaults when no keyword matches;
  - passes `specialist=...` into `SubagentManager.spawn(...)`;
  - leaves `parent_agent_id` empty for Workspace shortcut subagents because the column references `agent_runs.id`, not platform Agent ids such as `default`;
  - includes `specialist_id`, `specialist_slug`, `specialist_role`, and selection trace in the `orchestration` SSE payload.
- `services/api-server/app/api/schemas.py`
  - adds optional `specialist_slug` to `AgentChatStreamRequest`.
- `apps/agent-console/src/features/tasks/api.ts`
  - adds the matching optional `specialist_slug` request type.
- `services/api-server/tests/test_workspace_subagent_enterprise_flow.py`
  - covers automatic Workspace subagent expert binding, Chinese spaced `子 Agent` detection, explicit `specialist_slug=code-reviewer`, and vague follow-up defaulting to `researcher`.
- `services/api-server/tests/test_agents.py`
  - upgrades the existing forced-subagent regression to require `safety-checker` binding for release checklist inspection.

## Validation

```text
services/api-server/.venv/bin/python -m pytest \
  services/api-server/tests/test_workspace_subagent_enterprise_flow.py \
  services/api-server/tests/test_agents.py::test_agent_workspace_chat_force_subagent_persists_inspectable_agent_run -q
5 passed

services/api-server/.venv/bin/python -m ruff check \
  services/api-server/app/api/agents/_workspace_chat_helpers.py \
  services/api-server/app/api/schemas.py \
  services/api-server/tests/test_workspace_subagent_enterprise_flow.py \
  services/api-server/tests/test_agents.py
All checks passed

services/api-server/.venv/bin/python -m py_compile \
  services/api-server/app/api/agents/_workspace_chat_helpers.py \
  services/api-server/app/api/schemas.py \
  services/api-server/tests/test_workspace_subagent_enterprise_flow.py
passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" \
  npx tsc --noEmit --pretty false --types vite/client --skipLibCheck --jsx react-jsx \
  --lib DOM,DOM.Iterable,ES2022 --module ESNext --moduleResolution Bundler --target ES2020 \
  --esModuleInterop --allowSyntheticDefaultImports src/features/tasks/api.ts
passed

tmux restart harness_api
curl --noproxy '*' http://127.0.0.1:8000/health
{"status":"ok","service":"api-server"}

Direct API SSE POST /api/agents/default/runs/chat/stream with:
orchestration_mode=subagent
goal=请调用子 Agent 检查发布清单

emitted:
run_id=09c123c1-a5b8-4c59-8729-12a48ba7a17c
subagent_id=1938f2a1-221a-48da-868e-66023de9e90a
specialist_slug=safety-checker
specialist_role=checker

GET /api/agents/runs/09c123c1-a5b8-4c59-8729-12a48ba7a17c/workspace
GET /api/subagents/1938f2a1-221a-48da-868e-66023de9e90a

confirmed:
parent_agent_id=null
specialist_id=system-specialist-safety-checker
specialist.slug=safety-checker
context_json.specialist_slug=safety-checker
```
