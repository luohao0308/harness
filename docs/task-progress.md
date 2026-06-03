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
- Updated at: `2026-06-02`

## Completed: User Scoped Encrypted Secret Vault V1

Date: 2026-06-03

Status: `verified`

Changes:
- Added encrypted `stored_secrets` storage for business integration secrets with user-private and organization-shared scopes.
- Added Secrets API list/upsert/delete and admin-only env import without returning raw values.
- Updated model provider keys, Dify/Coze/RAGFlow connector secrets, MCP runtime secrets, Tavily/web research, and notification channel secret fields to resolve through the vault.
- Added Agent Console `/settings/secrets` and Model Settings configured/source display.
- Kept startup-level secrets in env and platform API keys hash-only.

Verification:
```text
services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_secrets.py services/api-server/tests/test_settings.py services/api-server/tests/test_knowledge_connectors.py services/api-server/tests/test_tool_registry.py services/api-server/tests/test_observability.py -q -> 102 passed
services/api-server/.venv/bin/python -m ruff check services/api-server/app services/api-server/tests -> passed
cd services/api-server && rm -f /tmp/harness-secret-vault.sqlite && DATABASE_URL=sqlite:////tmp/harness-secret-vault.sqlite .venv/bin/alembic upgrade head -> passed through 20260608_0035
cd apps/agent-console && npm test -- SecretVaultPage.test.tsx ModelSettingsPage.test.tsx -> 10 passed
cd apps/agent-console && npm run lint -- --pretty false -> passed
cd apps/agent-console && npm run build -> passed
frontend/test/security subagents -> PASS after fixes
```

## Completed: LangGraph/LangChain Compatibility Harness V1

Date: 2026-06-02

Status: `verified`

Changes:
- Added PRD and test spec artifacts for LangGraph workflow import, LangChain tool/retriever adapters, and LangGraph-vs-native Eval contrast experiments.
- Added immutable `langgraph_workflow` capability packages that can be staged/approved/attached without entering ToolRunner, tool registry, MCP discovery, workspace implicit tool inference, or `/test-invoke`.
- Added `langgraph_node` plan execution support, LangGraph workflow/node/tool-node EventStore evidence, replay/run-detail visibility, and observability step counts.
- Added bridge-gated `LangGraphRunnerAdapter` execution: production remains fail-closed by default, while enabled execution requires optional `langgraph` plus a Harness sandbox bridge and emits completed Harness evidence.
- Added LangChain MCP-shaped tool adapter, LangChain retriever grounding connector evidence, and Eval experiment projection APIs linked to existing EvalRun/EvalResult rows.

Verification:
```text
cd services/api-server && .venv/bin/python -m pytest tests/test_tool_registry.py tests/test_planner_executor.py tests/test_executor_multistep.py tests/test_observability.py::test_runtime_architecture_counts_langgraph_steps tests/test_dag_scheduler.py tests/test_langgraph_langchain_compat.py tests/test_eval_experiments.py -q -> 122 passed
cd services/api-server && .venv/bin/python -m pytest tests/test_langgraph_langchain_compat.py tests/test_eval_experiments.py -q -> 37 passed
cd services/api-server && .venv/bin/python -m ruff check app tests -> passed
cd services/api-server && rm -f /tmp/harness-langgraph-audit.sqlite && DATABASE_URL=sqlite:////tmp/harness-langgraph-audit.sqlite .venv/bin/alembic upgrade head -> passed through 20260607_0034
cd apps/agent-console && npm test -- ToolRegistryPage.marketplace.test.tsx KnowledgePage.test.tsx RunDetailPage.optimizer.test.tsx ObservabilityV1Pages.test.tsx EvalHarnessPage.langgraph.test.tsx -> 5 files / 14 tests passed
cd apps/agent-console && npm run lint -- --pretty false -> passed
cd apps/agent-console && npm run build -> passed
cd apps/agent-console && HARNESS_PLAYWRIGHT_EXTERNAL_SERVER=1 npm run e2e:smoke -> 21 passed
API restarted in tmux session harness-api-langgraph; GET http://127.0.0.1:8000/health -> {"status":"ok","service":"api-server"}
Agent Console restarted in tmux session harness-console-langgraph; HEAD http://127.0.0.1:5173/ -> HTTP 200
Temporary Playwright Vite session harness-console-playwright; HEAD http://127.0.0.1:5177/ -> HTTP 200
git diff --check -> passed
architect/code-reviewer/test-engineer/frontend-design/verifier subagents -> PASS after fixes
```

Latest review fix:
- Closed the final code-review finding by rejecting Windows drive-letter absolute paths such as `C:\...` and `C:/...` in LangGraph graph specs, env string/list entries, and dependencies.
- Added one-page visual summary: `docs/reports/langgraph-langchain-visual-summary-2026-06-03.html`.

