# Session 2026-05-16 Agent Knowledge P1 Grounding Audit

Category: `session-log`

Tags: `agent-knowledge-harness`, `rag`, `knowledge-grounding`, `prompt-manifest`, `policy-audit`, `eval`, `run-detail`, `cjk-retrieval`, `git`

## Summary

Agent Knowledge Harness P1 now has a pushed blocker-repair slice on `main` through `4475eef`. The prior `$code-review` blockers for verified-vs-fixture grounding, denied/redacted isolation, DB binding integrity, independently recomputable request hashes, Run Detail binding display, and Eval grounding-contract propagation have been implemented and covered by targeted tests.

The current status is **P1 audit-gate blocker repair complete / pushed**, but still not a fully promoted **verified baseline** because Docker/private deployment smoke remains unproven in this environment and docs/task-progress promotion has not been performed.

Pushed commits on `main`:

```text
30e972b Add grounding audit binding fields
7881cab Persist grounded prompt assembly evidence
4034f9b Bind grounded prompts to model attempts
f087d45 Expose exact grounding selectors
7524df0 Cover grounding gate readiness paths
9bee19e Add knowledge audit persistence tables
aef447c Persist auditable knowledge grounding evidence
247beec Expose grounding audit contracts through APIs
f199069 Show grounding audit evidence in Run Detail
eefa906 Cover grounding audit gate regressions
1415bf6 Document P1 grounding audit status
801e710 Add grounding audit contract storage
d8a681f Persist safe grounding policy outcomes
52fbc3d Bind model calls to recomputable request hashes
baa0b4a Enforce exact grounding contracts through APIs
6d51898 Preserve grounding contracts in Run Detail
4475eef Cover grounding contract blocker regressions
```

## What Changed

- Added durable `prompt_assembly_manifests` and `knowledge_policy_audits` tables.
- Persisted prompt assembly evidence:
  - included retrieval hit IDs;
  - omitted candidates and omission reasons;
  - source snapshot metadata;
  - prompt evidence hash;
  - prompt section metadata.
- Persisted policy/omission audit rows:
  - `allowed`;
  - `omitted`;
  - `no_omission_applicable`.
- Added Run Detail API/UI exposure for prompt manifest and policy audit evidence.
- Added grounding Eval contract checks for manifest presence, policy decisions, sufficient retrieval, citation-hit inclusion, and forbidden-text leakage.
- Fixed local database migration failure by running Alembic to `20260516_0012`.
- Added model-call attempt-level audit binding:
  - `ModelCall.grounding_correlation_id`;
  - `ModelCall.prompt_manifest_id`;
  - `ModelCall.model_request_sha256`;
  - `ModelCall.attempt_index`;
  - `ModelCall.terminal_status`.
- Added `PromptAssemblyManifest.grounding_correlation_id`; the chosen binding pattern is shared correlation ID rather than manifest backfill after model execution.
- Added gateway validation before grounded `ModelCall` insertion:
  - prompt manifest exists;
  - manifest belongs to the run/task;
  - correlation ID matches;
  - retrieval evidence IDs match;
  - evidence text hash matches;
  - prompt manifest version matches;
  - model messages include the evidence message hash.
- Added retry / fallback / streaming terminal statuses so failed, successful, and stream-aborted attempts are explicit audit records.
- Added exact selector support:
  - Run Detail API accepts `retrieval_session_id` and `prompt_manifest_id`;
  - Run Detail UI consumes those selectors from URL query params;
  - Eval grounding contracts can target exact retrieval sessions or prompt manifests;
  - no-selector lookup marks `inferred_fallback=true` with `fallback_reason=latest_run_retrieval_session`.
- Added fake web fallback as an explicit fixture path only when `knowledge.web_research_provider=fake`; default remains no web provider.
- Tightened manifest/policy safety:
  - omitted candidates are hash/id/reason level only;
  - selected evidence retains bounded text snapshots / hashes for audit lifecycle;
  - `sanitize_audit_payload()` centralizes policy audit safe metadata;
  - ORM listeners reject ordinary `PromptAssemblyManifest` and `KnowledgePolicyAudit` update/delete paths.
