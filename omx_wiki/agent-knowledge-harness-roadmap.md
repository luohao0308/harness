# Agent Knowledge Harness Roadmap

Category: `decision`

Tags: `agent-knowledge-harness`, `memory`, `rag`, `mcp`, `skills`, `token-optimization`, `hallucination`, `task-progress`

## Decision

The final task target is **Agent Knowledge Harness**: make the Harness layer a configurable, auditable, and evaluable capability system that turns a base model into a useful Agent.

```text
Model + Harness = Agent
```

This target comes from the repository HTML report `docs/reports/release-gate-handoff-diff-2026-05-14.html`, which reframes the next work from "add memory/RAG" into a full Harness capability layer. Each capability must answer:

- what problem it solves;
- what mechanism implements it;
- where runtime evidence is recorded.

## Final Capability Map

The final product target is not a single RAG feature. It is the combined Harness capability stack:

- **Short-term memory**: Workspace/session/branch task state, preferences, unresolved decisions, and recent tool observations.
- **Long-term memory**: durable Agent/org knowledge, facts, preferences, decisions, provenance, deletion, and expiry.
- **RAG / document knowledge**: user or internal documents are chunked, indexed, retrieved, cited, and evaluated.
- **Local-insufficient evidence path and web research**: the Agent must say when local evidence is insufficient; real web research requires a policy-gated provider and must not be mocked as real evidence.
- **MCP creation and management**: external capabilities become registered, policy-controlled, sandboxed, auditable tools.
- **Skills / capability packs**: reusable instructions, allowed tools, examples, constraints, versions, and eval cases can be attached to Agents.
- **Context and token optimization**: select between chat history, pinned context, memory, RAG, tool observations, and compression summaries under a visible token budget.
- **Hallucination control**: prefer cited evidence, mark unsupported claims, and measure groundedness.
- **Eval / regression gate**: prove capability changes with groundedness, citation quality, retrieval precision, policy, cost, and latency checks.
- **Observability / audit**: connect model calls, tool calls, retrieval hits, citations, policy decisions, memory writes, and context compression through Run events and traces.
- **Policy / sandbox**: keep tools, network, files, MCP, and research behind existing policy and sandbox boundaries.
- **Agent orchestration**: Plan DAG, subagents, handoff edges, pause/resume/cancel, replay, and evidence per step.

## Existing Implemented Foundation

The repository already contains more than the original roadmap described:

- Stage 01-07 and private deployment handoff are completed in `docs/ai/task-progress.yaml`.
- Release validation is split into quick browser smoke, mocked browser release gate, and live backend validation.
- Workspace already has chat-first execution, Plan-Act approval, branch navigation, pinned messages, context compression, token budget controls, Run Detail links, and Eval Case capture.
- Agent Studio already exposes Model, Tools/MCP, Prompt, RAG, Templates, Orchestration, and a knowledge source management surface.
- Tools/MCP already share ToolRunner, Policy, ToolCall audit, sandbox, and event paths.
- Run Detail already shows Plan DAG, Tool Calls, Guardrails, Event Stream, Subagents, Model Calls, Replay, Eval Case save, and knowledge grounding evidence.
- Eval already has datasets, cases, Eval Runs, Regression Gate, Trace Grader state, and backend-backed history.
- Observability already links service health, metrics, traces, logs, and concrete Run routes.
- Sandboxes already expose WarmPool, tenant isolation, quota, and policy-backed resource settings.

Knowledge/RAG code now exists in the current worktree:

- `services/api-server/alembic/versions/20260514_0011_create_knowledge_rag.py` creates knowledge, document, chunk, embedding, retrieval, citation, and web-source records.
- `services/api-server/alembic/versions/20260516_0012_create_knowledge_audit_manifests.py` creates prompt assembly manifest and policy audit tables.
- `services/api-server/app/knowledge.py` implements ingestion, chunking, deterministic embeddings, vector capability state, lexical/CJK fallback, retrieval sessions, citations, prompt manifest persistence, policy/omission audit rows, and insufficient-local-evidence behavior.
- `services/api-server/app/api/agents.py` exposes knowledge source lifecycle, document versioning, scope, and document endpoints, uses knowledge grounding in normal Workspace chat, and returns manifest/audit evidence to Run Detail.
- `services/api-server/app/api/evals.py` includes a deterministic grounding contract grader for prompt manifest, policy decisions, sufficient retrieval, citation-hit inclusion, and forbidden-text leakage.
- `apps/agent-console/src/features/agents/components/KnowledgeManagementPanel.tsx` provides source list/detail, document versions, add/reingest, lifecycle controls, scope/health badges, and multipart `.txt` / `.md` import controls inside Agent Studio.
- `apps/agent-console/src/features/agents/components/ChatMessageBubble.tsx` renders assistant grounding metadata.
- `apps/agent-console/src/features/runs/pages/RunDetailPage.tsx` renders retrieval hits, citations, web sources, vector capability, local status, grounded status, prompt manifest counts/hash, and policy audit decisions.
- `services/api-server/tests/test_knowledge_rag.py` covers ingestion, versioning, lifecycle, retrieval eligibility, exact historical selectors, restore/migration, lexical/CJK fallback, vector flag behavior, citation binding, prompt manifest persistence, policy audit rows, insufficient local evidence, tenant isolation, URL policy, API, and event behavior.

## Replanned Progress

### P0: Completed Baseline

Status: completed / keep closed.

- Private deployable Harness chain.
- Docker Compose private handoff.
- Release gate and handoff hygiene.
- Workspace execution evidence: context compression, Plan-Act, branching/search, Run Detail evidence, Eval Case capture.

### P1: Formalize Agent Knowledge Harness V1

Status: verified baseline.

Goal: turn the existing Knowledge/RAG implementation into the official recorded progress state.

Completed in the current P1 audit-gate slice:

