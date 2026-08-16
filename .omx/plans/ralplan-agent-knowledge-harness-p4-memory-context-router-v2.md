# RALPLAN: Agent Knowledge Harness P4 Memory And Context Router V2

Path: `.omx/plans/ralplan-agent-knowledge-harness-p4-memory-context-router-v2.md`

## Outcome

P4 交付一个 **后端拥有、可审计、可评估的 Memory and Context Router V2**：每次 Workspace chat / model call 的上下文选择由后端统一决策，并以持久化 manifest 记录短期分支/会话上下文、长期记忆、Pinned raw context、压缩摘要、附件摘要、RAG/web evidence、工具/Run observation、token budget 和 omitted reason。

P4 不交付 MCP/Skills 产品化、观测 dashboard、自动深度记忆抽取、完整 release/demo hardening、复杂 RBAC 或新的 web research provider。这些留给 P5/P6/P7 或后续 P4b。

## Progress Baseline

P4 starts after:

- `docs/task-progress.md` records **Completed: P3 Real Policy-Gated Web Research** with backend tests, Ruff, and Tavily live smoke evidence.
- `docs/ai/task-progress.yaml` records post-stage hardening `p3-real-policy-gated-web-research` as `live_provider_verified`.
- `omx_wiki/project-handoff-current-state.md` is stale and still says P3 is next planned work; P4 execution must refresh handoff/wiki before promotion.
- The current worktree is dirty with P3 changes. P4 execution must preserve those changes and must not revert unrelated local work.

Fresh planning context: `.omx/context/agent-knowledge-harness-p4-memory-context-router-v2-20260517T063103Z.md`.

## RALPLAN-DR Summary

### Principles

1. **Backend-owned assembly**: the backend, not frontend payload trimming, is authoritative for final model-input context selection.
2. **Memory as evidence, not authority**: memory and retrieved context are source material and must not outrank system/developer policy instructions.
3. **Lifecycle gates eligibility**: disabled, archived, deleted, expired, denied, redacted, or foreign-scope memory must not enter prompt assembly.
4. **Audit without raw prompt leakage**: persist hashes, refs, token estimates, bounded metadata, section metadata, and omission reasons; do not persist unrestricted raw prompt previews or inline memory text in manifests.
5. **Evolve existing surfaces**: P4 must extend existing `RunContextRouter`, task context endpoints, `ModelCall`, and grounding manifests instead of creating parallel routing systems.

### Decision Drivers

1. Current Workspace context is fragmented across client truncation, `_workspace_context_messages`, `ground_query`, `PromptAssemblyManifest`, and `ModelCall` audit bindings.
2. Existing `PromptAssemblyManifest` is retrieval-bound and requires `retrieval_session_id`, so it should not be overloaded as the parent model-input manifest.
3. `context_max_tokens` is currently a UI-side hint; P4 needs deterministic backend enforcement and auditable omissions.

### Viable Options

| Option | Pros | Cons | Verdict |
| --- | --- | --- | --- |
| A. Extend only `PromptAssemblyManifest` | Smallest schema change; reuses Run Detail knowledge evidence | Conflates retrieval evidence with full prompt/context assembly; breaks non-RAG context cases | Rejected |
| B. Add `ContextAssemblyManifest` as parent model-input manifest while preserving `PromptAssemblyManifest` as retrieval sub-manifest | Clean boundary for memory, pinned, compression, attachments, RAG/web, omissions, and token routing; preserves P1/P3 grounding contracts | New migration/API/test surface; must avoid audit sprawl | **Chosen** |
| C. Keep frontend-owned truncation and persist only model-call metadata | Fastest and least invasive | Backend cannot prove what was selected/omitted or enforce policy/token budget | Rejected |
| D. Create a brand-new context router separate from `RunContextRouter` | Clean greenfield service | Duplicates existing `/tasks/{id}/context` behavior and creates two router concepts | Rejected |

## ADR

Decision: Introduce an append-only `ContextAssemblyManifest` as the parent model-input assembly decision record, and evolve `services/api-server/app/agents/context_router.py::RunContextRouter` plus Workspace chat assembly into a `ContextAssemblyService` boundary. Keep `RunContextRouter` as the compatibility facade for existing `/api/tasks/{task_id}/context` and `/api/tasks/{task_id}/context/route`.

