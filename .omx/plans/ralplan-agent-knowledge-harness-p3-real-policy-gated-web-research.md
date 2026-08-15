# RALPLAN: Agent Knowledge Harness P3 Real Policy-Gated Web Research

Path: `.omx/plans/ralplan-agent-knowledge-harness-p3-real-policy-gated-web-research.md`

## Outcome

P3 交付一个 **真实、策略门控、可审计的 web research fallback**：当本地知识不足时，系统只在真实 provider 已配置且网络/域名/预算/审批策略通过后执行外部研究，并把结果作为可追溯 web source、retrieval hit、citation、prompt manifest、policy audit、Run event 和 Run Detail evidence 持久化。

P3 不交付通用爬虫平台、浏览器自动化抓取、企业级研究工作流、MCP/Skills 产品化、Memory Router V2、复杂 RBAC 或观测 dashboard。这些分别留给 P4/P5/P6/P7。

## Progress Baseline

P3 starts after:

- P1 is a verified baseline: `.omx/reports/agent-knowledge-harness-p1/p1-gate-result-20260516T211017Z.md`.
- P2 is completed in local progress docs: `docs/ai/task-progress.yaml` and `docs/task-progress.md`.
- Current code already has `WebResearchSource`, web-source retrieval hits/citations, web grounding metadata, Run Detail web-source display, and `WEB_RESEARCH_*` event types.
- Current fake fixture provider is intentionally non-verified: `grounding_provider=fake_web_fixture`, `fixture_grounded=true`, `verified_grounded=false`.

## RALPLAN-DR Summary

### Principles

1. **Real evidence boundary**: user-facing source-bound web grounding must come only from a configured real provider, never from the fake fixture path.
2. **Policy before network**: provider calls are denied by default until pre-call policy passes; provider-returned URLs are denied before persistence unless post-result policy passes.
3. **Snapshots over live recomputation**: Run Detail and Eval reconstruct web evidence from persisted snapshots, not fresh provider calls.
4. **Provider abstraction first**: P3 adds one production adapter behind a small interface, leaving room for Brave/Exa/etc. without hardwiring product logic to one vendor.
5. **Tests stay offline**: CI uses fake adapter responses and policy fixtures; live provider smoke is optional/manual and cannot gate normal tests.

### Decision Drivers

1. The roadmap says P3 is blocked on provider choice and must not mock real user evidence.
2. P2 closed local lifecycle/audit gaps, so P3 can focus on provider configuration, network safety, and verified-source semantics.
3. Existing code already contains the persistence and UI shape for web sources; the highest leverage is replacing fixture-only fallback with a real provider adapter and policy gate.

### Viable Options

| Option | Pros | Cons | Verdict |
| --- | --- | --- | --- |
| A. Adapter-first with Tavily as first production provider | Simple Search API, LLM-oriented snippets/raw content, include/exclude domains, time filters, request id/usage metadata | Vendor dependency; needs API key and budget controls | **Chosen** |
| B. Brave Search first | Independent index, AI/LLM-context oriented products, strong fit for search-only grounding | More product/API variants to choose; answer/grounding endpoints may overlap model-answer responsibility | Keep as second adapter candidate |
| C. Exa first | Strong AI-search/content/highlights APIs and deep research path | Broader capability than P3 needs; risk of widening into deep research | Keep as second adapter candidate for P3b/P6 |
| D. Generic HTTP crawler only | No search vendor dependency | Higher abuse/safety risk; weak relevance ranking; larger crawler/parser scope | Rejected for P3 |
| E. Keep fake fixture provider only | No credentials needed | Violates P3 target and roadmap; cannot claim source-bound real web grounding | Rejected |

External reference notes:

- Tavily Search exposes `/search`, ranked results, `include_raw_content`, `include_domains`, `exclude_domains`, `time_range`, `max_results`, `request_id`, and credit usage, which maps cleanly to bounded source snapshots and audit metadata: https://docs.tavily.com/documentation/api-reference/endpoint/search
- Brave Search API exposes web-search and AI grounding products, including web results/snippets and AI-oriented grounding endpoints; it remains a good later adapter candidate: https://brave.com/search/api/ and https://api-dashboard.search.brave.com/documentation/services/grounding
- Exa Search/Contents APIs expose search, clean content, highlights, context, and cost metadata; useful for later deep research or richer source extraction: https://docs.exa.ai/reference/search and https://exa.ai/docs/reference/contents-api-guide

## ADR

Decision: Implement P3 as a policy-gated web research adapter framework with **Tavily Search as the first production adapter**, while keeping the fake provider only as an explicit offline fixture.

Drivers:

- P3 needs real sources now, not a general crawler.
- Tavily’s result schema maps well to existing `WebResearchSource`, `RetrievalHit`, and `CitationRecord`.
- Existing persistence can absorb provider request ids, credits, URLs, snippets, raw-content hashes, and policy decisions without a broad schema rewrite.
- Tests can monkeypatch the adapter interface and avoid live network.

Alternatives considered:

- Brave first: viable, but better as a second adapter after the interface and policy model are stable.
- Exa first: viable, but the rich contents/deep research surface risks overscoping P3.
- Generic crawler: rejected because private-network blocking, robots/rate compliance, parsing, and abuse controls would dominate the slice.

Consequences:

- P3 completion requires a real provider configuration path and a live/manual smoke when credentials are available.
- Normal CI still uses fake provider fixtures, but fake evidence must never set `verified_grounded=true`.
- Provider-specific response fields stay in metadata; product contracts remain provider-neutral.
- P3 does **not** perform second-hop HTTP fetches of provider-returned URLs. It consumes bounded provider-returned title/url/snippet/metadata only. Any first-party crawler/fetcher, redirect handling, robots policy, DNS-rebinding defense, or page extraction belongs to a separate P4 crawler/fetcher security design.
- Tavily adapter defaults to `include_raw_content=false`. If a later implementation enables raw content, it may persist only a bounded excerpt plus hashes and must state that full original-page replay is not available unless a separate retention plan approves storing full content.

Architect review iteration:

- Split policy into pre-provider-call and post-result-ingestion stages because returned URLs are unknowable before a search provider responds.
- Extend or share the existing `PolicyEngine` network policy semantics instead of creating a parallel web research policy language.
- Resolve secrets through explicit config such as `TAVILY_API_KEY`, not arbitrary admin-provided environment variable names.

Security review hardening:

- Treat `verified_grounded` as legacy field wording only. In P3 docs/UI/Eval it means **real-source-bound**, not factual verification. It does not mean the source is true, the conclusion is correct, or the citation supports every claim.
- Provider-side include/exclude domain filters are advisory query constraints only. Authoritative enforcement happens in post-result policy before persistence or citation.
- Fake provider is allowed only in `test` / `development` or with explicit `ALLOW_FAKE_WEB_RESEARCH=1`. Production configuration with `provider=fake` must fail health checks or refuse runtime fallback.
- Runtime user-facing requests must not override the configured provider.
- Policy decisions must persist a safe policy snapshot so later Run Detail uses the historical decision context, not current settings.

Follow-ups:

- P3b may add Brave or Exa adapters after P3a passes.
- P6 should add unsupported-claim and citation-quality dashboards after real web evidence exists.

## Scope By Slice

### P3a: Provider Config And Adapter Boundary

Goal: make real provider availability explicit and safe before network execution.

Includes:

- `WEB_RESEARCH_PROVIDER_TAVILY` plus disabled/fake/tavily provider states.
- Provider settings stored through existing `SystemSetting` or admin settings, with API key from env/secret reference only.
- Adapter interface returning normalized `WebResearchResult` records: title, url, snippet/content, published/updated date when available, provider request id, provider score, content hash, usage/cost metadata.
- Provider health has two modes:
  - `local_config_only`: default, no network and no provider cost; returns `configured_no_live_check`, `missing_key`, `policy_disabled`, `fake_not_allowed`, or `not_supported_in_environment`.
  - `live_probe`: explicit admin action only, audited and rate-limited; uses a fixed low-risk query and can return `live_ok`, `live_failed`, `provider_error`, or `rate_limited`.
- Explicit fake fixture isolation: fake remains test/dev-only and always non-verified.

P3a completion claim: real provider can be configured and probed; no product claim that user fallback is complete yet.

### P3b: Policy Gate And Network Safety

Goal: deny unsafe external research before any provider call or result ingestion.

Includes:

- Default-deny web research when provider is disabled or policy is missing.
- Pre-call allowlist/denylist domain filters sent to the provider where supported. These are advisory provider query constraints, not the security boundary.
- Post-result URL policy that blocks non-http(s), localhost, private IP, loopback, link-local, multicast, reserved, `.local`, metadata service hostnames, and DNS resolutions to private ranges before any returned source is persisted or cited.
- Per-run limits: max web research calls per run, max results, timeout, max content bytes, and provider response metadata. P3 does not claim monthly credit-budget enforcement unless an atomic budget store and tests are added.
- Approval behavior: first pass uses admin-configured automatic allow for allowlisted domains; manual approval is recorded as follow-up unless existing approval infrastructure can be reused cheaply.
- `KnowledgePolicyAudit` rows for allowed, denied, blocked, omitted, provider-error, and budget/rate-limit outcomes.
- `WEB_RESEARCH_FAILED` events for policy/provider failures.
- `PolicyEngine` integration: P3 should extend `services/api-server/app/sandbox/policies.py` with a web-research-specific evaluator or extract a shared host/allowlist utility used by both sandbox network policy and web research policy. Do not implement a divergent hostname wildcard/private-network dialect in `knowledge.py`.

P3b completion claim: unsafe or unconfigured research fails closed and is visible in audit evidence.

### P3c: Real Web Fallback Runtime

Goal: when local evidence is insufficient and policy passes, execute real research and bind sources/citations.

Includes:

- `ground_query` switches from fake-only fallback to provider-neutral `run_web_research`.
- Real provider results create `WebResearchSource`, web `RetrievalHit`, `CitationRecord`, prompt manifest source snapshots, and web-source policy audit rows.
- `RetrievalSession.mode` becomes `web_fallback` only when actual web source rows are created after local evidence is insufficient. P3 does not introduce `hybrid` retrieval; combining partial local hits with web hits is a P4/P6 follow-up because it needs claim-level conflict and source-priority rules.
- Local attempted evidence is still diagnostically recorded when fallback triggers: `local_insufficient=true`, `local_hit_count`, `local_best_score`, and `fallback_trigger_reason`. These local attempted hits are not answer citations in P3.
- Real web sources set `grounding_provider=tavily_search` or provider-neutral `real_web_research`, `fixture_grounded=false`, `verified_grounded=true` only when source snapshots and citations bind successfully. This field means source-bound only, not factual verification.
- Provider failures preserve local-insufficient answer behavior and never fabricate citations.
- Deduplicate URLs within a retrieval session and store URL hash separately from display URL.

P3c completion claim: Workspace can use real provider fallback from insufficient local evidence and cite persisted web sources.

### P3d: Evidence Surfaces, Eval, Docs, And Release Gate

Goal: make P3 auditable and promotable without requiring live network in CI.

Includes:

- Run Detail distinguishes `fake_web_fixture`, `real_web_research`, `provider_error`, `policy_blocked`, accepted/omitted sources, source-bound status, citation count, policy decision, provider request id, timestamp, and partial-results warnings.
- Eval grounding contract rejects fixture evidence unless `allow_fixture_grounding=true`, and adds real-provider fixture tests for verified source-bound web grounding.
- Tests cover provider disabled, missing key, policy blocked, private target blocked, provider error, rate limit, real-adapter success via fake HTTP fixture, citation binding, and no-fabrication fallback.
- Deployment docs describe provider env vars/secrets, policy configuration, local disabled default, and manual live smoke.
- Progress docs must use one of the explicit promotion states defined below, so provider implementation is not confused with live external verification.

