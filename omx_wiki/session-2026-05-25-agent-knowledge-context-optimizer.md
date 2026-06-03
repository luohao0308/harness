# Session 2026-05-25 Agent Knowledge Context Optimizer

Category: `session-log`

Tags: `agent-knowledge-harness`, `context-assembly`, `token-optimization`, `capability-registry`, `run-detail`, `observability`

## Summary

Agent-level pluggable token optimization is implemented as a `context_optimizer`
Capability Package type, with a normal-user path in Agent Studio that uses
built-in manual presets instead of package install/upload/JSON editing. The
runtime still reuses the existing Capability Package, CapabilityVersion, and
AgentCapabilityAttachment path instead of creating a separate configuration
surface.

The v1 plugin contract is declarative JSON only. No third-party optimizer code
is executed. Optimizers can overlay the backend context assembly strategy with
budget ratio, section limits, drop order, compressed-summary preference, and a
low-cost route hint.

## Implementation Points

- `context_optimizer` is now an allowed package/capability type for private
  package install, approval, simple install, and Agent attachment.
- Agent Studio exposes four built-in plans: `关闭`, `保守省 Token`, `均衡`,
  and `强力省 Token`.
- Selecting a plan calls `POST /api/agents/{agent_id}/token-optimizer` with a
  `preset_id`. The backend creates or reuses an internal built-in
  `context_optimizer` CapabilityVersion, disables previous optimizer
  attachments for that Agent, and enables the selected preset attachment.
- The user-facing preset list does not expose optimizer JSON. The advanced
  Capability Package install/upload path remains available for operators, but
  it is no longer the normal Token Optimizer setup path.
- Runtime validation fails closed for invalid optimizer manifests, including
  unknown top-level fields, unknown optimizer fields, secret refs, execution
  runtime fields, unsupported drop rules, invalid ratios, invalid section
  limits, and non-`budget_overlay` modes.
- `ContextAssemblyService` resolves enabled optimizer attachments for the Agent
  in attachment priority order and conservatively merges overlays.
- Protected context remains non-droppable: authority messages, pinned context,
  and the current user goal cannot be removed by optimizers.
- `ContextAssemblyManifest.token_budget_json` records `baseline_strategy`,
  `effective_strategy`, `optimizer_capability_version_ids`,
  `optimizer_policy_hash`, and `optimizer_decisions`.
- Included and omitted refs carry optimizer metadata and omit reasons when an
  optimizer affects a section.
- Model call request audit, Run Detail token optimization, and Observability
  token summaries project optimizer version/hash/decision evidence plus
  low-cost route reasons.
- Agent Studio displays a simple Token 省用方案 selector and current preset
  state. Tool Registry install flows still accept `context_optimizer` packages
  for advanced lifecycle use.
- Added a user-facing Token 节省 page at `/token-savings`. It reads a
  backend projection instead of raw manifests and shows estimated saved tokens,
  actual prompt/total tokens, savings rate, active built-in plan names, cache
  and low-cost route counters, and recent run rows with omit reasons.
- Added `GET /api/observability/token-savings`, which aggregates organization
  token optimization evidence and projects recent Run rows with `run_id`,
  `context_manifest_id`, estimated savings, actual token usage, optimizer
  labels, low-cost route reasons, and omission-reason counts.

## Context Cache Follow-Up

The cache-hit evidence gap is fixed by making context cache status flow through
the same context assembly manifest path instead of adding a side channel.

- `CompressedContext` and `AgentCompressedContext` now carry `cache_status`.
  Workspace chat sends `summary.cacheStatus` back to the backend, and
  compressed-summary sections record `cache_source: compression_summary`,
  `cache_status`, `cache_key_hash`, and `cache_reason`.
- Added DB-backed `workspace_context_caches` for restart-stable cache payloads.
  Cache keys are scoped by organization and source, with source-specific agent,
  branch/path, pinned, model/provider, knowledge snapshot, user, and memory
  high-water inputs.
- `/context/compress` checks server-side summary cache before model
  recomputation and persists recomputed summaries. Cache hits return
  `cache_status: accepted`; recomputation returns `cache_status: recomputed`.
- RAG retrieval caches local sufficient retrieval payloads by normalized query,
  retrieval settings, and knowledge snapshot hash. Cache hits still create new
  `RetrievalSession`, `RetrievalHit`, `CitationRecord`,
  `PromptAssemblyManifest`, and policy audit records so each Run remains
  independently auditable.
- Long-term memory assembly caches candidate memory section selection while
  preserving protected system/developer, pinned, and current-goal boundaries.
