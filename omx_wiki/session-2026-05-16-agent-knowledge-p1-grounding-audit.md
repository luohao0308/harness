# Session 2026-05-16 Agent Knowledge P1 Grounding Audit

Category: `session-log`

Tags: `agent-knowledge-harness`, `rag`, `knowledge-grounding`, `prompt-manifest`, `policy-audit`, `eval`, `run-detail`, `cjk-retrieval`, `git`

## Summary

Agent Knowledge Harness P1 moved from an unproven Knowledge/RAG candidate to a stronger auditable candidate, but it is still **not verified baseline** and still **not fully P1 gate-ready**.

Pushed commits on `main`:

```text
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

## Important Remaining Gaps

Do not mark P1 as verified baseline yet.

Remaining blockers:

- Prompt manifest is not yet immutably bound to the exact `ModelCall` request/message hash.
- Eval and Run Detail still use latest retrieval-session fallback for run-level lookup; multi-query exact evidence targeting needs stronger IDs.
- C10 policy audit currently proves selected/omitted retrieval candidates, not a full policy-engine isolation proof for denied/redacted content.
- Docker/private deployment compatibility for these new knowledge audit tables was not proven in this environment because Docker was unavailable.

## Frontend Acceptance Path

For a minimal local UI check:

1. Open the Agent Console at `http://127.0.0.1:15173/`.
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

## Related Pages

- [[project-handoff-current-state]]
- [[agent-knowledge-harness-roadmap]]
- [[local-dev-backend-port-cors]]
