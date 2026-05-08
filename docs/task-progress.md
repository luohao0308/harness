# Task Progress

## Current Execution Mode

The project now follows Spec-first development with stage-gated vertical slices.

## Current Stage

- Stage: `09-portfolio-demo-docs`
- Status: `completed`
- Updated at: `2026-05-08`
- Product line: Production Agent Harness Platform

## Completed In This Pass

- Repositioned the product around Agent Harness infrastructure.
- Added Eval Harness backend vertical slice.
- Added Eval Harness console page.
- Removed static task KPI values from the Runs page and connected them to backend observability state.
- Added Run Detail replay to an explicit event sequence.
- Added Run Detail Eval regression panel for creating a Dataset, saving the current Run as a Case, and running Dataset Eval.
- Added Run Detail Guardrail panel for policy or denied events and denied tool calls.
- Added Tool Approval backend state and Run Detail approval actions for admin approve or reject.
- Added Tool Registry API and Console `/tools` page for builtin and MCP-shaped tools.
- Added deterministic MCP Adapter slice using the same ToolRunner, PolicyEngine, ToolCall audit, and EventStore path.
- Added Run Context API for working memory, long-term memory, artifact memory, RAG context, trace memory, context compression, and model routing.
- Added Route Context API that writes `CONTEXT_COMPRESSED` and `MODEL_ROUTED` events.
- Added Run Detail Context Router panel backed by live API data.
- Added WarmPool Benchmark API with persisted reports for warm avg, warm p95, cold baseline, hit rate, and target status.
- Added Sandboxes page Benchmark action and latest benchmark metrics from backend data.
- Regenerated OpenAPI JSON/YAML from the FastAPI app for docs and website public assets.
- Added Portfolio Demo Guide, Eval Report, Benchmark Report, SDK Example, and AI Harness Engineer Capability Map.
- Updated README current status, runtime routes, and deliverable links.

## Validation Record

Current validation result:

```text
cd services/api-server && .venv/bin/python -m pytest tests/test_context_router.py -> 2 passed
cd services/api-server && .venv/bin/python -m ruff check app/agents/context_router.py app/api/tasks.py app/api/schemas.py tests/test_context_router.py -> passed
cd services/api-server && .venv/bin/python -m pytest tests/test_context_router.py tests/test_model_gateway.py tests/test_tasks.py -> 24 passed
cd services/api-server && .venv/bin/python -m pytest -> 118 passed
cd services/api-server && .venv/bin/python -m ruff check app tests -> passed
cd services/api-server && .venv/bin/python -m pytest tests/test_warm_pool.py tests/test_sandbox.py -> 11 passed
cd services/api-server && .venv/bin/python -m ruff check app/sandbox/benchmark.py app/api/sandboxes.py app/api/schemas.py app/db/models.py tests/test_warm_pool.py -> passed
OpenAPI export from FastAPI app -> passed
cd services/api-server && .venv/bin/python -m pytest tests/test_evals.py tests/test_agents.py tests/test_observability.py tests/test_event_store.py -> 38 passed
cd services/api-server && .venv/bin/python -m ruff check app tests/test_evals.py tests/test_agents.py tests/test_observability.py tests/test_event_store.py -> passed
cd apps/agent-console && npm run build -> passed
python3 scripts/validate-docs.py -> passed
docker compose -f deploy/docker-compose/docker-compose.yml config -> passed
git diff --check -> passed
```