- `ContextAssemblyManifest.token_budget_json` keeps legacy `retrieval_cache`
  for compatibility and adds `context_cache.sources` for
  `compression_summary`, `rag_retrieval`, and `long_term_memory`, including
  hit/miss/stale counts, status counts, estimated saved tokens, reason, and
  key hash.
- Observability token-savings responses expose `cache_sources` in both summary
  and recent-run rows, while old manifests with only `retrieval_cache` still
  display safely.
- `/token-savings` now shows total cache hit rate, per-source cards for
  `摘要缓存`, `RAG 检索`, and `长期记忆`, dynamic token units, and per-run cache
  source labels. Empty or legacy cache evidence shows `0%` instead of implying
  a hit.
- Fixed the executable-tool boundary after a server error reported
  `capability version is not executable: bab4df7d-a68d-4d9e-a490-7c57c5bd5177-v1`.
  `context_optimizer` attachments now remain visible as Agent capabilities but
  are excluded from executable ToolRegistry/ToolRunner resolution and snapshots.
- Fixed the zero-savings behavior observed on `default` workspace chats after
  enabling `均衡`. The root cause was that `max_candidate_tokens_ratio` was
  compared only with the large configured context window budget, so short and
  medium chats stayed under budget and no pruning occurred. The optimizer
  budget now applies the ratio to the current candidate context token count,
  then caps it by the requested window budget.

## Verification

```text
cd services/api-server && uv run pytest tests/test_observability.py tests/test_context_router.py tests/test_tool_registry.py tests/test_agents.py -q -> 116 passed
cd services/api-server && uv run ruff check app tests -> passed
cd apps/agent-console && npm test -- AgentListPage.studio.test.tsx ToolRegistryPage.marketplace.test.tsx RunDetailPage.optimizer.test.tsx RunDetailPage.helpers.test.ts -> 7 passed
cd apps/agent-console && npm run lint -- --pretty false -> passed
cd apps/agent-console && npm run build -> passed
python3 scripts/validate-docs.py -> passed
git diff --check -> passed
```

Frontend build completed with the existing Vite large-chunk warning.

Follow-up validation after replacing the normal setup path with built-in manual
presets:

```text
cd services/api-server && uv run pytest tests/test_agents.py -q -> 54 passed
cd services/api-server && uv run pytest tests/test_observability.py tests/test_context_router.py tests/test_tool_registry.py tests/test_agents.py -q -> 120 passed
cd services/api-server && uv run ruff check app tests -> passed
cd apps/agent-console && npm test -- AgentListPage.studio.test.tsx -> 2 passed
cd apps/agent-console && npm test -- AgentListPage.studio.test.tsx ToolRegistryPage.marketplace.test.tsx RunDetailPage.optimizer.test.tsx RunDetailPage.helpers.test.ts -> 7 passed
cd apps/agent-console && npm run lint -- --pretty false -> passed
cd apps/agent-console && npm run build -> passed with the existing Vite large-chunk warning
python3 scripts/validate-docs.py -> passed
git diff --check -> passed
```

Bugfix validation for non-executable optimizer attachments:

```text
cd services/api-server && uv run pytest tests/test_tool_registry.py::test_context_optimizer_package_installs_and_attaches_without_tool_execution tests/test_tool_runner.py::test_tool_runner_executes_read_file_and_writes_audit -q -> 2 passed
cd services/api-server && uv run pytest tests/test_tool_registry.py tests/test_tool_runner.py tests/test_agents.py tests/test_context_router.py -q -> 108 passed
cd services/api-server && uv run ruff check app tests -> passed
```

Bugfix validation for optimizer ratio over current candidate context:

```text
cd services/api-server && uv run pytest tests/test_context_router.py::test_context_optimizer_ratio_limits_candidate_context_even_under_window_budget tests/test_context_router.py::test_agent_context_optimizer_records_manifest_evidence_and_protects_required_context -q -> 2 passed
cd services/api-server && uv run pytest tests/test_context_router.py tests/test_observability.py tests/test_agents.py -q -> 98 passed
cd services/api-server && uv run ruff check app tests -> passed
git diff --check -> passed
```

Live local smoke on the running services after restart:

```text
POST /api/agents/default/runs/chat/stream -> run 16be7fb1-e16c-427d-90a9-a48d78fdd439
context_manifest_id: 14b9e391-9771-42af-abc9-84001e7379c7
optimizer_labels: 均衡
estimated_candidate_tokens: 4014
estimated_included_tokens: 3070
estimated_saved_tokens: 944
estimated_savings_percent: 23.52
omission_reasons: optimizer_budget x2
low_cost_route: balanced summarization under budget
```