- prompt manifest persistence;
- policy/omission audit persistence;
- citation snapshot metadata;
- Run Detail manifest/audit display;
- grounding Eval contract checks;
- CJK lexical fallback for small Chinese handbook content;
- attempt-level `ModelCall` binding through `grounding_correlation_id`, `prompt_manifest_id`, `model_request_sha256`, `attempt_index`, and `terminal_status`;
- deterministic request-hash generation with manifest/model-call validation before grounded `ModelCall` insertion;
- exact Run Detail and Eval selectors for `retrieval_session_id` and `prompt_manifest_id`;
- fallback metadata via `inferred_fallback` and `fallback_reason`;
- bounded selected-evidence snapshots and safe omitted-candidate metadata;
- fake web fallback isolated to the explicit `knowledge.web_research_provider=fake` fixture path;
- explicit `grounding_provider`, `fixture_grounded`, `verified_grounded`, and `grounding_verification_reason` semantics;
- Eval fixture grounding opt-in via `allow_fixture_grounding`;
- denied/redacted policy isolation before prompt assembly;
- v2 model request hash recomputation from persisted ordered message hashes without raw request previews;
- Run Detail Model Calls binding-chain display;
- Run Detail saved Eval Cases preserve exact grounding contracts;
- `[Wn]` web citation normalization;
- regression coverage for sufficient evidence, insufficient evidence, tenant isolation, policy audit, denied/redacted isolation, CJK single-chunk grounding, model-call binding, v2 hash recomputation, exact selectors, fallback metadata, Run Detail Eval-save contract propagation, and stream-abort terminal status.

Fresh validation evidence is captured in [[session-2026-05-16-agent-knowledge-p1-grounding-audit]] and `.omx/reports/agent-knowledge-harness-p1/p1-gate-result-20260516T211017Z.md`.

Verified-baseline evidence:

- P1 gate artifact status is `verified_baseline`.
- Clean SQLite upgrade and compose/Postgres migration reached `20260517_0015 (head)`.
- Existing-data and restore smoke tests preserve P1 knowledge rows, exact historical evidence, lifecycle events, and org isolation.
- Docker/private smoke, Agent Run smoke, backend/frontend/docs/browser gates, exact selector, Eval grounding, and append-only audit decision are recorded as pass.

### P2: Productize Local Knowledge Management

Status: completed / pushed.

Goal: make local knowledge usable beyond an inline demo form.

Delivered scope:

- source lifecycle: edit, disable, enable, archive, status, versions, provenance, expiry;
- document-level versioned reingestion with stale chunks and current-version retrieval;
- multipart `.txt` / `.md` import with MIME and size validation;
- org-scoped versus agent-scoped source visibility and same-org/foreign-org isolation;
- source health and indexing errors in Agent Studio;
- migration and backup/restore notes for private deployment, backed by automated restore smoke.

Verification evidence:

- `uv run pytest tests/test_knowledge_rag.py tests/test_evals.py tests/test_agents.py -q` -> `72 passed`.
- `npm test -- KnowledgeManagementPanel` -> `7 passed`.
- `npm run e2e:smoke:release -- --grep "Agent Studio"` -> `5 passed`.
- Compose/Postgres P2 Knowledge API smoke passed with agent-scoped source, sibling document, v2 document version, lifecycle actions, org-scoped source visibility, and lifecycle audit rows.

### P3: Add Real Policy-Gated Web Research

Status: completed / pushed.

Goal: support external research only when a real provider and policy boundary exist.

Delivered scope:

- Tavily adapter and `TAVILY_API_KEY` configuration with `include_raw_content=false`;
- no backend second-hop fetch of provider-returned URLs;
- organization-scoped pre-call policy for provider enablement, key presence, query bounds, secret-pattern blocking, allowlist intent, timeout, max results, and per-run call limits;
- authoritative post-result URL policy for normalized URL, credentials, allow/deny domains, DNS/IP classification, private/local/link-local/metadata/reserved/multicast blocking, and safe URL hashing;
- `web_research_attempts` ledger with `(run_id, call_slot)` uniqueness for call reservation;
- source snapshots, retrieval hits, prompt manifests, citations, policy audit snapshots, and events for accepted real web results;
- fake provider hardening so fixture evidence remains non-verified and environment-limited;
- Run Detail source-bound wording, citation count, and provider/request/raw badges;
- runbook and HTML explanation report.

Verification evidence:

- Backend target tests: `96 passed`.
- Ruff: passed.
- Alembic clean SQLite upgrade to `20260517_0016`: passed.
- Frontend lint/build/targeted tests: passed.
- Live Tavily smoke: passed with `source_bound=true`, `fixture=false`, `raw_content_available=false`, `usage_credits=1.0`.
- Pushed to `origin/main` through `76f11d5`.

Important boundary: P3 is not a crawler. If the backend later fetches webpage bodies, that belongs in a separate P4+ crawler/fetcher security design.

### P4: Build Memory And Context Router V2

Status: completed / pushed.

Goal: connect short-term memory, long-term memory, RAG, pinned context, compression, and prompt assembly.

Scope:

- backend-owned `ContextAssemblyManifest` parent record with included/omitted refs, token budget, policy decisions, hashes, bounds, retention metadata, and append-only guards;
- `AgentMemoryRecord` with org/agent/user/run scopes, owner user, provenance fields, lifecycle status, expiry/deletion, policy flags, and SQL-level eligibility filtering;
- deterministic `TokenEstimator` path with `cl100k_base` for known OpenAI-family models when available and `ceil(chars / 4)` fallback for unknown models;
- fixed pruning order: authority, pinned, recent window, attachments, long-term memory, compressed summary, RAG/web evidence;
- compressed-summary eligibility requiring current schema, allowed producer model, matching branch ID, and matching coverage path hash;
- `ModelCall.context_manifest_id -> ContextAssemblyManifest.id` binding with `ContextAssemblyManifest.prompt_manifest_id` as retrieval truth source;
- shadow/authoritative rollout through `settings.context_assembly_v2_enabled`;
- memory injection wrapper and low-trust policy flags for suspicious instruction-like memory;
- Run Detail/model-call context manifest projection and predictive frontend token-budget wording.

