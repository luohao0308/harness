# Task Progress

## Current Execution Mode

The project follows Spec-first development with stage-gated vertical slices.

## Current Product Line

```text
AI Harness Platform
Model + Harness = Agent
```

Core modules: Agent Studio, Agent Workspace, Harness Management, Observability, Eval & Testing, Infra.

The website remains present as a public information shell. Console execution focuses on the AI Harness Platform plan.

## Current Stage

- Stage: `06-warmpool-infra`
- Status: `completed`
- Updated at: `2026-05-08`

## Completed In This Pass

- Rewrote core Spec files around AI Harness Platform.
- Replaced old nine-stage AI execution path with the new six-stage focused roadmap.
- Added Agent Run product API entry through `POST /api/agents/{agent_id}/runs`.
- Added Agent Run history and Workspace aggregate projection APIs.
- Replaced old task creation console route with Run history semantics.
- Rebuilt Agent Workspace as a three-column single Plan console: config, streamed Plan surface, runtime internals.
- Added MiniMax default model preset and verified settings/model gateway tests.
- Fixed sandbox execution path by letting Executor acquire and release WarmPool-backed sandboxes for sandboxed steps.
- Fixed test runtime with fake WarmPool and fake sandbox command path.
- Upgraded `/agents` from registry copy to Agent Studio with Model, Tools/MCP, Prompt, RAG, Templates, and Orchestration surfaces.
- Unified MiniMax context window metadata at `400000` tokens.
- Added MiniMax preset normalization so legacy persisted `204800` settings read back as `400000`.
- Upgraded `/tools` into a Harness management surface for Registry, Policy, Sandbox, MCP, and disabled Trigger state.
- Added Run Detail replay-to-sequence UI with state summary, diagnosis, and failure point.
- Fixed Observability links to concrete Run event and Subagent routes.
- Added Eval Regression Gate, Trace Grader state, and disabled A/B plus Human Review entries.
- Set WarmPool defaults to min_ready=2 and max_ready=5.
- Added Sandboxes Infra display for tenant isolation, WarmPool, API Gateway, and version rollout.
- Regenerated OpenAPI JSON/YAML for docs and website public assets.
- Downgraded legacy `/api/tasks/*` OpenAPI copy to deprecated Agent Run compatibility.
- Completed final regression.

## Validation Record

```text
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

## Not Completed Yet

- Focused six-stage AI Harness Platform vertical slice is complete.
- Workspace Pro full-spec gaps remain tracked for a later implementation pass:
  - `tool_call_result` backend emission and Workspace UI handling.
  - Continue preserving original Run and branch semantics.
  - Artifact extraction beyond `plan.json`.
  - Meaningful cost semantics beyond current placeholder values.
  - Branch sibling navigation in Conversation Tree.
  - Frontend component/e2e test infrastructure.

## Next Step

Manual product smoke in the browser: open `/agents/default/workspace`, create an Agent Run through the single Plan surface, inspect Plan DAG, Event Stream, Subagents, Tool Calls, Approvals, Replay, Models, Tools, Evals, Sandboxes, and Run History.