Browser smoke confirmed `http://127.0.0.1:5173/agents/default/workspace`
loads, the sidebar contains `Token 节省`, and
`http://127.0.0.1:5173/token-savings` shows `均衡`, `944 tokens`, and
`预算裁剪` with no browser console errors.

Follow-up UI polish for the Token 节省 page:

```text
cd apps/agent-console && npm test -- TokenSavingsPage.test.tsx -> 1 passed
cd apps/agent-console && npm run lint -- --pretty false -> passed
git diff --check -> passed
Playwright 1440x900 /token-savings smoke -> loaded, cache hit rate shown, saved-token data shown, overflowX 0, consoleErrors []
Playwright 390x844 /token-savings smoke -> loaded, cache hit rate shown, overflowX 0, consoleErrors []
```

The page now uses a cleaner card layout matching the supplied reference:
a large `总 Token` card with input/output totals, compact KPI cards for
estimated savings, actual prompt tokens, savings rate, and cache hit rate, plus
secondary cards for candidate context, pruned runs, cache hit/miss counts, and
low-cost routing. Recent run rows also show per-run cache hit rate and hit/miss
counts.

Follow-up polish compressed the KPI area further after browser review. Token
values now use dynamic compact units (`944`, `19.44K`, `76.78K`, `126.78K`,
and future `M`/`B` values) instead of fixed `tokens` suffixes, and the first
metrics section measured about 108px tall at a 2048px-wide viewport.

```text
cd apps/agent-console && npm test -- TokenSavingsPage.test.tsx -> 1 passed
cd apps/agent-console && npm run lint -- --pretty false -> passed
Playwright 2048x1165 /token-savings smoke -> total 126.78K, prompt 76.78K, candidate 19.44K, saved 944, topSectionHeight 108, overflowX 0, consoleErrors []
Playwright 390x844 /token-savings smoke -> total 126.78K, cache hit rate shown, overflowX 0, consoleErrors []
python3 scripts/validate-docs.py -> passed
git diff --check -> passed
```

Follow-up validation after adding built-in multi-level context caches:

```text
cd services/api-server && uv run pytest tests/test_context_router.py::test_compressed_summary_cache_status_flows_into_context_manifest tests/test_agents.py::test_agent_workspace_context_compression_uses_server_cache tests/test_observability.py::test_observability_summary_projects_token_optimization_evidence tests/test_observability.py::test_token_savings_page_projects_recent_run_evidence tests/test_knowledge_rag.py::test_rag_cache_reuses_hits_with_new_retrieval_session -q -> 5 passed
cd services/api-server && uv run pytest tests/test_context_router.py tests/test_agents.py tests/test_observability.py tests/test_knowledge_rag.py -q -> 144 passed
cd services/api-server && uv run ruff check app tests alembic/versions/20260525_0021_create_workspace_context_caches.py -> passed
cd services/api-server && DATABASE_URL=sqlite:////tmp/harness-cache-alembic.sqlite uv run alembic upgrade head -> reached 20260525_0021
cd apps/agent-console && npm test -- useChatStream.test.tsx TokenSavingsPage.test.tsx -> 8 passed
cd apps/agent-console && npm run lint -- --pretty false -> passed
cd apps/agent-console && npm run build -> passed with existing Vite large-chunk warning
python3 scripts/validate-docs.py -> passed
git diff --check -> passed
```

Runtime cache-hit fix after live testing:

```text
cd services/api-server && uv run pytest tests/test_context_router.py::test_compressed_summary_cache_status_flows_into_context_manifest tests/test_agents.py::test_agent_workspace_context_compression_uses_server_cache tests/test_agents.py::test_agent_workspace_context_compression_cache_survives_session_close tests/test_observability.py::test_observability_summary_projects_token_optimization_evidence tests/test_observability.py::test_token_savings_page_projects_recent_run_evidence tests/test_knowledge_rag.py::test_rag_cache_reuses_hits_with_new_retrieval_session -q -> 6 passed
cd services/api-server && uv run ruff check app/api/agents.py app/api/observability.py tests/test_agents.py tests/test_observability.py -> passed
cd services/api-server && python3 -m py_compile app/api/observability.py app/api/agents.py -> passed
cd apps/agent-console && npm test -- ChatSurface.shell.test.tsx TokenSavingsPage.test.tsx -> 17 passed
cd apps/agent-console && npm run lint -- --pretty false -> passed
cd apps/agent-console && npm run build -> passed with the existing Vite large-chunk warning
python3 scripts/validate-docs.py -> passed
git diff --check -> passed
```

