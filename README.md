# AI Harness Platform

AI Harness Platform is a production Agent infrastructure project.

```text
Model + Harness = Agent
```

A model handles reasoning and generation. Harness supplies model configuration, prompt control, tools, MCP, sandbox policy, planning, execution, event sourcing, replay, eval, observability, WarmPool, and rollout operations.

The repository keeps the public website as a public information shell. The implementation center is the Agent Console and FastAPI backend.

## Product Scope

| Module | Console Surface | Purpose |
|---|---|---|
| Agent Studio | `/agents`, `/settings/models` | Build Agents from model, prompt, tools, MCP, sandbox, RAG entry, templates entry |
| Agent Workspace | `/agents/:agentId/workspace` | Use an Agent through a single Plan surface plus Plan DAG, Event Stream, Subagents, Tool Calls, Model Calls |
| Harness Management | `/tools`, `/sandboxes` | Manage tools, MCP, permissions, sandbox policy, DAG and trigger entries |
| Observability | `/observability`, `/runs/:runId` | Inspect events, replay, cost, latency, health, audit trail |
| Eval & Testing | `/evals` | Manage datasets, eval runs, regression gates, grader traces |
| Infra | `/sandboxes`, `/settings/models` | Show WarmPool, tenant boundaries, API Gateway entry, versions and rollout state |

`Agent Run` is the product execution object. The database table named `tasks` remains an internal compatibility detail during migration.

## Active Routes

```text
/agents
/agents/:agentId/workspace
/runs
/runs/:runId
/settings/models
/tools
/observability
/evals
/sandboxes
/subagents
```

`/tasks/new` is removed from the console. `/tasks` redirects to `/runs` while compatibility routes remain.

## Current Implementation State

```text
Current stage: 07-private-deployable-harness-chain
Current status: completed
Website policy: retained as public shell
Latest post-stage completion: private deployment experience
Active next lane: pending fresh planning
```

## Agent Startup Context

New agent sessions use a low-token context path before implementation:

```text
AGENTS.md
docs/ai/agent-startup-context.md
python3 scripts/agent-context-brief.py --task "<user task>"
```

The root `AGENTS.md` is the new-session entrypoint. The startup file summarizes
the project target and current progress. The brief routes the task to the
smallest relevant `omx_wiki/`, `.omx/plans/`, and `.omx/context/` files. The
required completion write-back path is
`docs/ai/task-progress.yaml` plus a relevant `omx_wiki/` session or handoff
page.

Completed in the current focused pass:

- Agent Run creation API: `POST /api/agents/{agent_id}/runs`
- Agent Run history API: `GET /api/agents/runs`
- Workspace aggregate API: `GET /api/agents/runs/{run_id}/workspace`
- Agent Workspace three-column single Plan console
- Run History and Run Detail pages
- DeepSeek Flash and Pro default model presets through the OpenAI-compatible gateway path
- DeepSeek context metadata set to 1000000 tokens
- DeepSeek built-in preset normalization migrates legacy built-in provider settings to DeepSeek defaults
- Agent Studio configuration surfaces for Model, Tools/MCP, Prompt, RAG, Templates, and Orchestration
- Tool Runtime page surfaces Registry, Policy, Sandbox, MCP, and disabled Trigger state
- Run Detail replay-to-sequence UI with state summary, diagnosis, and failure point
- Eval Regression Gate with Trace Grader state and disabled A/B plus Human Review entries
- Executor sandbox acquire/release through WarmPool path
- WarmPool defaults set to min_ready=2 and max_ready=5
- Sandboxes Infra display for tenant isolation, WarmPool, API Gateway, and version rollout
- OpenAPI JSON/YAML regenerated for docs and website public assets
- Legacy `/api/tasks/*` OpenAPI copy downgraded to deprecated Agent Run compatibility
- Stage 07 closed the private deployable Harness-chain proof.
- Browser validation now distinguishes quick smoke, mocked release smoke, and live backend validation.
- Private deployment experience is complete: Docker Compose is the canonical low-context handoff path for a Docker-literate internal tester.

Validation completed:

```text
services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_agents.py services/api-server/tests/test_settings.py services/api-server/tests/test_model_gateway.py -> 29 passed
cd apps/agent-console && npm run build -> passed
```