Verification evidence:

- `cd services/api-server && uv run pytest tests/test_context_router.py tests/test_agents.py tests/test_knowledge_rag.py tests/test_evals.py -q` -> `91 passed`.
- `cd services/api-server && uv run pytest tests -q` -> `260 passed`.
- `cd services/api-server && uv run ruff check app tests` -> passed.
- `DATABASE_URL=sqlite:////tmp/harness-p4-alembic.sqlite uv run alembic upgrade head` -> reached `20260517_0017`.
- `cd apps/agent-console && npm test` -> `139 passed`.
- `cd apps/agent-console && npm run lint` -> passed.
- `cd apps/agent-console && npm run build` -> passed.
- `python3 scripts/validate-docs.py` -> passed.
- `git diff --check` -> passed.
- Pushed to `origin/main` through `6c4a95d`.

### P5: Productize MCP And Skills

Status: completed / pushed.

Goal: make tools and skills manageable Harness capabilities, not hidden implementation details.

Delivered scope:

- unified `CapabilityRegistry -> AgentCapabilityAttachment -> CapabilityVersion -> ToolRunner`
  authority boundary;
- deterministic one-way backfill from legacy `Agent.tools_json` into attachments, with no union
  or intersection bridge at runtime;
- immutable capability versions, capability snapshots, and Run/ModelCall/ToolCall/Eval snapshot
  refs/hashes;
- agent-scoped Workspace chat, Agent Run, assignment, subagent, compatibility, and test-invocation
  execution paths;
- non-executing admin validation with secret redaction;
- agent-scoped executing test invocation through ToolRunner/ToolCall/EventStore;
- fail-closed ToolRunner behavior when no Agent capability attachment is supplied.
- no runtime lazy backfill from `Agent.tools_json`; migration/seed/test setup are the only
  allowed one-way backfill surfaces.

Verification evidence:

- `cd services/api-server && uv run pytest -q` -> `272 passed`.
- `cd services/api-server && uv run ruff check app tests alembic/versions/20260517_0018_create_capability_registry.py` -> passed.
- `cd services/api-server && DATABASE_URL=sqlite:////tmp/harness-p5-alembic.sqlite uv run alembic upgrade head` -> reached `20260517_0018`.
- Pushed to `origin/main` through `f05816e`.

Important boundary: `Agent.tools_json` remains visible as legacy registry/preset metadata and as
deterministic backfill input only. New runtime execution must resolve from enabled attachments.

2026-05-26 Knowledge connector follow-up:

- `/knowledge` now treats Dify and Coze as runtime-capable knowledge connectors
  rather than package installs or config-only cards; RAGFlow, Local Dify, and
  Local RAGFlow remain preview endpoint configuration.
- Coze uses the same safety boundary as Dify: frontend API Key values are saved
  as backend connector secrets, source responses expose only `secret_ref` plus
  configured status, connector config documents stay `connector_config_only`,
  and grounded answers require source-bound runtime retrieval hits.
- Coze runtime retrieval runs after local Knowledge/RAG insufficiency and before
  Dify/web fallback, producing `coze_connector` hits, `[C1]` citations,
  prompt-manifest source snapshots, and policy-audit evidence when the provider
  returns accepted records.
- Live local API smoke proved Coze configuration readiness and secret storage,
  and a Workspace chat runtime smoke against a local Coze-compatible retrieval
  endpoint returned `coze_connector` grounding with a `[C1]` citation. External
  Coze retrieval still depends on a real Coze credential, dataset ID, and
  compatible configured retrieval endpoint.

2026-05-26 UI follow-up:

- Tool Registry and Agent Studio MCP/Skill/Tool configuration now follows the
  console design rule that operational pages are scannable before editable.
- Preset capability enabling, trusted URL install, public URL preflight, Skill
  upload, package lifecycle, Agent-scoped test invoke, and Agent Studio
  capability attachment are opened from compact buttons into `ConfigDialog`
  modals instead of being visible inline by default.
- Frontend regression coverage asserts configuration fields are absent from the
  default page and present only inside the relevant dialog.

2026-05-27 runtime configuration follow-up:

- Installed MCPs now have a dedicated Chinese `/tools/config` page, also linked
  as `工具配置` in the sidebar and `运行配置` from Tool Registry.
- The page lists Agent-scoped installed MCPs with clear `已配置 / 未配置 / 缺少密钥`
  state, supports HTTP/SSE/stdio runtime fields, and provides a visible case
  test panel after saving.
- Runtime config is saved as a new immutable `CapabilityVersion`; raw API Keys
  are written only through server-side secret storage and are never returned in
  page/API payloads.
- Configured Brave Search uses the official
  `https://api.search.brave.com/res/v1/web/search` endpoint with
  `X-Subscription-Token`; unconfigured marketplace MCPs remain explicit Harness
  smoke outputs rather than fake live-provider results.

### P5/P4 Extension: Agent Context Optimizer Capability

Status: verified.

Goal: make token optimization pluggable at the Agent capability layer without
creating a separate runtime configuration system.

Delivered scope:

- `context_optimizer` Capability Package type with install, approval, simple
  install, and Agent attachment support for advanced lifecycle use;
- built-in Agent Studio Token Optimizer presets (`关闭`, `保守省 Token`,
  `均衡`, `强力省 Token`) so normal users can manually choose a plan without
  installing, uploading, or editing JSON packages;
- preset selection API that creates/reuses an internal built-in
  `context_optimizer` CapabilityVersion, disables previous optimizer
  attachments for the Agent, and enables exactly one selected preset;
- v1 declarative JSON-only optimizer contract with no arbitrary code execution;
- fail-closed install/runtime validation for unknown fields, secret refs,
  execution-shaped runtime fields, invalid ratios, invalid section limits,
  unsupported drop rules, and non-`budget_overlay` modes;
- priority-ordered optimizer attachment resolution in backend context assembly;
- conservative overlay merge for budget ratio and section limits;
- protected system/developer authority, pinned context, and current user goal;
- optimizer evidence in `ContextAssemblyManifest.token_budget_json`,
  included/omitted refs, model-call request audit, Run Detail, and
  Observability token summaries;
