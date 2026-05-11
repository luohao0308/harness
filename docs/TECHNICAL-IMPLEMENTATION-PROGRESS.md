# Technical Implementation Progress

## Product Line

```text
AI Harness Platform
Model + Harness = Agent
```

The active implementation target is a production Agent infrastructure platform with six modules:

- Agent Studio
- Agent Workspace
- Harness Management
- Observability
- Eval & Testing
- Infra

The public website is retained as a public shell. Console and backend implementation follow the AI Harness Platform plan.

## Active Stage Table

| Stage | Document | Status |
|---|---|---|
| 01 Agent Workspace Three-Column Console | `docs/ai/stages/01-agent-workspace-console.md` | completed |
| 02 Agent Studio Configuration Loop | `docs/ai/stages/02-agent-studio-config.md` | completed |
| 03 Harness Management And Tool MCP Runtime | `docs/ai/stages/03-harness-tool-mcp.md` | completed |
| 04 Event Sourcing And Replay UI | `docs/ai/stages/04-event-sourcing-replay-ui.md` | completed |
| 05 Eval And Regression Harness | `docs/ai/stages/05-eval-regression.md` | completed |
| 06 WarmPool And Infra Display | `docs/ai/stages/06-warmpool-infra.md` | completed |

## Current Code Changes

- Added Agent Run creation through `/api/agents/{agent_id}/runs`.
- Added `/api/agents/runs` history API.
- Added `/api/agents/runs/{run_id}/workspace` aggregate projection.
- Reworked console routing from Task creation to Run history and Agent Workspace.
- Added new Run History and Run Detail pages.
- Reworked Agent Workspace into a chat-first control console.
- Preserved MiniMax Anthropic-compatible model support.
- Unified MiniMax context window metadata at `400000` tokens.
- Added MiniMax built-in preset normalization for legacy persisted settings.
- Upgraded Agent Studio with configuration surfaces for Model, Tools/MCP, Prompt, RAG, Templates, and Orchestration.
- Upgraded Tool Runtime page with Registry, Policy, Sandbox, MCP, and disabled Trigger surfaces.
- Added replay-to-sequence UI to Run Detail and fixed Observability Run deep links.
- Added Eval Regression Gate and disabled A/B plus Human Review entries without fake data.
- Set WarmPool default min_ready to 2 and max_ready to 5.
- Added Sandboxes infra surfaces for tenant isolation, WarmPool, API Gateway, and version rollout.
- Regenerated OpenAPI JSON/YAML for docs and website public assets.
- Downgraded legacy `/api/tasks/*` OpenAPI copy to deprecated Agent Run compatibility.
- Final regression passed.
- Updated Executor to acquire and release sandbox instances for sandboxed steps.
- Updated tests to isolate sandbox runtime from Docker.
- Closed the Workspace Pro gap register items for tool call results, continue semantics, artifact extraction, cost unavailable state, and branch sibling navigation.
- Left frontend test infrastructure deferred on purpose.

## Validation Record

```text
services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_agents.py services/api-server/tests/test_tool_approvals.py -> 22 passed
services/api-server/.venv/bin/python -m ruff check services/api-server/app services/api-server/tests -> passed
cd apps/agent-console && npm run build -> passed
python3 scripts/validate-docs.py -> passed
services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_agents.py services/api-server/tests/test_settings.py services/api-server/tests/test_model_gateway.py -> 29 passed
cd apps/agent-console && npm run build -> passed
services/api-server/.venv/bin/python -m pytest services/api-server/tests -> 123 passed
services/api-server/.venv/bin/python -m ruff check services/api-server/app services/api-server/tests -> passed
python3 scripts/validate-docs.py -> passed
python3 scripts/smoke-test-docker.py -> passed
services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_settings.py services/api-server/tests/test_model_gateway.py -> 15 passed
services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_tool_registry.py services/api-server/tests/test_tool_runner.py services/api-server/tests/test_tool_approvals.py services/api-server/tests/test_agents.py -> 24 passed
services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_event_store.py services/api-server/tests/test_events_stream.py services/api-server/tests/test_observability.py -> 28 passed
services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_evals.py -> 2 passed
services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_warm_pool.py services/api-server/tests/test_sandbox.py -> 11 passed
services/api-server/.venv/bin/python -m pytest services/api-server/tests -> 123 passed
services/api-server/.venv/bin/python -m ruff check services/api-server/app services/api-server/tests -> passed
cd apps/agent-console && npm run build -> passed
python3 scripts/validate-docs.py -> passed
python3 scripts/smoke-test-docker.py -> passed
git diff --check -> passed
Docker runtime verification -> MiniMax healthy/probe and context 400000
```

## Open Items

- Focused six-stage AI Harness Platform vertical slice is complete.
- Workspace Pro product gaps are closed in this pass.
- Frontend component/e2e test infrastructure remains explicitly deferred.