## Completed: P7 Console Chinese Selector Polish

Date: 2026-05-18

Status: `UI review fixes verified and pushed`

Changes:
- Added shared `MenuSelect` for model, knowledge, run, and settings dropdowns, replacing native and bespoke selectors.
- Preserved selector accessibility with keyboard/focus behavior, disabled-option skipping, grouping, top/bottom placement, and a focused component regression test.
- Added `TermHint` small-text explanations for required English terms such as MCP, RAG, API, Trace, WarmPool, JSON, Markdown, Prompt, and Provider.
- Reworked Agent Studio capability layout and model/knowledge selector presentation for a Chinese-first console.
- Updated Workspace, Eval, Observability, Run Detail, Sandboxes, Tool Registry, and Model Settings wording so required English technical values keep adjacent Chinese explanations.

Verification:
```text
cd apps/agent-console && npm run lint -> passed
cd apps/agent-console && npm test -> 30 files / 148 tests passed
cd apps/agent-console && npm run build -> passed
git diff --check -> passed
frontend http://127.0.0.1:18082/ -> ok
API http://127.0.0.1:8000/health -> {"status":"ok","service":"api-server"}
git push origin p7-release-demo-hardening -> pushed through a5d046b
```

## Completed: P7 Release And Demo Hardening

Date: 2026-05-18

Status: `P7 release demo hardening verified and pushed`

Changes:
- Added deterministic Knowledge/RAG demo seed script that uses public Agent Knowledge APIs, deterministic seed names, `p7-seed-fixture:*` idempotency keys, `seed-fixture://...` document URIs, and an agent grounding support document for the backend `min_hits=2` threshold.
- Added service-level Knowledge/RAG migration/restore smoke that runs Alembic, checks required tables, and verifies retrieval-hit and citation selector continuity after engine reopen.
- Added mocked release browser smoke covering Agent Studio seed projection, Workspace local grounding indicator, Run Detail retrieval/citation/prompt-manifest evidence, Eval grounding metrics, and Observability grounding quality.
- Wired the P7 browser smoke into `npm run e2e:smoke:release`.
- Updated deployment, troubleshooting, and web-research runbooks to distinguish deterministic local fixture evidence from optional credential-gated live provider validation.

Verification:
```text
python3 -m py_compile scripts/seed-knowledge-demo.py scripts/smoke-test-knowledge-migration-restore.py -> passed
python3 scripts/seed-knowledge-demo.py --print-plan -> passed
HARNESS_API_BASE_URL=http://127.0.0.1:18007 python3 scripts/seed-knowledge-demo.py --verify-readback --check-idempotent -> passed against temporary local API server
HARNESS_API_BASE_URL=http://127.0.0.1:18008 python3 scripts/seed-knowledge-demo.py --verify-readback --check-idempotent -> passed on non-default local API with agent_grounding-evidence_document_id
POST /api/agents/default/runs/chat/stream on http://127.0.0.1:18008 with the demo question -> returned knowledge_grounding: Local knowledge grounded the answer.
python3 scripts/smoke-test-knowledge-migration-restore.py -> passed
cd services/api-server && uv run ruff check ../../scripts/seed-knowledge-demo.py ../../scripts/smoke-test-knowledge-migration-restore.py app tests -> passed
cd services/api-server && uv run pytest tests/test_knowledge_rag.py tests/test_agents.py tests/test_evals.py tests/test_eval_regression.py tests/test_observability.py -q -> passed
cd apps/agent-console && npm run lint -> passed
cd apps/agent-console && npm run build -> passed
cd apps/agent-console && npm test -> passed
cd apps/agent-console && npm run e2e:smoke:release -> passed
docker compose --env-file deploy/docker-compose/.env.example -f deploy/docker-compose/docker-compose.yml config -> passed
python3 scripts/validate-docs.py -> passed
git diff --check -> passed
git push -u origin p7-release-demo-hardening -> pushed through c404603
```

## Completed: P6 Groundedness Eval And Observability

Date: 2026-05-18

Status: `P6 Eval-owned grounding quality verified`

Changes:
- Added `GroundingTraceV1` normalization so Eval owns groundedness pass/fail, failure reasons, citation selectors, fallback expectation/observation, unsupported markers, and forbidden evidence leak status.
- Scoped forbidden evidence leakage to Eval's normalized evidence package and removed raw `ModelCall.request_json` / `response_json` scanning from leak detection.
- Added grounding quality metrics and regression gates for grounding pass rate, citation coverage, unsupported marker rate, fallback mismatch, forbidden leak rate, required evidence misses, and low-sample caveats.
- Added read-only `GET /api/observability/grounding-quality` projection over Eval-owned traces/metrics with no raw forbidden snippet rendering.
- Updated Run Detail Eval Case save flow to persist objective evidence selectors only: citation keys, retrieval hit IDs, fallback expectation, retrieval session ID, prompt manifest ID, and policy decisions.
- Updated Eval Harness and Observability UI to display grounding metrics, regression gate state, failure reasons, leak sources, and evidence indexes without client-side quality recomputation.