Drivers:

- P4 must audit complete model-input context, not just retrieval evidence.
- Existing `PromptAssemblyManifest` already has a clear retrieval/grounding contract and should stay focused.
- Existing task context routes and frontend types need additive compatibility, not a breaking replacement.
- Existing P1/P3 privacy contracts avoid raw request previews; P4 should preserve that posture.
- `ContextAssemblyManifest.prompt_manifest_id` is the source of truth for retrieval evidence linked to a context assembly. `ModelCall.prompt_manifest_id` remains a deprecated compatibility projection mirrored from the manifest path and must not diverge.

Alternatives considered:

- Extend `PromptAssemblyManifest`: rejected because it requires retrieval semantics and would overload RAG/web evidence with non-retrieval sections.
- Keep frontend-owned routing: rejected because `context_max_tokens` remains unenforced by the backend.
- Add a separate router: rejected because `RunContextRouter` already owns task context projection and model routing endpoints.

Why chosen:

- A parent context manifest gives a durable answer to “what context was selected, omitted, budgeted, and sent for this model call?”
- Required binding direction is `ModelCall.context_manifest_id -> ContextAssemblyManifest.id` (N:1). `ContextAssemblyManifest` does not hold `model_call_id`.
- `ContextAssemblyManifest.prompt_manifest_id` preserves existing grounding evidence without weakening the binding chain; `ModelCall.prompt_manifest_id` is retained as read-compatible mirrored metadata.
- Additive fields and compatibility facades reduce migration risk.

Consequences:

- P4 needs a migration, new models/schemas, and focused UI evidence surfaces.
- `ModelCall` gets nullable `context_manifest_id`; `prompt_manifest_id` remains for compatibility but is deprecated as an independent source of truth.
- Existing frontend truncation remains an optimization, not the source of truth.
- P4 uses feature flag / shadow mode to compare old and new assembly before defaulting behavior.
- Later P6 dashboards can consume the manifest without reinterpreting raw prompts.

Follow-ups:

- P4b may add richer automatic memory extraction after manual/lifecycle-gated memory is stable.
- P5 handles MCP/Skills capability packs.
- P6 handles groundedness/citation/unsupported-claim dashboards.
- P7 handles seeded demos and broader release hardening.

## Implementation Plan

### 0. Execution Gate: Preserve P3 State

Before editing:

- Inspect `git status --short` and identify P3 dirty files.
- Do not revert or overwrite P3 worktree changes.
- Treat `docs/task-progress.md` and `docs/ai/task-progress.yaml` as the current progress source for P3 completion.
- Refresh `omx_wiki/project-handoff-current-state.md` during the docs step so it no longer says P3 is next.

Likely touched only for docs/progress:

- `docs/task-progress.md`
- `docs/ai/task-progress.yaml`
- `omx_wiki/project-handoff-current-state.md`
- `omx_wiki/agent-knowledge-harness-roadmap.md`

Pre-execution evidence requirement:

- Save a dirty-worktree baseline to `.omx/context/p4-pre-execution-worktree.txt` using `git status --short` and `git diff --stat origin/main...` when `origin/main` is available.
- At completion, compare the final diff against that baseline and explicitly report which changes are P3 carry-forward versus P4 work.

### 1. Schema: Memory And Context Manifest

Likely files:

- `services/api-server/app/db/models.py`
- `services/api-server/alembic/versions/20260517_0017_*.py`
- `services/api-server/app/api/schemas.py`

Add:

- `LongTermMemory` or `AgentMemoryRecord`
  - `organization_id`, `agent_id`, `owner_user_id`, optional `run_id`, optional `message_id`
  - `scope`: `org | agent | user | run`
  - `source_type`: manual, run_summary, user_preference, decision, tool_observation, imported
  - provenance refs: source run/message/tool/retrieval IDs where applicable
  - content fields: canonical text, `content_sha256`, length, metadata, policy flags
  - lifecycle: active, disabled, archived, deleted, expired
  - `expires_at`, `deleted_at`, `created_by`, `updated_at`
  - policy metadata and eligibility fields