The live miss root cause was that `/context/compress` recorded
`workspace_context_caches` rows with `session.flush()` only. The FastAPI request
session closed without a commit, so summary-cache rows were rolled back after
the response and the next identical compression recomputed. Cache writes,
existing-summary accepted writes, and cache hit-count updates now commit before
returning. A regression test simulates the request boundary by rolling back the
test session between two identical compression calls; the second call still
returns `cache_status: accepted` and the mocked compression model is called only
once.

`/api/observability/token-savings` now also merges active
`workspace_context_caches` rows for the current organization into the summary,
so `/token-savings` can show pure `/compress` cache hits immediately instead
of waiting for a later chat run to create a context manifest. Recent Run rows
remain based on manifest evidence only.

Agent Workspace compression feedback was made visible again: the summary
refresh icon spins while pending and the composer area shows
`正在压缩上下文...` until the summary is ready.

Live verification after restarting services:

```text
API: http://127.0.0.1:8000
Console: http://127.0.0.1:5173
GET /health -> {"status":"ok","service":"api-server"}
GET /agents/default/workspace -> HTTP 200
POST /api/agents/default/context/compress same payload #1 -> cache_status recomputed
POST /api/agents/default/context/compress same payload #2 -> cache_status accepted
GET /api/observability/token-savings -> total cache hits 2, misses 11, stale 0
compression_summary -> hits 2, misses 5, hit_rate 28.57
```

Playwright browser smoke loaded `http://127.0.0.1:5173/agents/default/workspace`
and `http://127.0.0.1:5173/token-savings`, found `缓存命中率` with `2 / 11`,
`摘要缓存` with `28.57%` and `2 / 5`, plus `RAG 检索` and `长期记忆`, and
reported no browser console errors.

Follow-up validation after adding the Token 节省 page:

```text
cd services/api-server && uv run pytest tests/test_observability.py -q -> 22 passed
cd services/api-server && uv run pytest tests/test_observability.py tests/test_context_router.py tests/test_agents.py -q -> 97 passed
cd services/api-server && uv run ruff check app tests -> passed
cd apps/agent-console && npm test -- TokenSavingsPage.test.tsx -> 1 passed
cd apps/agent-console && npm test -- TokenSavingsPage.test.tsx RunDetailPage.optimizer.test.tsx AgentListPage.studio.test.tsx -> 4 passed
cd apps/agent-console && npm run lint -- --pretty false -> passed
cd apps/agent-console && npm run build -> passed with the existing Vite large-chunk warning
python3 scripts/validate-docs.py -> passed
git diff --check -> passed
```

Local service restart after this page:

```text
API: http://127.0.0.1:8000
Console: http://127.0.0.1:5173
```

Follow-up hardening for long-term memory cache hit rates:

```text
cd services/api-server && uv run pytest tests/test_context_router.py::test_long_term_memory_cache_reuses_candidates_across_runs tests/test_context_router.py::test_long_term_memory_cache_invalidates_after_memory_lifecycle_change tests/test_context_router.py::test_memory_scope_filtering_happens_in_query tests/test_context_router.py::test_memory_injection_flags_low_trust -q -> 4 passed
cd services/api-server && uv run pytest tests/test_context_router.py tests/test_observability.py tests/test_knowledge_rag.py::test_rag_cache_reuses_hits_with_new_retrieval_session tests/test_agents.py::test_agent_workspace_context_compression_uses_server_cache tests/test_agents.py::test_agent_workspace_context_compression_cache_survives_session_close -q -> 50 passed
cd services/api-server && uv run ruff check app/agents/context_router.py app/api/schemas.py tests/test_context_router.py -> passed
cd apps/agent-console && npm test -- useChatStream.test.tsx TokenSavingsPage.test.tsx -> 8 passed
cd apps/agent-console && npm run lint -- --pretty false -> passed
cd apps/agent-console && npm run build -> passed with the existing Vite large-chunk warning
```

The long-term memory cache key no longer includes `run_id` for stable
org/agent/user memory candidates. That was the remaining reason long-term
memory cache evidence could keep missing across normal Workspace runs. The key
is now based on organization, agent, user, scope policy, memory high-water
evidence, and a memory snapshot hash. Run-scoped memory bypasses cache reuse so
single-run context cannot leak into another run.

The context manifest cache summary now deduplicates one cache event per
`cache_source` / `cache_status` / `cache_key_hash`, so multiple memory sections
do not inflate the same hit or miss. Empty memory candidate sets also avoid
writing cache evidence, keeping `/token-savings` at `0%` when there is no memory
data instead of showing an artificial miss.

