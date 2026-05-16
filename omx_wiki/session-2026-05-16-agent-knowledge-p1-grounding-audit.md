# Session 2026-05-16 Agent Knowledge P1 Grounding Audit

Category: `session-log`

Tags: `agent-knowledge-harness`, `rag`, `knowledge-grounding`, `prompt-manifest`, `policy-audit`, `eval`, `run-detail`, `cjk-retrieval`, `git`

## Summary

Agent Knowledge Harness P1 now has a pushed audit-gate implementation slice on `main`, but the outcome remains **auditable candidate / request changes**, not **verified baseline** and not fully P1 gate-ready.

The latest slice implements the executable parts of the reviewed Gate Matrix: model-call attempt binding, deterministic request hashing, exact Run Detail/Eval selectors, fallback metadata, bounded evidence snapshots, fake-web fallback audit fixtures, and regression coverage. A post-implementation `$code-review` found no critical security issue, but it returned **REQUEST CHANGES** with an architectural **BLOCK** because fixture/fake web grounding can still be interpreted as verified grounding and because policy isolation / DB integrity are not yet complete.

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

Manual local service URLs used for latest acceptance:

```text
API: http://127.0.0.1:18080/health
Agent Console: http://127.0.0.1:18082/
HTML report archive: http://127.0.0.1:18081/html-archive/
```

## Important Remaining Gaps

Do not mark P1 as verified baseline yet.

Remaining blockers after `$code-review`:

- **Fixture grounding versus verified grounding is not split.** Fake web fallback currently creates fixture evidence from the query and can satisfy `grounded` / Eval `require_grounded`. Before baseline, add explicit fields such as `grounding_provider`, `fixture_grounded`, and `verified_grounded`, and require Eval to opt into fixture grounding.
- **C10 policy isolation is still incomplete.** The audit path proves selected/omitted candidates but does not yet implement a real denied/redacted policy pass before prompt assembly. Add denied/redacted audit decisions, exclude or redact those candidates, and test forbidden content across hits, citations, manifests, audits, and model-call previews.
- **ModelCall binding is not DB-integrity protected.** Runtime validation exists, but `ModelCall.prompt_manifest_id` is still a nullable string, not a DB FK to `prompt_assembly_manifests.id`; `grounding_correlation_id` is also only a correlation string. Add FK/constraint or document the intentional boundary before verified baseline.
- **Request hash is not independently recomputable from persisted audit data.** The hash includes full message content while stored request JSON keeps previews/lengths. Persist ordered per-message hashes if independent audit recomputation is required.
- **Audit immutability is ORM-level only.** Ordinary SQLAlchemy update/delete paths are guarded, but DB triggers, RLS, or tamper-evident hashes are not present.
- **Frontend binding-chain display is partial.** Run Detail consumes grounding selectors, but the Model Call panel still needs stronger display/linking for `prompt_manifest_id`, `model_request_sha256`, `attempt_index`, and `terminal_status`.
- **Docker/private deployment compatibility for the new migration was not proven** in this environment because Docker was unavailable.

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