- Agent Studio Token 省用方案 selector and current preset status, with Tool
  Registry package-flow support retained for advanced users.
- Token 节省 page at `/token-savings`, backed by
  `GET /api/observability/token-savings`, so normal users can see total
  estimated saved tokens, actual prompt/total tokens, savings rate, active
  plan names, low-cost route evidence, cache counters, and recent run omit
  reasons without reading manifest/package details.
- Built-in multi-level context cache evidence for compression summaries, RAG
  retrieval, and long-term-memory candidates, persisted in
  `workspace_context_caches` and projected through
  `ContextAssemblyManifest.token_budget_json.context_cache`, Run Detail, and
  `/token-savings` per-source cache hit-rate cards.

Verification evidence:

- `cd services/api-server && uv run pytest tests/test_observability.py tests/test_context_router.py tests/test_tool_registry.py tests/test_agents.py -q` -> `116 passed`.
- Follow-up built-in preset validation: same backend target set -> `120 passed`.
- `cd services/api-server && uv run ruff check app tests` -> passed.
- `cd apps/agent-console && npm test -- AgentListPage.studio.test.tsx ToolRegistryPage.marketplace.test.tsx RunDetailPage.optimizer.test.tsx RunDetailPage.helpers.test.ts` -> `7 passed`.
- `cd apps/agent-console && npm run lint -- --pretty false` -> passed.
- `cd apps/agent-console && npm run build` -> passed with the existing Vite large-chunk warning.
- `python3 scripts/validate-docs.py` -> passed.
- `git diff --check` -> passed.
- Context cache follow-up: `cd services/api-server && uv run pytest tests/test_context_router.py tests/test_agents.py tests/test_observability.py tests/test_knowledge_rag.py -q` -> `144 passed`.
- Context cache follow-up: `cd services/api-server && uv run ruff check app tests alembic/versions/20260525_0021_create_workspace_context_caches.py` -> passed.
- Context cache follow-up: `cd services/api-server && DATABASE_URL=sqlite:////tmp/harness-cache-alembic.sqlite uv run alembic upgrade head` -> reached `20260525_0021`.
- Context cache follow-up: `cd apps/agent-console && npm test -- useChatStream.test.tsx TokenSavingsPage.test.tsx` -> `8 passed`.
- Detailed session record: [[session-2026-05-25-agent-knowledge-context-optimizer]].

### P6: Groundedness Eval And Observability

Status: completed and pushed through `83c8eee`.

Goal: make quality and hallucination control measurable.

Delivered scope:

- Eval-owned `GroundingTraceV1` contract and normalizer with stable failure reasons;
- deterministic citation selector, retrieval hit selector, required evidence, forbidden evidence, fallback, and unsupported marker checks;
- forbidden evidence leakage evaluated only by Eval against normalized retrieval, prompt manifest, citation, policy/audit, and model-call binding metadata inputs;
- no raw `ModelCall.request_json` or `ModelCall.response_json` scanning for forbidden leaks;
- grounding quality metrics in `EvalRun.metrics_json` and grounding deltas/gates in `RegressionDelta`;
- read-only `GET /api/observability/grounding-quality` projection over Eval-owned traces/metrics;
- Eval Harness metric/regression/failure display and Observability grounding-quality UI;
- Run Detail Eval Case save flow stores objective selectors only and does not infer required/forbidden snippets or unsupported markers.

Verification evidence:

- `cd services/api-server && uv run pytest tests/test_evals.py tests/test_eval_regression.py tests/test_observability.py -q` -> `36 passed`.
- `cd services/api-server && uv run ruff check app tests` -> passed.
- `cd apps/agent-console && npm run lint` -> passed.
- `cd apps/agent-console && npm run build` -> passed.
- `cd apps/agent-console && npm test` -> `147 passed`.
- Pushed to `origin/main` through `83c8eee`.
- Detailed P6 session record: [[session-2026-05-18-agent-knowledge-p6-groundedness-eval-observability]].

### P7: Release And Demo Hardening

Status: completed / pushed to `origin/p7-release-demo-hardening` through `a5d046b`.

Goal: preserve the private handoff quality while new capability layers grow.

Delivered scope:

- deterministic Knowledge/RAG demo seed through public APIs only;
- agent-scoped grounding support document so the demo question satisfies the backend `min_hits=2` local-grounding threshold;
- local fixture origin carried by seed names, `p7-seed-fixture:*` idempotency keys, and `seed-fixture://...` document URIs;
- service-level Knowledge/RAG migration/restore smoke for required tables and selector continuity;
- mocked release browser smoke covering Agent Studio knowledge, Workspace grounding, Run Detail knowledge evidence, Eval grounding metrics, and Observability grounding quality;
- updated deployment, troubleshooting, and web-research runbooks for seed/readback, migration/restore, browser smoke, and provider-boundary diagnosis.
- Chinese-first console UI follow-up:
  - shared accessible `MenuSelect` replaces native and bespoke selectors across model, knowledge, run, and settings surfaces;
  - keyboard selection, disabled-option skipping, grouping, and top/bottom placement are covered by a focused component test;
  - required English terms keep their original names with adjacent small Chinese explanations;
  - Agent Studio capability layout, Workspace selector/menu rows, Eval/Observability/Run Detail/Sandbox/Tool Registry terminology, and settings protocol selector were polished.
  - later 2026-05-27 follow-ups finished the remaining high-visibility `Agent / Leader` drift across Agent Studio, Knowledge, and Team surfaces, mapped visible `ACTIVE` badges to Chinese-first labels, and reran the 53-case Chromium regression after the focused headed browser checks.
  - the MCP / Skill store completion pass verified the beginner install flow end to end: explicit `未安装 / 待审批 / 待安装 / 已安装` chips, custom dialog/toast feedback instead of browser-native modals, null-safe installed-state detection for partial attachments, and concrete live cases for `mcp_context_search`, installed Brave MCP, and the `conservative-token-saver` Skill runtime context optimizer evidence.