- `ContextAssemblyManifest`
  - append-only parent model-input assembly record
  - `organization_id`, `agent_id`, `run_id`; no `model_call_id`
  - optional `retrieval_session_id`, required-if-grounded `prompt_manifest_id`
  - nullable `context_manifest_id` on `ModelCall`; `ModelCall.context_manifest_id -> ContextAssemblyManifest.id` is the binding direction
  - active branch / leaf IDs when available
  - `token_budget_json`
  - ordered `sections_json`
  - `included_refs_json`
  - `omitted_refs_json`
  - `policy_decisions_json`
  - `context_text_sha256` or equivalent section-hash aggregate
  - `tombstoned_refs_json` for compliance tombstones
  - `tombstoned_at` when organization-level compliance deletion marks manifest refs
  - metadata with schema version
  - retention fields: `created_at`, `expires_at` or retention metadata

Manifest invariants:

- append-only: reject update/delete like `PromptAssemblyManifest` and `KnowledgePolicyAudit` using SQLAlchemy `before_update` / `before_delete` events that raise an explicit immutable-record error
- stable section order
- deterministic omission reasons
- no unrestricted raw prompt preview
- no inline memory text snippets in manifests; memory refs store `memory_id`, `content_sha256`, content length, lifecycle snapshot, and section metadata only
- non-memory snippets, if any, are bounded by `MAX_SNIPPET_CHARS = 240` and carry `metadata.truncated=true`
- section refs point to memory, conversation node IDs, attachments, retrieval hits, citations, tool calls, events, or compression summaries
- `MAX_SECTIONS_PER_MANIFEST = 64`
- `MAX_OMITTED_REFS_LOGGED = 128`
- retention default: `CONTEXT_MANIFEST_RETENTION_DAYS = 90`, configurable per deployment; add config/schema now even if the cleanup job is P4b

Database hardening:

- Add SQLAlchemy immutability tests that update/delete attempts raise.
- If the deployment uses DB roles, add migration-level `REVOKE UPDATE, DELETE ON context_assembly_manifests FROM app_role`; otherwise add or plan a database trigger equivalent.
- Add `(organization_id, created_at desc)` index. If the current Postgres migration patterns support declarative monthly partitioning, use `created_at` monthly partitions; otherwise defer partitioning but keep the index and retention config.

### 2. Service Boundary: ContextAssemblyService

Likely files:

- `services/api-server/app/agents/context_router.py`
- optional new module if it reduces complexity, but keep `RunContextRouter` as facade

Refactor:

- Introduce `ContextAssemblyService` as the internal boundary.
- Keep `RunContextRouter.build()` compatible for existing task context projection.
- Existing `GET /api/tasks/{task_id}/context` and `POST /api/tasks/{task_id}/context/route` remain valid.
- Add context manifest output additively to `RunContextResponse`.

Responsibilities:

- provide a `TokenEstimator` interface selected by `model_id`
  - default implementation: `tiktoken` `cl100k_base` when available
  - unknown/unsupported models: deterministic conservative `ceil(chars / 4)` fallback
  - tests assert selected estimator and fallback behavior
- assemble short-term working context from active branch/recent turns
- include pinned raw messages regardless of normal recency truncation, with overflow warnings
- include compressed summaries as lossy context with lower priority than pinned/recent raw messages
- include attachment summaries already supplied by the client, not arbitrary file reads
- retrieve eligible long-term memory records
- include RAG/web evidence by linking to existing `ground_query` result and `PromptAssemblyManifest`
- enforce backend `context_max_tokens`
- record included and omitted context sections with reasons

Token budget contract:

- Section priority for retention is fixed as:
  1. `system` / developer authority
  2. pinned raw messages
  3. recent window, dropping older entries before newer entries
  4. attachment summaries
  5. long-term memory, dropping lower-scored items first
  6. compressed summary
  7. RAG/web evidence, dropping lower-relevance items first
- Omission reason for budget pruning is `token_budget`.
- Unit tests must lock the above ordering, including overflow cases.
- Frontend token counts remain predictive; UI should label them as predicted and surface backend `omission_reason=token_budget` when pruning occurs.

Compression eligibility:

- A compressed summary is eligible only when `summary_schema_version` equals the current schema, producer model is in the allowlist for the selected org/model family, and branch/leaf identity matches the active branch path.
- Ineligible summaries are omitted with explicit reason: `compression_schema_mismatch`, `compression_model_not_allowed`, or `compression_branch_mismatch`.