Compressed-summary chat payloads now carry estimated original and summary
token counts. `ContextAssemblyService` records the delta as
`cache_estimated_saved_tokens` for `compression_summary`, so per-run
`context_cache.sources` can show estimated saved tokens from the actual chat
manifest rather than only from DB aggregate rows.

Live restart and browser smoke:

```text
tmux session: harness-dev-cache
API: http://127.0.0.1:8000
Console: http://127.0.0.1:5173
GET /health -> {"status":"ok","service":"api-server"}
HEAD /token-savings -> HTTP 200
GET /api/observability/token-savings -> summary includes compression_summary, rag_retrieval, long_term_memory
Playwright 1440x900 /token-savings -> 缓存命中率, 摘要缓存, RAG 检索, 长期记忆, 预计节省 visible; overflowX 0; consoleErrors []
```

Follow-up hardening for server-authoritative summary cache:

```text
cd services/api-server && uv run pytest tests/test_agents.py::test_agent_workspace_context_compression_uses_server_cache tests/test_agents.py::test_agent_workspace_context_compression_does_not_trust_client_summary tests/test_agents.py::test_agent_workspace_context_compression_server_cache_ignores_stale_client_hint tests/test_agents.py::test_agent_workspace_context_compression_cache_survives_session_close tests/test_context_router.py::test_compressed_summary_cache_status_flows_into_context_manifest tests/test_knowledge_rag.py::test_rag_cache_reuses_hits_with_new_retrieval_session tests/test_observability.py::test_token_savings_page_projects_recent_run_evidence -q -> 7 passed
cd services/api-server && uv run pytest tests/test_context_router.py tests/test_observability.py tests/test_knowledge_rag.py::test_rag_cache_reuses_hits_with_new_retrieval_session tests/test_agents.py::test_agent_workspace_context_compression_uses_server_cache tests/test_agents.py::test_agent_workspace_context_compression_does_not_trust_client_summary tests/test_agents.py::test_agent_workspace_context_compression_server_cache_ignores_stale_client_hint tests/test_agents.py::test_agent_workspace_context_compression_cache_survives_session_close -q -> 52 passed
cd services/api-server && uv run ruff check app/api/agents.py app/api/observability.py app/agents/context_router.py app/knowledge.py app/api/schemas.py app/db/models.py tests/test_agents.py tests/test_context_router.py tests/test_observability.py tests/test_knowledge_rag.py alembic/versions/20260525_0021_create_workspace_context_caches.py -> passed
cd services/api-server && DATABASE_URL=sqlite:////tmp/harness-cache-alembic-latest.sqlite uv run alembic upgrade head -> reached 20260525_0021
cd apps/agent-console && npm test -- useChatStream.test.tsx TokenSavingsPage.test.tsx -> 8 passed
cd apps/agent-console && npm run lint -- --pretty false -> passed
cd apps/agent-console && npm run build -> passed with the existing Vite large-chunk warning
```

`/context/compress` no longer treats a client-provided `existing_summary` as a
trusted accepted cache entry. The client summary remains a compatibility hint
for request shape, but only a DB-backed `workspace_context_caches` row can
produce `cache_status: accepted`. Server cache lookup now runs before client
hint rejection, so an already persisted server summary still wins when the
submitted client hint is stale or has a mismatched prior coverage hash.

Live restart and smoke after the hardening:

```text
tmux session: harness-dev-cache
API: http://127.0.0.1:8000 via uvicorn --reload
Console: http://127.0.0.1:5173
GET /health -> {"status":"ok","service":"api-server"}
HEAD /token-savings -> HTTP 200
POST /api/agents/default/context/compress same payload #1 -> cache_status recomputed
POST /api/agents/default/context/compress same payload #2 -> cache_status accepted
POST /api/agents/default/context/compress with fake existing_summary and bad prior_coverage_path_hash -> cache_status accepted, server cached summary returned
GET /api/observability/token-savings -> total cache hits 5, misses 13, compression_summary hit_rate 41.67%
```

## Boundaries

- v1 optimizers do not execute arbitrary code.
- Optimizers cannot rewrite original user content.
- Optimizers cannot remove system/developer authority, pinned context, or the
  current user goal.
- Workspace and Team Mode keep using the existing context ring, `/compress`,
  Run Detail evidence, and capability attachment model; no separate optimizer
  configuration page was added.
- Normal users should use Agent Studio presets. Package install/upload remains
  an advanced/operator capability lifecycle surface, not the default Token
  Optimizer UX.