P3d completion claim: P3 has user-visible evidence, deterministic regression tests, and deployment/runbook handoff.

## Product Boundaries

Required for P3:

- one production web search adapter;
- provider config and health state;
- policy gate before provider calls;
- source snapshots and citation binding;
- insufficient-local-evidence behavior when provider is disabled/blocked/failing;
- Run Detail/Eval visibility for real vs fixture grounding;
- no first-party second-hop fetch of provider-returned URLs.

Out of scope:

- general-purpose crawler;
- first-party URL/page fetcher for provider-returned results;
- redirect following and page extraction;
- browser automation;
- PDF/doc extraction from arbitrary web pages;
- deep multi-hop research agent;
- paid-provider calls in CI;
- complex RBAC beyond current admin/engineer settings control;
- observability dashboard beyond existing Run Detail and events.

## P3 Hardening Contract

### No Second-Hop Fetch

P3 must not fetch provider-returned URLs from the Harness backend. It consumes provider-returned result fields only:

- title;
- URL;
- snippet or provider-provided bounded content;
- published/updated timestamp when present;
- rank/score/request id/usage metadata.

`include_raw_content=false` is the default adapter setting. If implementation later enables provider-returned raw content, the backend still must not fetch the URL itself; it may store only bounded excerpts and hashes. A first-party crawler/fetcher requires a separate P4 design covering DNS rebinding, CNAME/private resolution, IPv6 local/private ranges, credentials-in-URL rejection, redirects to private networks, IDN/punycode confusion, integer/octal IP forms, bracketed IPv6 variants, metadata aliases, and redirect-chain audit.

### Source-Bound Semantics

`verified_grounded=true` is retained only for compatibility with existing API/Eval fields. In P3 it means:

- provider is a real configured provider, not fake;
- returned source URL passed post-result policy;
- source snapshot was persisted;
- citation is bound to that persisted source.

It does **not** mean factual verification, truth, claim support, or correctness. UI and docs should prefer wording such as `real source bound` / `verified source-bound` and must not present this as fact verification.

### Query Privacy

P3 sends the minimum query needed for external research:

- send the user question or a minimized search query only;
- do not send local private document snippets, memory, tool outputs, secrets, or full prompt context to the provider;
- block or redact obvious secret patterns before provider calls;
- audit persisted query evidence as hash plus bounded redacted preview, not as unrestricted sensitive text unless a later privacy decision permits it.

## Policy Contract

P3 has two policy stages. This split is required because a search provider call can be policy-checked before execution, but individual result URLs are known only after the provider responds.

### Pre-Call Policy

Provider call is allowed only if all pre-call conditions are true:

- `provider != disabled`;
- provider is real, not `fake`, for user-facing source-bound web grounding;
- API key exists through an explicit allowlisted config field such as `TAVILY_API_KEY`;
- organization policy enables web research;
- query length and content pass bounded validation;
- query privacy validation confirms no local private document snippets, memory, tool outputs, secrets, or full prompt context are sent;
- requested include/exclude domains pass allowlist/denylist as advisory provider filters only;
- per-run result/time/byte/call limits are within configured maxima;
- per-run call limit is not exhausted. Monthly/provider credit budget is record-only in P3 unless a tested atomic budget store is added.

### Post-Result Policy

Each returned source is persisted or cited only if all post-result conditions are true:

