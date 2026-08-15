# Agent Knowledge Harness P7 Release And Demo Hardening Context

## Task Statement

Plan P7 based on current wiki task progress.

## Desired Outcome

Produce a consensus-ready P7 implementation plan that hardens private release and demo validation for the completed Agent Knowledge Harness layers, especially Knowledge/RAG, Workspace grounding, Run Detail evidence, Eval grounding quality, Observability, and Docker Compose handoff.

## Known Facts / Evidence

- `omx_wiki/project-handoff-current-state.md` says Agent Knowledge Harness P6 groundedness Eval and Observability is completed and pushed, and the next planned lane is P7 Release And Demo Hardening.
- `omx_wiki/agent-knowledge-harness-roadmap.md` defines P7 scope as Docker Compose migration smoke for knowledge tables, one-command seeded demo data for Knowledge/RAG, browser release smoke covering Agent Studio knowledge, Workspace grounding, and Run Detail knowledge evidence, plus runbook updates for backup/restore, provider configuration, and failure diagnosis.
- `docs/ai/task-progress.yaml` records P6 as `eval_owned_grounding_quality_verified`, with backend Eval/Observability tests, ruff, frontend lint/build, and frontend tests passing.
- `docs/task-progress.md` records P6 as completed on 2026-05-18 and documents Eval-owned grounding quality, Observability read-only projection, and Run Detail objective-selector save behavior.
- Existing release validation already includes `apps/agent-console` `e2e:smoke:release`, `scripts/validate-harness-flow.sh`, `scripts/smoke-test-docker.py`, and `scripts/smoke-test-agent-run.py`.
- Existing private deployment handoff uses Docker Compose with documented host-port overrides and prior smoke evidence.
- Existing migrations include knowledge/RAG, audit manifests, grounding binding, lifecycle contracts, web research attempts, context assembly, capability registry, and P6 Eval/Observability changes.
- P6 session evidence is recorded in `omx_wiki/session-2026-05-18-agent-knowledge-p6-groundedness-eval-observability.md`: P6 completed and pushed through `83c8eee`, with a later P6 wiki handoff commit on `origin/main`.
- Current repository evidence showed P6 commits and wiki handoff updates on `origin/main` with no tracked P6 residue, but P7 execution must recheck that before editing because it touches the same progress, roadmap, runbook, smoke, and evidence surfaces.
- P7 default decisions are fixed: seed data is a CLI script over public APIs using existing writable fields (`idempotency_key`, `seed-fixture://...` URI, and seed naming/description); Docker smoke defaults to a service-level migration/restore profile with full Compose only manual/nightly; browser smoke adds a focused `knowledge-demo.smoke.spec.ts` wired into the existing release smoke command.

## Constraints

- Do not reopen Stage 07 or redefine the product target.
- Do not add new core Agent Knowledge Harness capabilities in P7; this lane is release/demo hardening and evidence freshness.
- Do not introduce Kubernetes, cloud matrix, installer work, full operations platform work, or complex RBAC without a new explicit plan.
- Preserve P1-P6 evidence boundaries: append-only audit/manifests, real web provider policy gates, backend-owned context assembly, immutable capability snapshots, and Eval-owned grounding quality.
- Preserve P6 forbidden-snippet boundary: Eval API responses, frontend fixtures, reports, Run Detail, Observability, and runbooks must not reintroduce raw `forbidden_evidence_snippets` payloads.
- Keep seeded demo data deterministic, local/private safe, and non-confusing about fixture versus verified/provider-backed evidence.
- Prefer existing scripts, tests, fixtures, runbooks, and browser smoke structure before adding new infrastructure.
- Treat live provider validation as optional/credential-gated; deterministic seeded demo and mocked release smoke must work without secrets.
- P7-0 is a hard gate: verify pushed P6 implementation/report and wiki handoff commits, green CI/equivalent verification, P6 task-progress done, and a clean P7 branch before any P7 edits.

## Resolved Decisions

- P6 must be confirmed pushed, CI/equivalent verified, and recorded done before P7 starts.
- P7 fixtures and reports must preserve P6 response scrubbing: no raw forbidden snippet text.
- Seeded demo data must be created by a CLI script that calls public APIs, not by direct DB writes.
- Seeded evidence must use existing public API fields to mark fixture origin: deterministic `idempotency_key`, `seed-fixture://...` URI, and explicit P7 seed naming/description. Do not require `metadata_json` writes unless a separate API extension is approved.
- Docker smoke defaults to a service-level migration/restore profile; full Compose is manual/nightly.
- Browser smoke should add a focused `knowledge-demo.smoke.spec.ts` and wire it into the existing release smoke command. Because release smoke is mocked, this spec uses route fixtures aligned with the seed contract; the real seed script is verified by API readback.
- Provider configuration runbook updates should stay focused on current Tavily/web-research boundaries and optional live validation.

## Likely Codebase Touchpoints

- Release and smoke scripts:
  - `scripts/smoke-test-docker.py`
  - `scripts/smoke-test-agent-run.py`
  - `scripts/validate-harness-flow.sh`
  - a new or existing seed script under `scripts/`
  - a service-level migration/restore smoke script under `scripts/`
- Backend:
  - `services/api-server/app/api/agents.py`
  - `services/api-server/app/knowledge.py`
  - `services/api-server/tests/test_knowledge_rag.py`
  - Alembic migrations and migration/restore smoke tests
- Frontend browser smoke:
  - `apps/agent-console/e2e/agent-studio.smoke.spec.ts`
  - `apps/agent-console/e2e/agent-workspace*.spec.ts`
  - `apps/agent-console/e2e/run-detail.smoke.spec.ts`
  - `apps/agent-console/e2e/knowledge-demo.smoke.spec.ts`
  - `apps/agent-console/package.json`
- Docs/progress:
  - `docs/runbooks/deployment.md`
  - `docs/runbooks/troubleshooting.md`
  - `docs/runbooks/web-research.md`
  - `docs/ai/task-progress.yaml`
  - `docs/task-progress.md`
  - `omx_wiki/agent-knowledge-harness-roadmap.md`
  - `omx_wiki/project-handoff-current-state.md`

## P7-0 Baseline Verification Gate And Planning Bias

Prefer a narrow release-hardening vertical slice:

0. Verify the P6 baseline first: pushed P6 implementation/report and wiki handoff commits, green CI/equivalent verification, P6 done in task-progress/wiki, and a clean tracked P7 branch.
1. Do not edit any P7 files until P7-0 passes.
2. Add deterministic seeded Knowledge/RAG demo data through an idempotent public-API command with readback verification.
3. Add the service-level migration/restore smoke that proves knowledge tables survive upgrade/restore with current evidence selectors.
4. Add `knowledge-demo.smoke.spec.ts` to cover fixture projections aligned with the seed contract: Agent Studio knowledge source, Workspace grounded answer indicator, Run Detail knowledge evidence, and Eval/Observability grounding-quality presence, without raw forbidden snippet payloads.
5. Update runbooks and progress artifacts with exact commands, host-port override guidance, provider configuration boundaries, and failure-diagnosis evidence shape.