Feature flag / rollout:

- Add org-scoped `settings.context_assembly_v2_enabled`.
- Off: old `_workspace_context_messages` path remains authoritative, but the service writes a shadow manifest with `mode=shadow`.
- On: `ContextAssemblyService` is authoritative and old path is kept only for fallback/debug comparison.
- Acceptance includes a shadow-mode sample comparison where included/omitted refs are identical or all differences are recorded with reasons.

### 3. Workspace Chat Integration

Likely files:

- `services/api-server/app/api/agents.py`
- `services/api-server/app/api/schemas.py`
- `services/api-server/tests/test_agents.py`
- `services/api-server/tests/test_context_router.py`

Change:

- Replace direct `_workspace_context_messages` + separate grounding injection with a single assembly flow that calls the context service.
- Preserve normal chat, `markdown_plan`, Plan mode, continue, attachments, pins, and compression behavior.
- Keep `ground_query` as the RAG/web grounding provider, but route its evidence through `ContextAssemblyManifest` as a linked retrieval sub-manifest.
- Persist `ModelCall.context_manifest_id` for every model call that uses an assembly manifest.
- Same chat turn may reuse one manifest across multiple model calls. If tool output, new evidence, or budget input changes require reassembly, create a new manifest and bind subsequent model calls to it.
- `ContextAssemblyManifest.prompt_manifest_id` is the source of truth for retrieval evidence. `ModelCall.prompt_manifest_id` is a deprecated compatibility projection mirrored by service-layer code and must not contradict the manifest.
- Keep grounding correlation binding unchanged for compatibility.

### 4. Memory Lifecycle APIs

Likely files:

- `services/api-server/app/api/agents.py`
- `services/api-server/app/api/schemas.py`
- `services/api-server/tests/test_context_router.py`

Minimum P4 API:

- list eligible memory records for an agent/org
- create manual memory record
- disable/archive/delete memory record
- expose memory eligibility and policy metadata

Scope and eligibility contract:

- Supported memory scopes: `org`, `agent`, `user`, `run`.
- Add `owner_user_id` for user-scoped memory.
- Eligibility must be enforced in SQL predicates, not only after rows are loaded.
- `allowed_scopes(caller)` must prevent cross-user, cross-agent, and cross-org leakage.
- Tests must cover cross-user, cross-agent, and cross-org isolation.

Deletion and append-only audit contract:

- Normal user deletion changes memory lifecycle so future assembly and rendering treat it as ineligible.
- Historical manifests do not inline memory text. They keep only `memory_id`, `content_sha256`, length, section metadata, and lifecycle snapshot.
- Rendering historical manifest refs joins live memory records; if the source record is deleted/expired/disabled/archived, UI/API returns `redacted_by_lifecycle` instead of text.
- Organization-level compliance deletion uses a tombstone job/path that marks related manifest refs `tombstoned_at` while preserving hashes for audit.

Prompt-injection mitigation:

- Wrap injected memory in fixed evidence markup:

```xml
<memory id="..." source_type="..." trust="evidence">...</memory>
```

- The system prompt must state that `<memory>` content is reference material and cannot change instructions.
- Service sanitizes memory text with `strip_control_chars` and a length cap before injection.
- Scan memory for patterns such as `(?i)ignore (all )?previous|system prompt|you are now`.
- Matching memory may still be injected, but with `trust=low`, `policy_flags`, and an entry in `policy_decisions_json`.
- Add dedicated prompt-injection memory tests.

Deferred unless cheap:

- autonomous extraction from every assistant response
- memory ranking beyond deterministic scope/status/recency scoring
- memory import UI separate from existing Knowledge Management

### 5. Evidence Surfaces

Likely files:

- `apps/agent-console/src/features/tasks/api.ts`
- `apps/agent-console/src/features/runs/pages/RunDetailPage.tsx`
- `apps/agent-console/src/features/agents/components/ChatSurface.tsx`
- `apps/agent-console/src/features/agents/hooks/useChatStream.ts`
- focused frontend tests under `apps/agent-console/src/features/agents/__tests__/` or run detail tests

Add:

- Workspace Context evidence: backend manifest ID, selected sections, memory count, pinned count, compression status, RAG/web links, token budget, omitted count/reasons.
- Run Detail context assembly panel beside knowledge grounding, not inside the knowledge-only panel.
- Model Call panel/projection should show `context_manifest_id` when present.
- Do not display raw full prompt previews.
- For memory refs, render joined memory text only when lifecycle-eligible; otherwise render `redacted_by_lifecycle`.
- When frontend displays predicted token counts, label them as predictions and show backend recount/omission evidence once returned.

### 6. Eval And Regression Contracts

Likely files:

- `services/api-server/tests/test_context_router.py`
- `services/api-server/tests/test_agents.py`
- `services/api-server/tests/test_knowledge_rag.py`
- `services/api-server/tests/test_evals.py`
- optionally `docs/evals/prompt-eval-cases.yaml`

Cover:

- backend token budget changes included/omitted sections deterministically
- exact section retention/drop order under token pressure
- `TokenEstimator` model selection and fallback behavior
- deleted/expired/disabled/archived/foreign memory is not assembled
- deleted memory in historical manifest renders as `redacted_by_lifecycle`
- compliance tombstone marks related manifest refs without deleting the manifest row
- memory scope isolation across user, agent, and organization
- memory prompt-injection flags and `trust=low` behavior
- pinned context outranks normal recent-window trimming
- compressed summary is included only when schema/model/path checks pass
- RAG/web evidence remains linked through existing `PromptAssemblyManifest`
- `ModelCall.context_manifest_id` binds to the manifest without weakening `prompt_manifest_id`
- `ContextAssemblyManifest.prompt_manifest_id` and mirrored `ModelCall.prompt_manifest_id` cannot diverge
- compatibility endpoints still return existing required fields
- golden response-shape snapshot for `GET /api/tasks/{task_id}/context`
- feature-flag off path writes `mode=shadow` manifests while preserving old behavior
- shadow mode records identical included/omitted refs or explicit diff reasons
- append-only update/delete attempts raise
- Run Detail exact manifest selectors work if added

### 7. Docs And Progress

Update at completion only after verification:

- `docs/task-progress.md`
- `docs/ai/task-progress.yaml`
- `omx_wiki/project-handoff-current-state.md`
- `omx_wiki/agent-knowledge-harness-roadmap.md`
- optional runbook note if memory deletion/backup behavior needs operator guidance

## Acceptance Criteria

- Every Workspace chat model request persists a context assembly manifest with stable section order, included refs, omitted refs, token budget, safe hashes/metadata, and deterministic omission reasons.
- `TokenEstimator` selection is deterministic: known models use configured tokenizer implementation, defaulting to `cl100k_base`; unknown models use conservative `ceil(chars / 4)` fallback.
- Backend `context_max_tokens` changes assembly behavior in a tested, deterministic way using the fixed section drop order.
- Existing `/api/tasks/{task_id}/context` and `/api/tasks/{task_id}/context/route` remain backwards compatible and gain only additive fields.
- `PromptAssemblyManifest` remains retrieval-focused; P1/P3 grounding and request-hash tests still pass.
- `ModelCall.context_manifest_id` is implemented and points to `ContextAssemblyManifest`; `ContextAssemblyManifest` does not hold `model_call_id`.
- `ContextAssemblyManifest.prompt_manifest_id` is the source of truth for retrieval evidence; `ModelCall.prompt_manifest_id` is a deprecated compatibility mirror and cannot contradict it.
- Long-term memory records support lifecycle status, deletion/expiry, provenance, policy metadata, scope, `owner_user_id`, and SQL-level eligibility filtering.
- Deleted, expired, disabled, archived, denied, redacted, foreign-scope, or cross-user memory never enters prompt assembly.
- Historical manifest rendering redacts deleted/ineligible memory as `redacted_by_lifecycle`; manifests do not inline memory text.
- Feature flag `settings.context_assembly_v2_enabled` supports old-path shadow mode and authoritative v2 mode.
- Append-only manifest update/delete attempts fail in tests.
- Manifest constants are enforced: `MAX_SNIPPET_CHARS = 240`, `MAX_SECTIONS_PER_MANIFEST = 64`, `MAX_OMITTED_REFS_LOGGED = 128`.
- Workspace and Run Detail show context assembly evidence beside knowledge grounding without exposing unrestricted raw prompt previews.
- P3 progress/handoff is not regressed; stale wiki language that says P3 is next is corrected before P4 promotion.