- URL is parsed and normalized before policy, dedupe, hashing, and persistence;
- URL scheme is `http` or `https`;
- URL does not contain embedded username/password credentials;
- hostname passes the same wildcard allowlist/denylist semantics used by `PolicyEngine.evaluate_network_request`;
- DNS-resolved addresses are not localhost/private/link-local/metadata/reserved/multicast;
- URL is not a metadata-service hostname or `.local` host;
- normalized URL is not already present in the retrieval session;
- provider result content stays within byte and snippet limits;
- source status is `READY` only after policy acceptance and snapshot hashing succeed.

URL normalization order:

1. parse URL;
2. IDNA/punycode normalize and lower-case host;
3. reject credentials and unsupported schemes;
4. normalize default ports and path;
5. remove fragments unless needed for source identity;
6. compute normalized URL hash;
7. dedupe within retrieval session;
8. evaluate policy;
9. persist accepted source snapshot.

Provider-side include/exclude domains are advisory only. They may reduce provider result volume, but they are not an authoritative security decision.

Policy implementation requirement:

- Prefer extending `PolicyEngine` with `evaluate_web_research_pre_call` and `evaluate_web_research_result`, plus shared helpers for hostname parsing, wildcard allowlist, and private-address checks.
- P3 must not leave web research policy as a separate ad hoc helper if that duplicates sandbox network policy semantics.

Concrete call shape:

```python
PolicyEngine(session).evaluate_web_research_pre_call(
    organization_id=organization_id,
    run_id=run_id,
    provider=provider,
    query=query,
    include_domains=include_domains,
    exclude_domains=exclude_domains,
    max_results=max_results,
)

PolicyEngine(session).evaluate_web_research_result(
    organization_id=organization_id,
    run_id=run_id,
    provider=provider,
    url=url,
    content_bytes=content_bytes,
)
```

`run_id` is nullable because health/probe and future admin preview paths may not have a Run. Runtime Workspace fallback should pass the Agent Run id when available. These methods should read organization-scoped settings directly, not depend on a `Task` lookup the way `evaluate_network_request(task_id, url)` does today.

Failure modes:

- `provider_disabled`: no web call; local-insufficient path remains; write a `KnowledgePolicyAudit` row with safe metadata and do not emit `WEB_RESEARCH_FAILED` for automatic fallback unless the user explicitly requested web research.
- `provider_missing_key`: no web call; admin-visible health error; write a `KnowledgePolicyAudit` row and emit `WEB_RESEARCH_FAILED` for runtime fallback attempts because policy allowed research but execution was misconfigured.
- `policy_denied`: no web call for pre-call denial; audit row + `WEB_RESEARCH_FAILED`.
- `result_policy_denied`: omit that result with safe audit metadata; continue citing other allowed results.
- `all_results_denied`: emit `WEB_RESEARCH_FAILED`; no verified source-bound grounding.
- `partial_results`: allowed sources are persisted and cited; denied sources are audit-only and do not emit failed events.
- `provider_error` / `rate_limited` / `timeout`: no verified source-bound grounding; error audit row and local-insufficient answer. Include `retryable` where knowable and include timeout seconds for timeout events.

## Data And Snapshot Contract

Existing `WebResearchSource` can carry P3 data, but P3 should add typed columns or documented metadata keys for:

- provider name;
- provider request id;
- provider result id/rank/score;
- fetched/search timestamp;
- published/updated date when available;
- URL SHA-256;
- normalized URL;
- content/snippet SHA-256;
- raw content hash if raw content is stored;
- fixture flag;
- verified flag;
- policy decision id or policy snapshot id.

P3 should not store unbounded page content by default. Persist bounded snippet/content excerpts plus hashes first. Full extracted content requires a separate retention decision.

Provider metadata allowlist:

```json
{
  "request_id": "...",
  "response_time_ms": 123,
  "usage_credits": 1,
  "answer": null,
  "result_rank": 1,
  "result_score": 0.87,
  "raw_content_available": false
}
```

Do not persist the complete provider response JSON as metadata. Metadata must be bounded, redacted, and stable enough for UI/Eval use.

