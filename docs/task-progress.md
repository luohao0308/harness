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
- Updated at: `2026-05-14`

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
- Added browser-level Workspace smoke coverage with Playwright for the demo-critical `Model + Harness = Agent` shell.
- Locked Workspace/small-screen console chrome into a compact layout so the chat surface and composer remain usable at 390px.

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
cd apps/agent-console && npm run e2e:install -> passed
cd apps/agent-console && npm run e2e:smoke -> 2 passed
cd apps/agent-console && npm test -- WorkspaceShellBar.render.test.tsx ChatSurface.shell.test.tsx -> 11 passed
cd apps/agent-console && npm test -> 96 passed
cd apps/agent-console && npm run lint -> passed
cd apps/agent-console && npm run build -> passed
cd services/api-server && .venv/bin/python -m pytest tests/test_cors.py -> 2 passed
```

## Not Completed Yet

- Full-infra validation profile (Tempo + Loki) not yet exercised in this environment.
- Sandbox tool execution fails (Docker socket issue in local dev — 500 on `/api/tasks/:id/tools/execute`).

## Completed: Multi-Step Harness Execution (Phase 1-5)

Date: 2026-05-13

Full implementation of multi-step DAG execution, eval regression, browser e2e coverage, and workspace context management.

### Phase 1: Multi-Step DAG Execution (Backend)
- DAG Scheduler: validate (cycles, refs, depth≤20, fan-out≤10), resolve (Kahn's topo sort, max_parallel=3)
- Executor: DAG-driven execution, step output passing (64KB), failure propagation (STEP_SKIPPED)
- Planner: depends_on field, linear chain for deterministic, DAG validation in quality report
- Model-driven tool selection with MODEL_CALL purpose=tool_parameter_generation
- Timeouts: tool 60s, subagent 300s, heartbeat 30s
- 42 new backend tests

### Phase 2: Eval Regression Flow (Backend + Frontend)
- baseline_run_id on EvalDataset + Alembic migration
- PATCH /api/evals/datasets/{id}/baseline, GET /api/evals/runs/{id}/regression
- Regression delta: 10pp threshold, newly failing/passing cases
- Eval UI: datasets, cases, runs, regression display, Set as Baseline
- "Save as Eval Case" on Run Detail page
- 10 new backend tests

### Phase 3: Browser E2E Tests
- eval-page.smoke: datasets, cases, regression delta
- observability.smoke: service health, summary metrics
- tools-page.smoke: registry, MCP, policy
- sandboxes-page.smoke: WarmPool, instances, tenant isolation
- agent-studio.smoke: 6 surfaces, model info, disabled states
- 15 new e2e tests

### Phase 4: Workspace Context Management (Frontend)
- contextTruncation.ts: truncateForContext() with content.length/4 estimation
- ContextUsageBar: amber 80%, red 95%
- useChatStream: integrated truncation into buildPayload (payload-only)
- Pin toggle UI (📌) on messages
- Branch from here action on assistant messages
- BranchSwitcher: N/M with left/right arrows
- 22 new unit tests

### Verification
```text
services/api-server/.venv/bin/python -m pytest services/api-server/tests -> 200 passed
cd apps/agent-console && npm test -> 118 passed (24 test files)
cd apps/agent-console && npm run lint -> passed
cd apps/agent-console && npm run build -> passed
cd apps/agent-console && npx playwright test --project=chromium e2e/ -> 28 passed
```

## Completed: Complete Harness Validation Flow

Date: 2026-05-13

Layers implemented:
- **L0** Static/Unit/Build/Docs gates — all pass (96 unit tests, lint, build, docs validation, whitespace).
- **L2** Mocked browser product-perception tests — 12 tests pass:
  - Workspace shell failure path (2 existing tests preserved)
  - Workspace success-flow: run_created → delta → tool_call → artifact → usage → done
  - Run Detail: summary, Plan DAG, Tool Calls, Guardrails, Event Stream, Subagents, Model Calls, Replay
  - Inspector deep-link anchors (#plan, #model-calls, #tool-runtime, #approvals)
- **L3** Live browser validation spec created (separate from mocked smoke):
  - L3A: Canonical Run browser continuity (uses HARNESS_E2E_RUN_ID from backend smoke)
  - L3B: Live Workspace user journey (uses HARNESS_E2E_LIVE_WORKSPACE flag)
- **L4** UI deep-link and state coherence:
  - Added id attributes to RunDetailPage sections for Inspector hash anchors
  - Workspace Run status behavior: lazy projection (intentional, tested)
- **L5** Evidence capture:
  - Report directory: `.omx/reports/complete-harness-validation-flow/`
  - Orchestration script: `scripts/validate-harness-flow.sh`

Verification commands:
```text
cd apps/agent-console && npm run e2e:smoke -> 12 passed
cd apps/agent-console && npm test -> 96 passed
cd apps/agent-console && npm run lint -> passed
cd apps/agent-console && npm run build -> passed
python3 scripts/validate-docs.py -> passed
git diff --check -> passed
```

## Completed: Workspace Navigation Resilience

Date: 2026-05-13

Bug fix: Stream content and Run state now survive client-side navigation away from Workspace mid-stream.

Changes:
- **activeRunId** lifted from component `useState` to zustand global store — Run state persists across route navigation.
- **SSE delta writes** bypass `useStreamFlush` and write directly to zustand store — content survives component unmount.
- **Hydration guard** on re-mount skips overwriting store when in-memory assistant content is newer than localStorage snapshot.
- **Navigation resilience e2e test** added covering link-click-away and browser-back flow.

Verification:
```text
cd apps/agent-console && npx playwright test --project=chromium e2e/nav-resilience.spec.ts -> 1 passed
cd apps/agent-console && npm run e2e:smoke -> 12 passed
cd apps/agent-console && npm test -> 96 passed
cd apps/agent-console && npm run lint -> passed
git diff --check -> passed
```

Total mocked browser tests: 13.

## Completed: L3 Live Browser Validation

Date: 2026-05-13

L3 live browser validation passes against real backend (API on 127.0.0.1:8000 + frontend on 127.0.0.1:5177).

Results:
- **L3A** Canonical Run browser continuity — 4 tests pass:
  - Run Detail shows canonical run with full Harness evidence
  - Replay works for the canonical run
  - `/runs/:runId/events` shows event evidence
  - `/runs/:runId/subagents` shows subagent evidence
- **L3B** Live Workspace user journey — 1 test passes:
  - Submit a goal through Workspace and perceive a created Run with assistant output

Verification:
```text
HARNESS_E2E_RUN_ID=<run_id> HARNESS_E2E_LIVE_WORKSPACE=1 npx playwright test --project=chromium e2e/live-harness.spec.ts -> 5 passed
cd apps/agent-console && npm run e2e:smoke -> 13 passed
cd apps/agent-console && npm run lint -> passed
git diff --check -> passed
```

Total live browser tests: 5. Total mocked browser tests: 13.

## Completed: Release-Gate And Handoff Hygiene

Date: 2026-05-14

This post-stage hygiene pass keeps the quick browser smoke fast while adding an explicit mocked browser release gate:

- `npm run e2e:smoke` remains the quick Workspace + Run Detail loop.
- `npm run e2e:smoke:release` covers Workspace, Workspace success, Run Detail, Agent Studio, Eval, Observability, Tools, Sandboxes, and navigation resilience.
- `scripts/validate-harness-flow.sh` L2 now runs the release smoke gate.
- `apps/agent-console/README.md`, `docs/human/10-task-progress.md`, `docs/ai/task-progress.yaml`, and `omx_wiki/project-handoff-current-state.md` distinguish quick smoke, release smoke, and live validation.
- Stage 07 remains closed historical context; this work does not reopen it.

Verification:
```text
cd apps/agent-console && npm run e2e:smoke -> passed
cd apps/agent-console && npm run e2e:smoke:release -> passed
cd apps/agent-console && npm run lint -> passed
cd apps/agent-console && npm run build -> passed
python3 scripts/validate-docs.py -> passed
git diff --check -> passed
targeted stale-reference audit -> passed with explainable historical/quick-smoke matches only
```

## Next Step

Use the release-gate smoke for mocked browser validation:

```text
cd apps/agent-console && npm run e2e:smoke:release
```

Keep primary Agent Run smoke and live validation in the full validation path:

```text
python3 scripts/smoke-test-agent-run.py
./scripts/validate-harness-flow.sh --full-infra
```