Verification evidence:

- `python3 -m py_compile scripts/seed-knowledge-demo.py scripts/smoke-test-knowledge-migration-restore.py` -> passed.
- `python3 scripts/seed-knowledge-demo.py --print-plan` -> passed.
- `HARNESS_API_BASE_URL=http://127.0.0.1:18007 python3 scripts/seed-knowledge-demo.py --verify-readback --check-idempotent` -> passed against a temporary local API server.
- `python3 scripts/smoke-test-knowledge-migration-restore.py` -> passed.
- `cd services/api-server && uv run ruff check ../../scripts/seed-knowledge-demo.py ../../scripts/smoke-test-knowledge-migration-restore.py app tests` -> passed.
- `cd services/api-server && uv run pytest tests/test_knowledge_rag.py tests/test_agents.py tests/test_evals.py tests/test_eval_regression.py tests/test_observability.py -q` -> passed.
- `cd apps/agent-console && npm run lint` -> passed.
- `cd apps/agent-console && npm run build` -> passed.
- `cd apps/agent-console && npm test` -> passed.
- `cd apps/agent-console && npm run e2e:smoke:release` -> passed.
- `HARNESS_API_BASE_URL=http://127.0.0.1:18008 python3 scripts/seed-knowledge-demo.py --verify-readback --check-idempotent` -> passed on the non-default local API with `agent_grounding-evidence_document_id`.
- `POST /api/agents/default/runs/chat/stream` with the demo question on `http://127.0.0.1:18008` -> returned `knowledge_grounding: Local knowledge grounded the answer.`
- `docker compose --env-file deploy/docker-compose/.env.example -f deploy/docker-compose/docker-compose.yml config` -> passed.
- `python3 scripts/validate-docs.py` -> passed.
- `git diff --check` -> passed.
- Follow-up console UI validation: `cd apps/agent-console && npm run lint` -> passed.
- Follow-up console UI validation: `cd apps/agent-console && npm test` -> `30 files / 148 tests passed`.
- Follow-up console UI validation: `cd apps/agent-console && npm run build` -> passed.
- Follow-up console UI validation: `git diff --check` -> passed.
- Follow-up local service check: frontend `http://127.0.0.1:18082/` -> ok; API `http://127.0.0.1:8000/health` -> ok.
- Pushed branch `p7-release-demo-hardening` to `origin` through `a5d046b`.

### P8.2: Eval Dimensions v2 Refusal Safety Persona

Status: implemented locally on `p7-release-demo-hardening`.

Goal: make Eval judge model-behavior quality beyond tool/dialogue/cost success.

Delivered scope:

- optional `refusal_contract`, `safety_contract`, and `persona_contract` JSON sections in `EvalCase.expected_json`;
- deterministic graders for refusal calibration, overrefusal, safety marker/regex scans, tool-argument scanning, role drift, tone markers, first-person drift, and optional out-of-scope response markers;
- aggregate metrics and regression gates for refusal/safety/persona pass rates, safety violation deltas, overrefusal, and role drift;
- Eval UI metric cards, regression deltas, per-case badges, breakdown rows, and JSON preset buttons for the new contract dimensions.

Verification evidence:

- `cd services/api-server && uv run pytest tests/test_evals.py tests/test_eval_regression.py -q` -> `26 passed`.
- `cd services/api-server && uv run ruff check app tests` -> passed.
- `cd apps/agent-console && PATH="$HOME/.nvm/versions/node/v24.15.0/bin:$PATH" npm test -- EvalRunResults.contracts.test.tsx --run` -> `2 passed`.
- `cd apps/agent-console && PATH="$HOME/.nvm/versions/node/v24.15.0/bin:$PATH" npm run lint` -> passed.
- `cd apps/agent-console && PATH="$HOME/.nvm/versions/node/v24.15.0/bin:$PATH" npm run build` -> passed with the existing Vite large-chunk warning.
- `python3 scripts/validate-docs.py` -> passed.
- `git diff --check` -> passed.
- Detailed session record: [[session-2026-05-28-eval-dimensions-v2]].

### P8.3: Subagent Specialists v1

Status: implemented locally on `p7-release-demo-hardening`.

Goal: make subagents reusable Harness specialist contracts instead of anonymous async workers.

Delivered scope:

- `subagent_specialists` templates for role prompt, capability whitelist, output schema, trigger keywords, visibility, status, and per-specialist budget;
- seeded system specialists: `code-reviewer`, `researcher`, `safety-checker`, and `synthesizer`;
- `subagent_outputs` write-once structured output records with schema hash, budget consumed, and budget exceeded evidence;
- `AgentRun.specialist_id` plus context snapshots for specialist prompt, whitelist, output schema, schema hash, and budget;
- deterministic planner/executor routing through `recommended_specialist_slug` and trigger-keyword matching;
- worker budget and whitelist guards after model/tool calls, with `BUDGET_EXCEEDED` as terminal subagent status;
- parent task result aggregation of specialist output and budget evidence;
- Agent Console `专家库`, specialist detail/preflight, specialist filtering on `/subagents`, structured output/budget detail, plan-step specialist badges, and Run Detail `专家证据`.

Verification evidence:

- `cd services/api-server && uv run pytest tests/test_subagent_specialists.py tests/test_subagents.py -q` -> `20 passed`.
- `cd services/api-server && uv run pytest tests -q` -> `426 passed`.
- `cd services/api-server && uv run ruff check app tests` -> passed.
- SQLite Alembic upgrade to `20260528_0023` and downgrade to `20260527_0022` -> passed.
- `cd apps/agent-console && npm test -- SubagentSpecialistsPage SubagentDetailPage --run` -> `3 passed`.
- `cd apps/agent-console && npm run lint -- --pretty false` -> passed.
- `cd apps/agent-console && npm run build` -> passed with the existing Vite large-chunk warning.
- `python3 scripts/validate-docs.py` -> passed.
- `git diff --check` -> passed.
- Detailed session record: [[session-2026-05-28-subagent-specialists-v1]].

