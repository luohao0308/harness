# Agent Knowledge Harness P6 Groundedness Eval And Observability Context

## Task Statement

Plan P6 based on current wiki task progress.

## Desired Outcome

Produce a consensus-ready P6 implementation plan that makes groundedness, citations, unsupported claims, retrieval quality, fallback correctness, and grounding observability measurable without reopening P1-P5 foundations.

## Known Facts / Evidence

- `omx_wiki/project-handoff-current-state.md` says the latest completed Agent Knowledge Harness lane is P5 MCP/Skills productization and the next planned lane is P6 Groundedness Eval and Observability.
- `omx_wiki/agent-knowledge-harness-roadmap.md` defines P6 scope as groundedness, citation coverage, unsupported-claim, retrieval precision, fallback correctness graders, Observability filters, and dashboards for token savings, retrieval cost, grounding quality, latency, and policy decisions.
- P1 already established prompt manifests, policy audit persistence, citation snapshots, exact grounding selectors, verified-vs-fixture grounding semantics, and Eval grounding contract checks.
- P3 already established real policy-gated web research evidence and fake-provider isolation.
- P4 already established backend-owned context assembly manifests, token-budget pruning, memory injection flags, and model-call context manifest binding.
- P5 is recorded as locally completed and verified: runtime capability authority flows through `CapabilityRegistry -> AgentCapabilityAttachment -> immutable CapabilityVersion -> ToolRunner`, and Run/ModelCall/ToolCall/Eval artifacts carry capability snapshot refs/hashes.
- `services/api-server/app/api/evals.py` already has Eval Dataset/Case/Run APIs, deterministic trace grading, grounding contract grading, aggregate metrics, baseline regression deltas, and Eval events.
- `services/api-server/app/api/observability.py` already has organization-scoped Observability summary, logs, traces, exports, Grafana dashboard listing, and service-health surfaces.
- `apps/agent-console/src/features/evals/pages/EvalHarnessPage.tsx` already renders datasets, cases, run history, regression gate, and trace-grader readiness.
- `apps/agent-console/src/features/observability/pages/ObservabilityPage.tsx` already renders runtime overview, log filters, trace filters, exports, health, recovery, and dashboard links.
- `apps/agent-console/src/features/runs/pages/RunDetailPage.tsx` already renders knowledge grounding evidence and saves exact grounding contracts into Eval Cases.

## Constraints

- Do not reopen Stage 07 or rewrite P1-P5 foundations.
- Preserve P1 append-only evidence semantics for prompt manifests, context manifests, and policy audits.
- Preserve P3 boundary: web research is source-bound provider evidence, not crawler/factual verification.
- Preserve P5 boundary: capability snapshots are immutable audit refs, not lazily recomputed runtime state.
- Keep P6 focused on Eval/Observability and hallucination-control measurement; defer release/demo seeded-data hardening to P7 unless minimal smoke evidence is needed.
- Use existing org/agent isolation, EventStore, Run Detail, Eval, and Observability patterns.
- No new external grader dependency unless an execution plan explicitly chooses one later; deterministic graders should be the first slice.

## Unknowns / Open Questions

- Whether unsupported-claim grading should remain deterministic from citation keys/claim annotations in P6, or introduce LLM-as-judge later.
- Whether P6 should persist claim-level records in a new table or keep all detail inside EvalResult/grader trace JSON for the first slice.
- Exact dashboard UX split between Eval Harness, Observability, Run Detail, and any future quality dashboard.
- How much token/cost attribution can be computed from existing manifests versus needing new counters.

## Likely Codebase Touchpoints

- Backend:
  - `services/api-server/app/api/evals.py`
  - `services/api-server/app/api/observability.py`
  - `services/api-server/app/api/metrics.py`
  - `services/api-server/app/observability/metrics.py`
  - `services/api-server/app/api/agents.py`
  - `services/api-server/app/api/schemas.py`
  - `services/api-server/app/db/models.py`
  - `services/api-server/app/knowledge.py`
  - Alembic migration under `services/api-server/alembic/versions/`
  - Tests: `services/api-server/tests/test_evals.py`, `test_knowledge_rag.py`, `test_agents.py`, plus focused observability tests if present or newly added
- Frontend:
  - `apps/agent-console/src/features/evals/pages/EvalHarnessPage.tsx`
  - `apps/agent-console/src/features/evals/components/EvalRunResults.tsx`
  - `apps/agent-console/src/features/evals/components/EvalCaseList.tsx`
  - `apps/agent-console/src/features/observability/pages/ObservabilityPage.tsx`
  - `apps/agent-console/src/features/runs/pages/RunDetailPage.tsx`
  - `apps/agent-console/src/features/tasks/api.ts`
- Docs/progress:
  - `docs/ai/task-progress.yaml`
  - `docs/task-progress.md`
  - `omx_wiki/agent-knowledge-harness-roadmap.md`
  - `omx_wiki/project-handoff-current-state.md`

## Planning Bias

Prefer a thin vertical P6 slice:

1. Extend deterministic Eval grading around existing grounding contracts before adding any LLM judge path.
2. Persist enough structured per-run/per-case quality evidence to support regression gates and Observability filters.
3. Add Observability aggregates and filters from existing retrieval, citation, manifest, policy, context, model-call, and Eval data.
4. Expose quality dashboards in existing Eval Harness and Observability surfaces, with Run Detail remaining the per-run evidence drilldown.
5. Verify with backend target tests, Alembic upgrade, frontend targeted tests, lint/build, and docs/progress updates.