Policy snapshot minimum:

- provider;
- enabled;
- allow/deny domains;
- require_allowlist;
- max_results;
- timeout_seconds;
- max_content_bytes;
- max calls per run;
- decision reason;
- evaluator version;
- normalized hostname;
- resolved IP classification, without storing sensitive source content.

Run Detail must render the persisted policy snapshot and decision. It must not infer historical allow/deny reasons from current settings.

Exact selector rule:

```text
Run Detail and Eval with retrieval_session_id or prompt_manifest_id MUST render persisted web source snapshots.
They MUST NOT call the provider again.
```

## API / Configuration Contract

Preferred configuration keys:

```text
knowledge.web_research_provider.provider = disabled | fake | tavily
knowledge.web_research_provider.api_key_env = TAVILY_API_KEY
knowledge.web_research_policy.enabled = false | true
knowledge.web_research_policy.allow_domains = [...]
knowledge.web_research_policy.deny_domains = [...]
knowledge.web_research_policy.max_results = 2..5
knowledge.web_research_policy.timeout_seconds = 3..10
knowledge.web_research_policy.max_content_bytes = <= 120000
knowledge.web_research_policy.require_allowlist = true
```

Admin/settings API may expose read-only redacted health plus controlled updates. Do not return secret values.

Secret resolution rule:

- `api_key_env` is not arbitrary user input. It must be a provider-owned allowlist value, initially only `TAVILY_API_KEY`, resolved by `app/core/config.py` or a small allowlisted secret resolver.
- Admin APIs may toggle provider and policy settings, but must not choose arbitrary environment variable names or read back secret values.
- Production startup or health must reject `provider=fake` unless `ALLOW_FAKE_WEB_RESEARCH=1` is explicitly set.
- Runtime user-facing paths cannot accept request-level provider overrides.
- Eval defaults reject fake evidence unless `allow_fixture_grounding=true`.

## Execution Plan

### Phase 0: Baseline, Migration, And Guardrails

1. Confirm P2 local commits are present and note push gap if still ahead of `origin/main`.
2. Scan historical web/fake grounding rows and confirm old fake rows remain non-verified.
3. Add migration/backfill only if needed for new typed web-source/policy-snapshot fields.
4. Mark older ambiguous web evidence conservatively as non-verified or `legacy_grounding=true`.
5. Add/confirm tests that old Run Detail exact selectors still render.
6. Add/confirm tests that fake fixture evidence cannot become verified by default.
7. Add/confirm tests that provider disabled preserves local-insufficient behavior.

Acceptance:

- Current P1/P2 tests pass or a fresh validation gap is recorded.
- Fake fixture path remains non-verified.
- Historical Run Detail/Eval evidence still renders after any migration/backfill.

### Phase 1: Provider Interface, Fake Hardening, And Tavily Adapter

1. Add provider enum/setting semantics.
2. Harden fake provider availability by environment and `ALLOW_FAKE_WEB_RESEARCH`.
3. Add adapter interface and Tavily adapter using stdlib HTTP or existing project HTTP pattern.
4. Set Tavily defaults to `include_raw_content=false` and no backend second-hop fetch.
5. Normalize provider responses into bounded source records.
6. Add local-config health and explicit live probe without leaking credentials.
7. Add unit tests with monkeypatched HTTP responses.

Acceptance:

- Missing key, invalid provider, provider error, timeout, and success are tested.
- No live network is used in tests.
- Secret resolution accepts only `TAVILY_API_KEY` for the Tavily adapter and rejects arbitrary env-var names.
- Provider disabled and provider missing-key runtime paths both write `KnowledgePolicyAudit`; missing-key runtime fallback emits `WEB_RESEARCH_FAILED`, while disabled automatic fallback does not create noisy failure events.
- Fake provider is unavailable in production unless explicitly allowed.
- Local health does not perform network calls or consume provider credits; live probe is explicit, audited, and rate-limited.