### P8.4: Subagent Specialists v2

Status: implemented locally on `p7-release-demo-hardening`.

Goal: make specialist orchestration parallel, bounded, measurable, and evaluable without schema churn.

Delivered scope:

- bounded fanout step contracts through `fanout_specialist_slugs` and `fanout_aggregation`;
- shared fanout metadata in `AgentRun.context_json`, including `fanout_batch_id`, `fanout_index`, and `fanout_total`;
- `SubagentManager.spawn_fanout(...)` with `MAX_FANOUT_PER_STEP=5`;
- nested specialist depth guard with `MAX_SPECIALIST_DEPTH=3`, `SubagentDepthExceededError`, HTTP 409 mapping, and `SUBAGENT_DEPTH_REJECTED` events;
- real-time specialist stats endpoint with `7d`, `30d`, and `all` windows;
- success-rate ranking for multi-candidate keyword matches, plus recency fallback trace metadata;
- Eval `specialist_contract` deterministic grader, aggregate metrics, role distribution, failure breakdown, and regression delta/gate support;
- fanout batch API and console projections for batch filters, sibling links, badges, grouped Run Detail evidence, specialist performance windows, and `专家契约` Eval preset.

Verification evidence:

- `cd services/api-server && uv run pytest tests/test_subagent_specialists.py tests/test_subagents.py tests/test_evals.py tests/test_eval_regression.py -q` -> `55 passed`.
- `cd services/api-server && uv run pytest -q` -> `435 passed`.
- `cd services/api-server && uv run ruff check app tests` -> passed.
- `cd apps/agent-console && npm test -- SubagentSpecialistsPage.test.tsx SubagentDetailPage.test.tsx EvalRunResults.contracts.test.tsx` -> `5 passed`.
- `cd apps/agent-console && npm run lint -- --pretty false` -> passed.
- `cd apps/agent-console && npm run build` -> passed with the existing Vite large-chunk warning.
- `cd apps/agent-console && npm test -- --run` -> `44 files / 214 tests passed`.
- `python3 scripts/validate-docs.py` -> passed.
- `git diff --check` -> passed.
- Detailed session record: [[session-2026-05-28-subagent-specialists-v2]].

### P8.5: Real Tool Adapters v1

Status: verified locally on `p7-release-demo-hardening`.

Goal: turn the Tool Registry and MCP-shaped runtime from marketplace smoke output into a real adapter boundary for common production collaboration tools.

Delivered scope:

- registry-backed adapter dispatch through `AdapterRegistry` and `MCPAdapter`;
- real read-only GitHub adapters for issues, pull requests, changed files, and code search;
- real read-only Slack adapters for message search, channel listing, and thread retrieval;
- sandbox file browser adapters for read/list/write/delete with workspace confinement and high-risk approval gates for writes/deletes;
- adapter introspection and rate-limited health endpoints;
- ToolCall capability snapshots with adapter version/module/source hash and input/output schema hashes;
- Tool Registry, Tool Configuration, and Run Detail UI evidence for health, schema, try-it execution, and adapter hashes.

Verification evidence:

- `cd services/api-server && .venv/bin/python -m pytest tests/test_adapter_registry.py tests/test_adapters_github.py tests/test_adapters_slack.py tests/test_adapters_sandbox_file.py tests/test_mcp_adapter.py tests/test_tool_runner.py tests/test_sandbox.py tests/test_warm_pool.py tests/test_tool_registry.py -q` -> `73 passed`.
- `cd services/api-server && .venv/bin/python -m pytest tests -q` -> `456 passed`.
- `cd services/api-server && .venv/bin/python -m ruff check app tests` -> passed.
- `cd apps/agent-console && npm test -- AdapterHealthBadge AdapterSchemaDrawer ToolRegistryPage ToolConfigurationPage RunDetailPage` -> `13 passed`.
- `cd apps/agent-console && npm test -- --run` -> `46 files / 219 tests passed`.
- `cd apps/agent-console && npm run lint -- --pretty false` -> passed.
- `cd apps/agent-console && npm run build` -> passed with the existing Vite large-chunk warning.
- `python3 scripts/validate-docs.py` -> passed.
- `git diff --check` -> passed.
- Detailed session record: [[session-2026-05-28-real-tool-adapters-v1]].

Important boundary: no migration files, new tables, or new dependencies were added. Real MCP protocol transports, OAuth, write-capable GitHub/Slack operations, Code Interpreter, and additional SaaS adapters remain future lanes.

### P8.6: Real Tool Adapters v2

Status: verified locally on `p7-release-demo-hardening`.

Goal: make installed MCP servers and common production tools executable through real protocol/provider adapters while preserving the existing capability, sandbox, approval, audit, and no-migration boundaries.

Delivered scope:

- minimal MCP JSON-RPC client/session/discovery with protocol version `2024-11-05`, HTTP/SSE response handling, and stdio transport that requires an injected sandbox executor plus in-sandbox initialize replay before target calls;
- `/api/tools/mcp-servers` list/discovery APIs that register discovered MCP child tools as Agent-attached org-scoped capabilities;
- Code Interpreter adapters for sandboxed Python execution and package installation, with denylist checks for dangerous imports/calls/dynamic lookup plus bounded stdio/file output;
- GitHub write tools for issue comments, issue creation, and pull request reviews;
- Slack write tools for posting messages and adding reactions;
- Notion search/page/database reads plus append-block writes;
- Linear issue/comment reads and writes;
- persistent 24h idempotency replay for non-idempotent tools using existing `SystemSetting` rows;
- Tool Registry UI panels for MCP server discovery and Code Interpreter test invocation.

Review fixes before completion:

- restored built-in capability registration to the global capability path after a duplicate visible capability regression exposed by full backend tests;
- made discovered MCP write-tool schemas require `idempotency_key`;
- added runtime `idempotency_key` enforcement in ToolRunner before non-idempotent MCP/adapter side effects, including approval request and approved-call paths.
- made Slack reaction and mutating discovered MCP tools high-risk/critical by default;
- tightened stdio runtime command config to a single executable name/path with safe args;
- replayed MCP initialize/initialized in the stdio sandbox process and tightened Code Interpreter bypass checks for `subprocess`, `importlib`, and `getattr`.

Verification evidence:

- `cd services/api-server && .venv/bin/python -m pytest tests/test_tool_runner.py tests/test_mcp_protocol_discovery.py tests/test_sandbox.py::test_tool_registry_matches_stage12_required_tools tests/test_adapters_code_interpreter.py -q` -> `24 passed`.
- `cd services/api-server && .venv/bin/python -m pytest tests -q` -> `487 passed`.
- `cd services/api-server && .venv/bin/python -m ruff check app tests` -> passed.
- `cd apps/agent-console && npm test -- src/features/tools/__tests__/ToolRegistryPage.marketplace.test.tsx src/features/tools/__tests__/ToolConfigurationPage.test.tsx src/features/tasks/__tests__/api.test.ts --run` -> `3 files / 11 tests passed`.
- `cd apps/agent-console && npm test -- src/features/teams/__tests__/TeamPages.test.tsx --run` -> `19 passed`.
- `cd apps/agent-console && npm test -- --run --pool forks --poolOptions.forks.singleFork` -> `47 files / 222 tests passed`.
- `cd apps/agent-console && npm test -- --run` -> failed on the unrelated TeamPages branch-switch flaky (`分支 1/2`) while the direct TeamPages file and single-fork full suite passed.
- `cd apps/agent-console && npm run lint -- --pretty false` -> passed.
- `cd apps/agent-console && npm run build` -> passed with the existing Vite large-chunk warning.
- `python3 scripts/validate-docs.py` -> passed.
- `git diff --check` -> passed.
- Detailed session record: [[session-2026-05-29-real-tool-adapters-v2]].

Important boundary: no migration files, new tables, or new dependencies were added. Stdio MCP is never launched from the host path; admin discovery rejects stdio without a run sandbox. Live external-provider smoke and live stdio MCP server smoke remain pending until safe credentials/fixtures are available. Default parallel frontend Vitest exposed an unrelated TeamPages branch-switch flaky, but targeted TeamPages and single-fork full frontend reruns passed.

### P8.7: Observability v1

Status: verified locally on `p7-release-demo-hardening`.

Goal: make private-deployment operations observable without adding an external observability stack requirement.

Delivered scope:

- real-time cost rollups for model calls, specialist budgets, and adapter tool costs by agent, provider, specialist, or adapter;
- local `otel_spans` storage with 90-day retention and trace list/detail APIs before Tempo/Event Store fallbacks;
- HTTP, model gateway, tool runner, subagent spawn/finalize, and eval grader spans;
- `alert_rules` and `alert_events` with four default in-app rules, org clone editing, evaluator worker, manual evaluation, SSE, and console bell;
- console pages for Cost, Trace, and Alerts, plus Run Detail trace links.

Verification evidence:

- `cd services/api-server && uv run ruff check app tests` -> passed.
- `cd services/api-server && uv run pytest tests/test_observability.py tests/test_observability_cost_rollup.py tests/test_observability_tracing.py tests/test_observability_alerts.py tests/test_evals.py tests/test_eval_regression.py -q` -> `60 passed`.
- `cd services/api-server && uv run pytest -q` -> `465 passed`.
- `cd services/api-server && DATABASE_URL=sqlite:////tmp/harness-observability-v1.sqlite uv run alembic upgrade head` -> passed through `20260529_0024`.
- `cd apps/agent-console && npm test -- ObservabilityV1Pages` -> `3 passed`.
- `cd apps/agent-console && npm test -- --run` -> `47 files / 222 tests passed`.
- `cd apps/agent-console && npm run lint -- --pretty false` -> passed.
- `cd apps/agent-console && npm run build` -> passed with the existing Vite large-chunk warning.
- `python3 scripts/validate-docs.py` -> passed.
- `git diff --check` -> passed.
- Detailed session record: [[session-2026-05-29-agent-knowledge-observability-v1]].

Important boundary: Observability projects Eval-owned grounding/regression evidence only; it does not recompute grounding quality. v1 stays in-app/local and does not add external alert channels, Jaeger/Grafana deployment requirements, cost enforcement, or SLO burn-rate automation.

### P8.8: Subagent Specialists v3

Status: verified locally on `p7-release-demo-hardening`.

Goal: make specialist orchestration smarter, shareable across orgs, and dynamically extensible while preserving v1/v2 specialist contracts.

Delivered scope:

- LLM-based specialist selection through `SpecialistLLMSelector`, using model-gateway JSON output, confidence thresholds, and fallback to keyword/success-rate/recency routing;
- persisted `specialist_selection_decisions` with selected slug, confidence, selector, candidates, alternatives, reasoning, trace, and task/step linkage;
- calibration API with confidence buckets, low-sample reporting, and ECE computed from same-task subagent outcomes;
- signed specialist marketplace listings with admin approval, manifest schema/budget validation, prompt blacklist scanning, capability allowlist checks, and org-local install copies;
- dynamic fanout extension with same-batch requester validation, running-batch guard, `MAX_DYNAMIC_FANOUT=10`, max 3 extensions per batch, max 1 extension per requester, and `FANOUT_EXTENDED` event evidence;
- Agent Console marketplace pages, calibration panel, dynamic fanout badges, and fanout extension history.

Review fixes before completion:

- changing a verified listing's manifest, signature, or version now resets `verified=false` and blocks install until admin reapproval;
- marketplace uninstall archives the installed specialist copy instead of hard deleting historical `AgentRun` / `SubagentOutput` FK targets;
- calibration run matching is scoped to the decision task ids, avoiding stale or abnormal context from another task influencing bucket scoring.

Verification evidence:

