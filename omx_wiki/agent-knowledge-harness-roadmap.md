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

Status: completed.

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

Status: committed / pending push.

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

Important boundary: `Agent.tools_json` remains visible as legacy registry/preset metadata and as
deterministic backfill input only. New runtime execution must resolve from enabled attachments.

### P6: Groundedness Eval And Observability

Status: planned.

Goal: make quality and hallucination control measurable.

Scope:

- groundedness, citation coverage, unsupported-claim, retrieval precision, fallback correctness graders;
- Observability filters for retrieval sessions, citations, insufficient-evidence, fallback, and unsupported claims;
- dashboards for token savings, retrieval cost, grounding quality, latency, and policy decisions.

### P7: Release And Demo Hardening

Status: planned.

Goal: preserve the private handoff quality while new capability layers grow.

Scope:

- Docker Compose migration smoke for knowledge tables;
- one-command seeded demo data for Knowledge/RAG;
- browser release smoke covering Agent Studio knowledge, Workspace grounding, and Run Detail knowledge evidence;
- updated runbooks for backup/restore, provider configuration, and failure diagnosis.

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