Additional validation completed:

```text
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
docker compose -p harness-private-test --env-file deploy/docker-compose/.env.example -f deploy/docker-compose/docker-compose.yml up -d --build with override ports -> passed
python3 scripts/smoke-test-docker.py with HARNESS_* override URLs -> passed
python3 scripts/smoke-test-agent-run.py with HARNESS_API_BASE_URL=http://127.0.0.1:18000 -> passed
docker compose -p harness-private-test --env-file deploy/docker-compose/.env.example -f deploy/docker-compose/docker-compose.yml down -> passed
```

## Spec Documents

- [Harness Platform Spec](./docs/SPEC.md)
- [Product Spec](./docs/00-product-spec.md)
- [System Architecture](./docs/01-system-architecture.md)
- [Data Model And Event Spec](./docs/02-data-model-and-event-spec.md)
- [API Spec](./docs/03-api-spec.md)
- [Agent Runtime Spec](./docs/04-agent-runtime-spec.md)
- [Tool MCP Runtime Spec](./docs/05-tool-mcp-runtime-spec.md)
- [Guardrail Policy Spec](./docs/06-guardrail-policy-spec.md)
- [Eval Harness Spec](./docs/07-eval-harness-spec.md)
- [Console UI Spec](./docs/08-console-ui-spec.md)
- [Benchmark Spec](./docs/09-benchmark-spec.md)
- [Portfolio Demo Spec](./docs/10-portfolio-demo-spec.md)
- [Spec Mode Task Progress](./docs/task-progress.md)
- [AI Execution Docs](./docs/ai/README.md)
- [AI Execution Protocol](./docs/ai/00-execution-protocol.md)
- [AI Task Progress](./docs/ai/01-task-progress.md)
- [Machine Task Progress](./docs/ai/task-progress.yaml)
- [Human Task Progress](./docs/human/10-task-progress.md)

## Private Deployment Handoff

Use the canonical Docker Compose handoff path in [Deployment Runbook](./docs/runbooks/deployment.md).

Expected first-pass proof:

```text
docker compose --env-file deploy/docker-compose/.env.example -f deploy/docker-compose/docker-compose.yml config
docker compose --env-file deploy/docker-compose/.env.example -f deploy/docker-compose/docker-compose.yml up -d --build
python3 scripts/smoke-test-docker.py
python3 scripts/smoke-test-agent-run.py
docker compose --env-file deploy/docker-compose/.env.example -f deploy/docker-compose/docker-compose.yml down
```

If startup is blocked, record the failing service, command, log pointer, recovery note, and unproven acceptance criteria.

## Active Stage Specs

- [Stage 01: Agent Workspace Three-Column Console](./docs/ai/stages/01-agent-workspace-console.md)
- [Stage 02: Agent Studio Configuration Loop](./docs/ai/stages/02-agent-studio-config.md)
- [Stage 03: Harness Management And Tool MCP Runtime](./docs/ai/stages/03-harness-tool-mcp.md)
- [Stage 04: Event Sourcing And Replay UI](./docs/ai/stages/04-event-sourcing-replay-ui.md)
- [Stage 05: Eval And Regression Harness](./docs/ai/stages/05-eval-regression.md)
- [Stage 06: WarmPool And Infra Display](./docs/ai/stages/06-warmpool-infra.md)

## Technical Stack

```text
Backend: Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic
Database: PostgreSQL 16
Queue: Redis 7, Dramatiq
Sandbox: Docker SDK for Python, WarmPool
Observability: Prometheus, Grafana, Loki, OpenTelemetry
Console: React, Vite, TypeScript, Tailwind CSS
Website: Next.js, TypeScript, Tailwind CSS
Deployment: Docker Compose, systemd, Nginx
```

## Project Structure

```text
harness/
├─ apps/
│  ├─ agent-console/
│  └─ web-site/
├─ services/
│  └─ api-server/
├─ docs/
│  ├─ ai/
│  ├─ human/
│  ├─ api/
│  ├─ demo/
│  ├─ evals/
│  ├─ qa/
│  ├─ reports/
│  └─ runbooks/
├─ deploy/
│  └─ docker-compose/
└─ scripts/
```