Verification:
```text
cd services/api-server && uv run pytest tests/test_evals.py tests/test_eval_regression.py tests/test_observability.py -q -> 36 passed
cd services/api-server && uv run ruff check app tests -> passed
cd apps/agent-console && npm run lint -> passed
cd apps/agent-console && npm run build -> passed
cd apps/agent-console && npm test -> 147 passed
```

## Completed: P3 Real Policy-Gated Web Research

Date: 2026-05-17

Status: `P3 live provider verified`

Changes:
- Added Tavily as the first production web research adapter with `include_raw_content=false` and no backend second-hop fetch of provider-returned URLs.
- Added organization-scoped pre-call and post-result web policy gates with historical policy snapshots in `KnowledgePolicyAudit`.
- Hardened fake web research so fixture evidence stays non-verified and environment-limited.
- Bound accepted real web results to `WebResearchSource`, retrieval hits, citations, prompt manifests, events, and Run Detail evidence.
- Clarified `verified_grounded=true` as real-source-bound compatibility wording, not factual verification.
- Added deployment/runbook notes in `docs/runbooks/web-research.md`.
- Verified Tavily live smoke with a fixed low-risk query and no backend second-hop fetch.

Verification:
```text
cd services/api-server && uv run pytest tests/test_knowledge_rag.py tests/test_settings.py tests/test_evals.py tests/test_agents.py tests/test_tool_runner.py -q -> 96 passed
cd services/api-server && uv run ruff check app/api/agents.py app/api/schemas.py app/api/settings.py app/db/models.py app/knowledge.py app/knowledge_web.py app/core/config.py app/sandbox/policies.py tests/test_knowledge_rag.py tests/test_settings.py tests/test_evals.py tests/test_agents.py -> passed
Tavily live smoke -> passed (source_bound=true, fixture=false, raw_content_available=false, usage_credits=1.0)
```

## Completed: P4 Memory And Context Router V2

Date: 2026-05-17

Status: `P4 backend context assembly verified`

Changes:
- Added backend-owned `ContextAssemblyManifest` and `AgentMemoryRecord` persistence with memory scope, lifecycle, policy flags, retention metadata, append-only guards, and `ModelCall.context_manifest_id`.
- Added deterministic `ContextAssemblyService` with `TokenEstimator`, fixed token-budget drop order, memory injection wrapping, SQL-level memory eligibility, shadow/authoritative feature flag behavior, and bounded manifest metadata.
- Bound Workspace chat model calls to context manifests while preserving `PromptAssemblyManifest` as the retrieval truth source.
- Added memory lifecycle APIs and Run Detail/model-call context manifest evidence without raw prompt previews.
- Enforced compressed-summary eligibility with current schema, producer-model allowlist, branch ID match, and coverage path hash match.
- Updated frontend token-budget copy to clarify that UI token counts are predictive and backend recounts.

Verification:
```text
cd services/api-server && uv run pytest tests/test_context_router.py tests/test_agents.py tests/test_knowledge_rag.py tests/test_evals.py -q -> 91 passed
cd services/api-server && uv run pytest tests -q -> 260 passed
cd services/api-server && uv run ruff check app tests -> passed
DATABASE_URL=sqlite:////tmp/harness-p4-alembic.sqlite uv run alembic upgrade head -> reached 20260517_0017
cd apps/agent-console && npm test -> 139 passed
cd apps/agent-console && npm run lint -> passed
cd apps/agent-console && npm run build -> passed
python3 scripts/validate-docs.py -> passed
git diff --check -> passed
```

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

## Completed: Private Deployment Experience

Date: 2026-05-14

Private deployment experience is now recorded as a completed post-stage lane. The target was a Docker Compose handoff package for a Docker-literate internal tester, with this acceptance signal:

```text
Docker Compose full-chain startup
-> Console reaches expected API base URL
-> scripts/smoke-test-docker.py passes
-> scripts/smoke-test-agent-run.py passes
-> docker compose down cleanup recorded
```

Execution evidence:

```text
python3 -m py_compile scripts/smoke-test-docker.py scripts/smoke-test-agent-run.py -> passed
python3 scripts/validate-docs.py -> passed
git diff --check -> passed
docker compose --env-file deploy/docker-compose/.env.example -f deploy/docker-compose/docker-compose.yml config -> passed
docker compose -p harness-private-test --env-file deploy/docker-compose/.env.example -f deploy/docker-compose/docker-compose.yml up -d --build with override ports -> passed
python3 scripts/smoke-test-docker.py with HARNESS_* override URLs -> passed
python3 scripts/smoke-test-agent-run.py with HARNESS_API_BASE_URL=http://127.0.0.1:18000 -> passed
docker compose -p harness-private-test --env-file deploy/docker-compose/.env.example -f deploy/docker-compose/docker-compose.yml down -> passed
```

The local default ports `127.0.0.1:8000` and `127.0.0.1:5173` were already occupied, so the runtime proof intentionally used host-port overrides instead of killing unrelated local services. During smoke verification, Promtail was fixed to preserve Loki `app` and `service` labels when Docker Compose runs with a custom project name such as `harness-private-test`.

## Completed: Agent Knowledge Harness P1 Gate

Date: 2026-05-16

P1 is now recorded as a verified baseline in `.omx/reports/agent-knowledge-harness-p1/p1-gate-result-20260516T211017Z.md`.

Gate evidence:
```text
status: verified_baseline
clean_alembic_upgrade: pass
existing_data_upgrade: pass
docker_compose_config: pass
docker_private_smoke: pass
agent_run_smoke: pass
run_detail_exact_selector: pass
eval_grounding_contract: pass
append_only_audit_decision: pass
backend_frontend_docs_browser_gate: pass
```

The Docker/private blocker was cleared after Docker Desktop became available. The `harness-p2-knowledge-test` compose stack started with host-port overrides, Postgres migration reached `20260517_0015 (head)`, `scripts/smoke-test-docker.py` passed, `scripts/smoke-test-agent-run.py` passed with run `f2f14ba1-92ea-495f-973a-8eca21d6374d`, and compose cleanup completed.

## Completed: Agent Knowledge Harness P2 Local Knowledge Management

Date: 2026-05-17

P2 delivers a local knowledge source manager for agent/org-scoped text and Markdown documents, with lifecycle controls, versioned reingestion, retrieval eligibility filtering, audit-preserving historical reconstruction, `.txt` / `.md` import, and private deployment recovery evidence.

Implemented:
- Backend lifecycle contract: typed source/document/chunk fields, source disable/enable/archive, document-level version creation, stale chunks, current-version retrieval, source/document/chunk retrieval eligibility, expiry filtering, and org/agent scoped visibility.
- Scope mutation contract: source, document, chunk, and embedding `agent_id` values are updated together when a source changes between agent and org scope.
- Audit and history contract: lifecycle mutations write `knowledge-lifecycle-v1` audit events in the same request transaction, failed import/reingest creates a `FAILED` document and audit event, and historical Run/Eval exact selectors use persisted retrieval/citation/prompt snapshots instead of current active chunk state.
- Agent Studio management surface: `KnowledgeManagementPanel` covers source list/detail, document list, version history, add/reingest document, disable/enable/archive, scope changes, health/error/status badges, and actual multipart `.txt` / `.md` import controls.
- Recovery path: `docs/runbooks/migrations.md` records the knowledge restore verification contract, backed by automated restore smoke coverage.

Verification:
```text
cd services/api-server && uv run pytest tests/test_knowledge_rag.py tests/test_evals.py tests/test_agents.py -q -> 72 passed
cd services/api-server && uv run ruff check app/api/agents.py app/api/schemas.py app/db/models.py app/knowledge.py tests/test_knowledge_rag.py -> passed
cd apps/agent-console && npm test -- KnowledgeManagementPanel -> 7 passed
cd apps/agent-console && npm run e2e:smoke:release -- --grep "Agent Studio" -> 5 passed
cd apps/agent-console && npm run lint -- --pretty false -> passed
cd apps/agent-console && npm run build -> passed
docker compose private smoke + P2 Knowledge API smoke against Postgres -> passed
git diff --check -> passed
```

Private P2 smoke was refreshed after the multipart/failure/scope fixes. The compose stack built and started on override ports, Postgres migration reached `20260517_0015 (head)`, `scripts/smoke-test-docker.py` passed, `scripts/smoke-test-agent-run.py` passed with run `173a957a-50c7-4730-864f-a170030d4107`, and cleanup completed. The P2 Knowledge API smoke created multipart agent-scoped source `e4207b6c-4779-442b-9eb0-045ebd5c5065`, added a sibling document, created a multipart v2 version while preserving v1 as superseded, disabled/enabled the source, created org-scoped source `9abb368e-1011-4735-8bb5-9c98fc507ff1`, verified same-org visibility, and confirmed lifecycle audit events in compose Postgres.