- `cd services/api-server && uv run pytest tests/test_subagent_marketplace.py tests/test_specialist_calibration.py tests/test_fanout_extend.py tests/test_specialist_llm_selector.py -q` -> `10 passed`.
- `cd services/api-server && uv run pytest tests -q` -> `497 passed`.
- `cd services/api-server && uv run ruff check app tests` -> passed.
- `cd services/api-server && DATABASE_URL=sqlite:////tmp/harness-subagent-specialists-v3.sqlite uv run alembic upgrade head` -> passed through `20260530_0025`.
- `cd apps/agent-console && npm test -- SubagentSpecialistsPage.test.tsx SubagentDetailPage.test.tsx SubagentMarketplacePage.test.tsx --run` -> `3 files / 4 tests passed`.
- `cd apps/agent-console && npm test -- src/features/teams/__tests__/TeamPages.test.tsx --run` -> `19 passed`.
- `cd apps/agent-console && npm test -- --run --pool forks --poolOptions.forks.singleFork` -> `48 files / 223 tests passed`.
- `cd apps/agent-console && npm run lint -- --pretty false` -> passed.
- `cd apps/agent-console && npm run build` -> passed with the existing Vite large-chunk warning.
- `python3 scripts/validate-docs.py` -> passed.
- `git diff --check` -> passed.
- Detailed session record: [[session-2026-05-29-subagent-specialists-v3]].

Important boundary: dynamic fanout currently uses existing authenticated API plus subagent path identity to enforce same-batch requester semantics; a separate subagent-runtime credential remains future hardening. `MARKETPLACE_INSTALLED` is reserved in the enum but not emitted through the task-scoped EventStore for org-scoped marketplace lifecycle.

### P8.9: Post-Audit Hardening v1

Status: verified locally on `p7-release-demo-hardening`.

Goal: close the non-blocking audit gaps left after Large File Refactor v1, Observability v1, Real Tool Adapters v2, and Subagent Specialists v3 without adding new product scope.

Delivered scope:

- patch migration `20260531_0026_widen_marketplace_ids.py` widens specialist marketplace decision/listing/installation ids and installation `listing_id` to `String(128)` while preserving unrelated task/team UUID widths;
- FastAPI startup registration now uses an async lifespan hook;
- built-in adapter registration is idempotent and available to import-only scripts through `ensure_builtin_adapters_registered` plus `python -m app.cli.registry_info`;
- Vite manual chunks split the console build into vendor and feature bundles; the main JS chunk is now 77.18 kB in the latest build;
- `agent_chat`, `agent_knowledge`, eval endpoint, and provider fallback code were split into smaller modules with compatibility re-exports;
- deployment runbook and `scripts/migration-preflight.sh` now require a PostgreSQL Alembic preflight for new migrations, with Docker-first and local-PostgreSQL fallback modes.

Review fixes before completion:

- code review found accidental out-of-scope widening of `TeamAgent.id` and `TeamMailboxMessage.id`; both were reverted to `String(36)`;
- follow-up code review returned APPROVE;
- architecture review returned WATCH only for route-level lazy loading and wildcard compatibility re-exports, both kept as v2 follow-ups under the PRD boundary.

Verification evidence:

- `cd services/api-server && .venv/bin/python -m pytest tests/test_teams.py tests/test_subagent_marketplace.py tests/test_specialist_calibration.py tests/test_adapter_registry.py -q` -> `44 passed`.
- `cd services/api-server && .venv/bin/python -m ruff check app tests` -> passed.
- `cd services/api-server && .venv/bin/python -m pytest tests -q` -> `500 passed`.
- `cd services/api-server && DATABASE_URL=sqlite:////tmp/harness-post-audit-hardening-after-review.sqlite .venv/bin/python -m alembic upgrade head` -> passed through `20260531_0026`.
- `bash scripts/migration-preflight.sh` -> passed through `20260531_0026` on PostgreSQL; Docker daemon was unavailable, so the script used local PostgreSQL binaries.
- `cd apps/agent-console && npm test -- --run --pool forks --poolOptions.forks.singleFork` -> `48 files / 223 tests passed`.
- `cd apps/agent-console && npm run lint -- --pretty false` -> passed.
- `cd apps/agent-console && npm run build` -> passed with 7 JavaScript chunks and main `index-*.js` at 77.18 kB.
- `python3 scripts/validate-docs.py` -> passed.
- `git diff --check` -> passed.
- Detailed session record: [[session-2026-05-29-post-audit-hardening-v1]].

Important boundary: this hardening slice does not implement route-level `React.lazy`, does not replace compatibility wildcard re-exports with explicit public APIs, and does not rewrite already-pushed history. `.omx/plans/_template.md` was updated locally for future commit-hygiene DoD, but `.omx/` is repository-ignored and remains an OMX planning artifact unless later promoted to a tracked docs path.

## Boundaries

- Do not reopen Stage 07. It is a completed foundation.
- Do not claim Agent Knowledge Harness completion from UI surfaces alone; each capability needs persisted records, runtime evidence, and tests.
- Do not add complex RBAC unless a later plan explicitly changes that boundary. Use existing agent/org isolation.
- Mock or deterministic retrieval helpers are acceptable for tests, but user-facing web research must require a real provider and policy gate.

## Related Pages

- [[project-handoff-current-state]]
- [[deep-interview-private-harness-chain]]
- [[agent-workspace-execution-evidence-architecture]]
- [[session-2026-05-14-workspace-execution-evidence]]
- [[session-2026-05-17-agent-knowledge-p3-web-research]]
- [[session-2026-05-17-agent-knowledge-p4-context-assembly]]
- [[session-2026-05-17-agent-knowledge-p5-capability-registry]]
- [[session-2026-05-28-subagent-specialists-v1]]
- [[session-2026-05-28-subagent-specialists-v2]]
- [[session-2026-05-29-subagent-specialists-v3]]
- [[session-2026-05-28-real-tool-adapters-v1]]
- [[session-2026-05-29-agent-knowledge-observability-v1]]
- [[session-2026-05-29-post-audit-hardening-v1]]