- Fixed CJK fallback retrieval for small Chinese handbook content:
  - Chinese characters now tokenize for lexical fallback;
  - a single strong CJK match can be sufficient with `sufficiency_reason=single_cjk_strong_match`;
  - non-CJK single-hit evidence still cannot fake grounding below `min_hits`.
- Added explicit grounding outcome fields:
  - `grounding_provider`;
  - `fixture_grounded`;
  - `verified_grounded`;
  - `grounding_verification_reason`.
- Eval `require_grounded` now counts verified grounding by default and counts fake-web fixture grounding only with explicit `allow_fixture_grounding=true`.
- Added denied/redacted policy decisions before prompt assembly:
  - `DENY:` candidates are excluded from prompt evidence;
  - `REDACT:` candidates are redacted before snippets, citations, manifests, and Run Detail exposure;
  - redaction treats the marker as rest-of-line so secrets containing periods, URLs, or email-like tokens do not leak.
- Hardened `ModelCall.prompt_manifest_id` persistence through the 20260517 migration and runtime/API contract:
  - historical nullable/orphan values remain compatible;
  - v2 rows bind to prompt manifests through persisted IDs and grounding correlation.
- `model_request_sha256` v2 is recomputable from persisted ordered per-message hashes and generation metadata.
- v2 request audit JSON no longer persists raw request `content_preview`; it keeps role, content length, and content hash.
- Run Detail Model Calls now displays manifest ID, correlation ID, request hash, hash audit status, attempt index, terminal status, and message-hash aggregate.
- Run Detail "Save as Eval Case" now writes exact `grounding_contract` selectors from the displayed grounding evidence instead of saving only status.
- Citation normalization now recognizes `[Wn]` web citation keys and removes unsupported `[W999]`-style references.

## Validation Evidence

Backend validation run after the CJK retrieval fix:

```text
services/api-server/.venv/bin/python -m pytest tests/test_knowledge_rag.py -q
12 passed

services/api-server/.venv/bin/python -m pytest \
  tests/test_agents.py::test_agent_workspace_chat_stream_uses_selected_model_and_attachment_context \
  tests/test_agents.py::test_agent_workspace_chat_stream_rewrites_unbound_citation_keys \
  tests/test_evals.py::test_eval_run_grades_grounding_contract_cases -q
3 passed

services/api-server/.venv/bin/python -m ruff check \
  app/knowledge.py app/api/agents.py app/api/evals.py tests/test_knowledge_rag.py
All checks passed
```

Live local probe after hot reload:

```text
query = 看一下团队手册里写了什么
local_status = sufficient
grounded = True
hits = 1
citations = 1
reason = single_cjk_strong_match
```

Local dev services used during verification:

```text
Frontend UI: http://127.0.0.1:15173/
Backend API: http://127.0.0.1:18080/
```

Fresh verification after the latest pushed P1 gate slice:

```text
cd services/api-server && .venv/bin/python -m pytest tests -q
226 passed in 15.54s

cd services/api-server && .venv/bin/python -m ruff check app tests \
  alembic/versions/20260516_0013_add_grounding_model_call_binding.py
All checks passed

cd apps/agent-console && \
  PATH=/Users/luohao/.nvm/versions/node/v24.15.0/bin:$PATH \
  npm run lint -- --pretty false
tsc --noEmit passed

git diff --check
passed

git push origin main
d1fb051..7524df0  main -> main
```

Fresh verification after the 2026-05-17 blocker-repair slice:

```text
cd services/api-server && uv run ruff check \
  app/knowledge.py app/agents/model_gateway.py app/api/agents.py app/api/evals.py \
  app/api/schemas.py app/db/models.py tests/test_knowledge_rag.py \
  tests/test_evals.py tests/test_agents.py \
  alembic/versions/20260517_0014_harden_grounding_audit_contract.py
All checks passed

cd services/api-server && uv run pytest \
  tests/test_knowledge_rag.py tests/test_evals.py tests/test_agents.py -q
63 passed

cd apps/agent-console && npm run lint
tsc --noEmit passed

cd apps/agent-console && npm run test -- \
  src/features/tasks/components/__tests__/ModelCallPanel.render.test.tsx
1 passed

cd apps/agent-console && npm run e2e:smoke -- e2e/run-detail.smoke.spec.ts
14 passed

cd services/api-server && DATABASE_URL=sqlite:///$tmpdb uv run alembic upgrade head
passed through 20260517_0014

git push origin main
a3cbea0..4475eef  main -> main
```

