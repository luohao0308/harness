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

- Stage: `07-private-deployable-harness-chain`
- Status: `completed`
- Updated at: `2026-05-11`

## Completed In This Pass

- Rewrote core Spec files around AI Harness Platform.
- Replaced old nine-stage AI execution path with the new six-stage focused roadmap.
- Added Agent Run product API entry through `POST /api/agents/{agent_id}/runs`.
- Added Agent Run history and Workspace aggregate projection APIs.
- Replaced old task creation console route with Run history semantics.
- Rebuilt Agent Workspace as a chat-first console with config, streamed assistant output, and runtime internals.
- Added DeepSeek default model presets and verified settings/model gateway tests.
- Fixed sandbox execution path by letting Executor acquire and release WarmPool-backed sandboxes for sandboxed steps.
- Fixed test runtime with fake WarmPool and fake sandbox command path.
- Upgraded `/agents` from registry copy to Agent Studio with Model, Tools/MCP, Prompt, RAG, Templates, and Orchestration surfaces.
- Unified DeepSeek context window metadata at `1000000` tokens.
- Added DeepSeek preset normalization so legacy persisted built-in provider settings read back as DeepSeek defaults.
- Upgraded `/tools` into a Harness management surface for Registry, Policy, Sandbox, MCP, and disabled Trigger state.
- Added Run Detail replay-to-sequence UI with state summary, diagnosis, and failure point.
- Fixed Observability links to concrete Run event and Subagent routes.
- Added Eval Regression Gate, Trace Grader state, and disabled A/B plus Human Review entries.
- Set WarmPool defaults to min_ready=2 and max_ready=5.
- Added Sandboxes Infra display for tenant isolation, WarmPool, API Gateway, and version rollout.
- Regenerated OpenAPI JSON/YAML for docs and website public assets.
- Downgraded legacy `/api/tasks/*` OpenAPI copy to deprecated Agent Run compatibility.
- Completed final regression.
- Closed the Workspace Pro gap register items for `tool_call_result`, Continue semantics, artifact extraction, cost unavailable state, and branch sibling navigation.
- Kept frontend test infrastructure explicitly deferred instead of inventing a fake `test` script.
- Added Stage 07 canonical smoke script: `scripts/smoke-test-agent-run.py`.
- Added Stage 07 stage doc: `docs/ai/stages/07-private-deployable-harness-chain.md`.
- Made primary Agent Run planning resilient to runtime plan-parse failure so Stage 07 canonical smoke starts from `POST /api/agents/default/runs`.
- Added Agent Run promotion path in compatibility start endpoint so chat-created run without plan can be promoted into full Harness execution.
- Updated docker compose `api-server` runtime with Docker socket mount and `DOCKER_HOST`, enabling sandbox allocation in canonical smoke.

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
Docker runtime verification -> DeepSeek healthy/probe and context 1000000
python3 -m py_compile scripts/smoke-test-agent-run.py -> passed
python3 scripts/smoke-test-agent-run.py -> passed (run_id=3a310efa-dcbd-4216-b78c-c49241e97245; primary /api/agents/default/runs succeeded without chat-stream fallback and completed execution)
python3 scripts/smoke-test-docker.py -> passed
python3 scripts/validate-docs.py -> passed
docker compose -f deploy/docker-compose/docker-compose.yml config -> passed
services/api-server/.venv/bin/python -m pytest services/api-server/tests -> 139 passed
services/api-server/.venv/bin/python -m ruff check services/api-server/app services/api-server/tests scripts/smoke-test-agent-run.py -> passed
cd apps/agent-console && npm run build -> passed
git diff --check -> passed
```

## Not Completed Yet

- Frontend component/e2e test infrastructure remains explicitly deferred.

## Next Step

Keep primary Agent Run smoke in the regular release gate:

```text
python3 scripts/smoke-test-agent-run.py
```