## Risks And Mitigations

- Risk: audit sprawl from a new manifest.
  - Mitigation: define `ContextAssemblyManifest` as parent model-input assembly only; keep `PromptAssemblyManifest` retrieval-only.
- Risk: breaking P1/P3 grounding chain.
  - Mitigation: add nullable `context_manifest_id`; do not weaken existing `prompt_manifest_id` foreign key semantics.
- Risk: prompt/privacy leakage.
  - Mitigation: manifests store hashes, refs, section metadata, token counts, and no inline memory text; non-memory snippets are capped at 240 chars.
- Risk: frontend and backend token estimates diverge.
  - Mitigation: backend is authoritative; frontend remains predictive/ergonomic and labels token counts as predicted.
- Risk: P3 dirty files conflict with P4 edits.
  - Mitigation: start execution with explicit worktree inspection, save `.omx/context/p4-pre-execution-worktree.txt`, and compare final diff.
- Risk: memory becomes prompt injection.
  - Mitigation: fixed `<memory trust=...>` wrapper, system-side warning, control-char stripping, length caps, injection-pattern policy flags, and `trust=low` handling.
- Risk: append-only manifests conflict with deletion/privacy requirements.
  - Mitigation: manifests do not inline memory text; lifecycle joins redact historical rendering; compliance tombstone marks refs while preserving hash audit.
- Risk: manifest table grows quickly.
  - Mitigation: retention config defaults to 90 days, add `(organization_id, created_at desc)` index, and use partitioning when supported by project migration patterns.

## Verification Plan

Backend targeted:

```bash
cd services/api-server
uv run pytest tests/test_context_router.py tests/test_agents.py tests/test_knowledge_rag.py tests/test_evals.py -q
uv run ruff check app tests
```

Required backend assertions:

- token estimator selection and fallback
- fixed section drop order
- `ModelCall.context_manifest_id` N:1 binding
- `ContextAssemblyManifest.prompt_manifest_id` truth-source mirror behavior
- append-only update/delete rejection
- memory lifecycle redaction and tombstone behavior
- SQL-level scope isolation for user/agent/org
- prompt-injection policy flags
- feature-flag shadow mode
- `GET /api/tasks/{task_id}/context` golden response shape

Migration:

```bash
cd services/api-server
uv run alembic upgrade head
```

If the repo keeps downgrade coverage for new migrations, also run the downgrade/upgrade pair for the P4 revision.

Frontend targeted:

```bash
cd apps/agent-console
npm test -- ChatSurface RunDetailPage
npm run lint
npm run build
```

Required frontend assertions:

- predicted token display is labeled as predictive/backend-recounted
- backend `omission_reason=token_budget` is visible when pruning occurs
- Run Detail renders context assembly as sibling evidence beside knowledge grounding
- deleted memory refs render `redacted_by_lifecycle`

Docs/hygiene:

```bash
python3 scripts/validate-docs.py
git diff --check
```

Optional if UI evidence changes are substantial:

```bash
cd apps/agent-console
npm run e2e:smoke:release
```

## Available Agent Types Roster

- `explore`: fast repo lookup and touchpoint mapping
- `architect`: boundary review for manifest/service/API compatibility
- `executor`: backend/frontend implementation
- `test-engineer`: regression and migration coverage
- `designer`: Workspace/Run Detail evidence surface review
- `code-reviewer`: final diff review
- `verifier`: completion evidence and claim validation
- `writer`: docs, wiki, progress, runbook updates

## Follow-Up Staffing Guidance

### Ralph Path

Recommended when one owner should preserve P3 dirty state and drive sequential verification.

Suggested lanes:

- `executor` / medium: schema, service, API, backend integration
- `test-engineer` / medium: backend tests, migration validation, frontend focused tests
- `designer` / high if UI gets complex: Workspace Context / Run Detail placement
- `verifier` / high: final evidence and no-regression review
- `writer` / high: progress/wiki/handoff updates

Launch hint:

```text
$ralph execute .omx/plans/ralplan-agent-knowledge-harness-p4-memory-context-router-v2.md
```

### Team Path

Recommended if parallel delivery is desired after P3 state is stabilized.

Suggested split:

- Lane 1 backend schema/service: `db/models.py`, Alembic, `context_router.py`
- Lane 2 chat/API integration: `api/agents.py`, `api/tasks.py`, `api/schemas.py`, backend tests
- Lane 3 frontend evidence: `tasks/api.ts`, `RunDetailPage.tsx`, Workspace context UI/tests
- Lane 4 docs/progress: progress docs and wiki handoff
- Lane 5 verification: targeted backend/frontend/doc gates

Launch hints:

```text
$team implement .omx/plans/ralplan-agent-knowledge-harness-p4-memory-context-router-v2.md
omx team --task ".omx/plans/ralplan-agent-knowledge-harness-p4-memory-context-router-v2.md"
```

Team verification path:

- Team must report changed files, tests run, migration status, frontend build status, docs validation, and remaining gaps.
- Ralph/verifier follow-up should run the final integrated gates and inspect manifest/privacy invariants before completion.

## Goal-Mode Follow-Up Suggestions

- `$ultragoal` is the default durable follow-up for P4 because this is implementation delivery with multiple verifiable checkpoints.
- `$ultragoal` + `$team` is suitable if parallel lanes are used while keeping a durable leader-owned ledger.
- `$autoresearch-goal` is not the default; P4 is not primarily a research project.
- `$performance-goal` is not the default; token optimization matters, but P4’s primary target is correctness/auditability rather than benchmark optimization.

## P4 Hardening Contract

This section is mandatory for execution and overrides any softer wording above.

- Token authority: backend owns final token counting through `TokenEstimator`; tests lock tokenizer selection, fallback, and section drop order.
- Manifest binding: `ModelCall.context_manifest_id -> ContextAssemblyManifest.id`; N model calls may share one manifest; reassembly creates a new manifest; `ContextAssemblyManifest` never holds `model_call_id`.
- Retrieval truth source: `ContextAssemblyManifest.prompt_manifest_id` is authoritative. `ModelCall.prompt_manifest_id` is deprecated compatibility metadata mirrored from the context manifest path.
- Memory privacy: manifests do not inline memory text. Historical rendering joins lifecycle-eligible memory or returns `redacted_by_lifecycle`.
- Memory scope: `scope = org | agent | user | run`; `owner_user_id` is required for user scope; SQL predicates enforce allowed scopes.
- Rollout: `settings.context_assembly_v2_enabled` gates authority. Off mode writes `mode=shadow` manifests and preserves old behavior.
- Immutability: SQLAlchemy events reject context manifest update/delete; DB-level revoke/trigger is used when available.
- Injection handling: memory is wrapped as evidence markup and policy-scanned; suspicious memory gets `trust=low`.
- Retention: default context manifest retention is 90 days, indexed by `(organization_id, created_at desc)`, with partitioning or cleanup hook prepared.
- Bounds: `MAX_SNIPPET_CHARS = 240`, `MAX_SECTIONS_PER_MANIFEST = 64`, `MAX_OMITTED_REFS_LOGGED = 128`.
- Compatibility: `/api/tasks/{task_id}/context` has golden response-shape coverage before and after refactor.

## Consensus Review Changelog

- Applied Architect iteration: changed direction from “new router service” to evolving existing `RunContextRouter` / task context routes into a `ContextAssemblyService`.
- Applied Architect boundary guidance: `ContextAssemblyManifest` is parent model-input assembly; `PromptAssemblyManifest` remains retrieval sub-manifest.
- Applied Critic improvements: added exact likely files, manifest invariants, concrete acceptance criteria, verification commands, P3 dirty-state gate, and Run Detail sibling evidence placement.
- Applied user hardening review: defined token authority, fixed manifest/model-call cardinality, resolved deletion vs append-only privacy, added memory scope SQL isolation, feature flag/shadow mode, retrieval truth source, immutability enforcement, injection wrapper, retention/indexing, bounded constants, golden compatibility tests, compression eligibility, frontend token UX, and P3 diff baseline capture.
- Final Architect verdict: `APPROVE`.
- Final Critic verdict: `APPROVE`.