### Phase 2: Policy Gate

1. Add web research policy setting and evaluator.
2. Extend `PolicyEngine` or shared policy helpers so web research and sandbox network policy use the same hostname wildcard/private-network semantics.
3. Implement pre-call policy with query minimization, secret-pattern block/redaction, provider-call limits, and advisory domain filters.
4. Implement post-result URL normalization and policy before accepting provider result URLs.
5. Persist safe policy snapshots for allowed/denied/blocked results.
6. Emit `WEB_RESEARCH_FAILED` according to the failure-mode table.

Acceptance:

- Private/localhost/metadata/non-http(s)/denylist cases are blocked.
- Allowlist success and wildcard suffix behavior are tested.
- Audit rows do not leak blocked source content.
- Denied pre-call emits audit + `WEB_RESEARCH_FAILED` and performs no provider call.
- Denied returned URLs are omitted with safe metadata and do not prevent allowed results from being cited.
- Mock adapter call count is exactly zero for provider disabled, missing key, query validation failure, and pre-call policy denial.
- Provider-side domain filters are tested as advisory only; post-result policy remains authoritative.

### Phase 3: Runtime Integration

1. Replace direct fake-only fallback branch with provider-neutral `run_web_research`.
2. Bind real web results to `WebResearchSource`, `RetrievalHit`, `CitationRecord`, prompt manifest, and event stream.
3. Preserve fake fixture only for explicit fixture mode.
4. Persist local-insufficient diagnostics without making weak local hits answer citations.
5. Update grounding outcome semantics for real vs fake vs none.
6. Ensure provider failures do not produce fake citations.

Acceptance:

- Real-adapter fixture success creates web sources/citations and `verified_grounded=true` only in the source-bound sense.
- Fake fixture remains `verified_grounded=false`.
- Provider failure leaves `verified_grounded=false` and explains insufficient evidence.
- Citation must bind to a `web_research_source_id` from the same retrieval session, source status `READY`, passed policy snapshot, and a persisted retrieval hit.
- Web claims without citations fail Eval.

### Phase 4: UI, Eval, Docs, Promotion

1. Update Run Detail labels for real provider, fixture, policy blocked, and provider error.
2. Show accepted/omitted source status, source-bound status, citation count, policy decision, timestamp, provider request id, and partial-results warnings.
3. Extend Eval grounding contract for real-provider source-bound fixture and unsupported web claims.
4. Add deployment/troubleshooting docs for provider setup, disabled defaults, fake restrictions, query privacy, and source-bound semantics.
5. Add optional manual live smoke script or documented command requiring `TAVILY_API_KEY`.
6. Update progress/wiki only after deterministic gates and live/manual evidence rules are satisfied.

Acceptance:

- Run Detail makes real vs fixture source status obvious.
- Eval rejects missing citation binding and fixture-as-real claims.
- Docs explain that disabled/missing provider keeps local-insufficient behavior.
- Docs distinguish `P3 implementation complete, live smoke not run` from `P3 live provider smoke verified`.

### Suggested Micro-Slices

Use these smaller implementation units if executing with `$team`:

1. P3a-1: configuration, health modes, secret resolver, and fake hardening.
2. P3a-2: Tavily adapter interface and offline adapter tests.
3. P3b-1: pre-call policy, query privacy, and provider-call-count tests.
4. P3b-2: post-result URL normalization/policy and policy snapshots.
5. P3c-1: web source persistence and local-insufficient diagnostics.
6. P3c-2: citation/prompt manifest binding and Eval failure cases.
7. P3d-1: Run Detail source-state UI.
8. P3d-2: docs, migration notes, and promotion evidence.

## Verification Commands

Backend:

```bash
cd services/api-server
uv run pytest tests/test_knowledge_rag.py tests/test_evals.py tests/test_agents.py -q
uv run pytest tests/test_settings.py tests/test_tool_runner.py -q
uv run ruff check app/api/agents.py app/api/schemas.py app/api/settings.py app/db/models.py app/knowledge.py app/core/config.py app/sandbox/policies.py app/knowledge_web.py tests/test_knowledge_rag.py tests/test_settings.py
DATABASE_URL=sqlite:///$TMPDIR/harness-p3-clean.db uv run alembic upgrade head
```

Frontend:

```bash
cd apps/agent-console
npm test -- RunDetailPage KnowledgeManagementPanel
npm run e2e:smoke:release -- --grep "Agent Studio|Run Detail"
npm run lint -- --pretty false
npm run build
```

Docs/hygiene:

```bash
python3 scripts/validate-docs.py
git diff --check
```

Private deployment when Docker is available:

```bash
docker compose --env-file deploy/docker-compose/.env.example -f deploy/docker-compose/docker-compose.yml config
python3 scripts/smoke-test-docker.py
python3 scripts/smoke-test-agent-run.py
```

Optional live provider smoke, only with explicit credential:

```bash
TAVILY_API_KEY=... HARNESS_ENABLE_LIVE_WEB_RESEARCH_SMOKE=1 uv run pytest tests/test_knowledge_rag.py -q -k live_web_research
```

## Promotion Rules

P3a may be marked complete when provider config, health, and adapter normalization pass offline tests.

P3b may be marked complete when policy denial/allowance and audit/event behavior pass offline tests.

P3c may be marked complete when real-provider fixture success binds web source snapshots, citations, prompt manifest, and verified source-bound semantics.

Full P3 may be promoted in `docs/ai/task-progress.yaml`, `docs/task-progress.md`, and wiki only when:

- fake evidence cannot be promoted to source-bound real web grounding;
- real provider adapter is implemented and policy-gated;
- deterministic backend/frontend/eval/docs gates pass;
- private compose smoke remains valid or a documented unavailable gap is recorded;
- progress status is explicitly one of:
  - `P3 implementation complete, live smoke not run`;
  - `P3 live provider smoke verified`.
- `hybrid` retrieval is not claimed in P3; any progress entry must describe only local-insufficient to web-fallback behavior.
- no progress entry may imply factual verification from `verified_grounded`; use source-bound language.

## Available Agent Types

- `explore`: current knowledge/web-source implementation mapping.
- `researcher`: official provider docs and API behavior.
- `dependency-expert`: provider comparison and adapter/vendor risk.
- `architect`: policy/data/event boundary review.
- `executor`: backend/frontend/doc implementation.
- `test-engineer`: offline provider fixtures, policy matrix, Eval contract, e2e smoke.
- `verifier`: completion evidence and fake-vs-real grounding claims.
- `code-reviewer`: final security and product-risk review.
- `writer`: deployment docs, wiki, and progress docs after gates pass.

Suggested reasoning:

- Architect / code-reviewer / verifier: high.
- Executor / test-engineer: medium.
- Explore: low.
- Researcher / dependency-expert: high when provider docs or vendor choice changes.

## Execution Handoff

Recommended sequential lane:

```text
$ralph implement P3a/P3b provider config, Tavily adapter, and web research policy gate from .omx/plans/ralplan-agent-knowledge-harness-p3-real-policy-gated-web-research.md
```

Recommended team lane after P3a interface is stable:

```text
$team implement P3 from .omx/plans/ralplan-agent-knowledge-harness-p3-real-policy-gated-web-research.md
```

Suggested team lanes:

1. Config/health/fake-hardening lane.
2. Tavily adapter/offline fixture lane.
3. Pre-call policy/query privacy lane.
4. Post-result URL policy/snapshot lane.
5. Runtime persistence/citation/Eval lane.
6. Run Detail/docs/deployment lane.
7. Verification/security review lane.

Goal-mode follow-up:

- `$ultragoal` is the default if P3 should become a durable goal ledger.
- `$ultragoal` + `$team` is appropriate after P3a adapter boundaries are stable.