Manual local service URLs used for latest acceptance:

```text
API: http://127.0.0.1:18080/health
Agent Console: http://127.0.0.1:18082/
HTML report archive: http://127.0.0.1:18081/html-archive/
```

## Important Remaining Gaps

Do not mark P1 as verified baseline until the remaining release-gate evidence is collected.

Prior `$code-review` blockers now repaired:

- fixture grounding is split from verified grounding and Eval fixture use is opt-in;
- denied/redacted policy isolation runs before prompt assembly and has forbidden-text regression coverage;
- prompt manifest/model-call binding has migration/runtime/API coverage;
- request hash v2 is recomputable from persisted ordered message hashes;
- raw request previews are removed from v2 request audit JSON;
- Run Detail displays the model-call binding chain;
- Run Detail-saved Eval cases preserve exact grounding selectors;
- `[Wn]` citation normalization is covered.

Remaining gaps:

- **Docker/private deployment compatibility for the new migration was not proven** in this environment because Docker was unavailable.
- **Audit immutability is still primarily ORM-level.** Ordinary SQLAlchemy update/delete paths are guarded, but DB triggers, RLS, or tamper-evident hashes remain a future hardening lane if verified baseline requires stronger append-only guarantees.
- **Task-progress promotion is not done.** `docs/ai/task-progress.yaml` and `docs/task-progress.md` should only be updated after the private deployment gate is rechecked.

## Frontend Acceptance Path

For a minimal local UI check on the latest running services:

1. Open the Agent Console at `http://127.0.0.1:18082/`.
2. Ensure `default` agent has a knowledge source named `团队手册` with content similar to `# 团队手册\n\n使用简洁、带引用的回答。`.
3. Ask:

```text
看一下团队手册里写了什么
```

Expected:

- answer no longer shows `Local knowledge is insufficient`;
- Run Detail `知识依据` shows sufficient grounding;
- Prompt assembly audit is present;
- policy/omission audit is present;
- retrieval hit and citation are present.
- Model Calls show manifest ID, correlation ID, request hash, hash audit status, attempt index, terminal status, and message-hash aggregate.
- Saving the Run as an Eval Case sends a `grounding_contract` with the displayed `retrieval_session_id` / `prompt_manifest_id`.

For exact selector acceptance:

1. Open a Run Detail route such as:

```text
http://127.0.0.1:18082/runs/<run_id>
```

2. In the `知识依据` / Grounding panel, record:

```text
retrieval_session_id
prompt_manifest_id
grounding_correlation_id
evidence_text_sha256
```

3. Reopen with exact retrieval selector:

```text
http://127.0.0.1:18082/runs/<run_id>?retrieval_session_id=<retrieval_session_id>
```

4. Reopen with exact manifest selector:

```text
http://127.0.0.1:18082/runs/<run_id>?prompt_manifest_id=<prompt_manifest_id>
```

Expected:

- default no-selector view may show `fallback latest_run_retrieval_session`;
- exact selector view should not be treated as inferred latest fallback;
- `selected_retrieval_session_id` / `selected_prompt_manifest_id` should match the URL target;
- conflicting retrieval and manifest selectors should fail with conflict rather than silently choose one.

## HTML Reports

Archived local HTML references:

- `.omx/reports/html-archive/20260516-knowledge-p1-gate-added-feature-map.html`
- `.omx/reports/html-archive/agent-knowledge-p1-repair-review-2026-05-16.html`
- `.omx/reports/html-archive/release-gate-handoff-diff-2026-05-14.html`

## Related Pages

- [[project-handoff-current-state]]
- [[agent-knowledge-harness-roadmap]]
- [[local-dev-backend-port-cors]]
