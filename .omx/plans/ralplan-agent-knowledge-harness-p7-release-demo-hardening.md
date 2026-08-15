# Ralplan: Agent Knowledge Harness P7 Release And Demo Hardening

## Status

Consensus: approved by Planner, Architect, and Critic.

Planning scope only. P7 implementation may start only after P7-0 is rechecked in the current worktree.

## Context

The wiki and progress docs record P6 Groundedness Eval and Observability as completed and pushed. The next planned lane is P7 Release And Demo Hardening.

Current planning evidence:

- `omx_wiki/project-handoff-current-state.md`: P6 is completed and pushed; P7 is next.
- `omx_wiki/agent-knowledge-harness-roadmap.md`: P7 scope is Docker Compose migration smoke for knowledge tables, one-command seeded Knowledge/RAG demo data, browser release smoke for Agent Studio knowledge / Workspace grounding / Run Detail evidence, and runbook updates.
- `docs/ai/task-progress.yaml` and `docs/task-progress.md`: P6 owns `GroundingTraceV1`, grounding metrics/regression gates, Observability projection, and Run Detail objective selectors.
- `omx_wiki/session-2026-05-18-agent-knowledge-p6-groundedness-eval-observability.md`: P6 push/session record through `83c8eee`, followed by wiki handoff updates on `origin/main`.
- `.omx/context/agent-knowledge-harness-p7-release-demo-hardening-20260517T191008Z.md`: P7 pre-context snapshot.

Current risk: P7 touches the same progress, roadmap, runbook, smoke, and evidence surfaces that P6 recently changed. Current repository evidence showed P6 commits and wiki handoff updates on `origin/main` with no tracked P6 residue, but every P7 execution must still recheck this before editing.

## RALPLAN-DR Summary

### Principles

1. Verify the pushed P6 baseline before P7 edits.
2. Treat P7 as release/demo proof for existing capabilities, not new Harness capability work.
3. Make demo data deterministic, idempotent, local-safe, and non-secret-gated.
4. Preserve evidence ownership: Eval owns grounding quality; UI and Observability only project it.
5. Keep private handoff bounded to Docker Compose, runbooks, smoke tests, and evidence freshness.

### Decision Drivers

1. P6 recently changed files that P7 will also touch, so P7 must revalidate the pushed P6 baseline before editing.
2. P7 must make Knowledge/RAG, Workspace grounding, Run Detail evidence, Eval, and Observability reliably demonstrable.
3. Existing release gates and private deployment scripts already exist, so P7 should extend them instead of creating a parallel validation universe.

### Viable Options

Option A: Extend existing release/demo gates.
- Pros: smallest surface area; fits `scripts/smoke-test-docker.py`, `scripts/smoke-test-agent-run.py`, `scripts/validate-harness-flow.sh`, and `npm run e2e:smoke:release`.
- Cons: default smoke can become slower or more fragile if overloaded.

Option B: Add a narrow P7 demo seed/profile.
- Pros: gives internal testers a repeatable Knowledge/RAG demo path.
- Cons: if not wired into release gates, it becomes a side-channel proof.

Option C: Broaden into full deployment/operations hardening.
- Pros: wider operational confidence.
- Cons: scope creep; violates P7 boundaries.

Chosen: Option A plus a limited form of Option B. Integrate with existing gates and add a narrow one-command public-API demo seed. Reject Option C.

## ADR

Decision: P7 will harden release and demo validation for existing Agent Knowledge Harness capabilities through public-API demo seeding, Docker Compose migration/restore proof, mocked browser release smoke, and runbook/progress updates.

Drivers:
- P7 roadmap calls for release/demo hardening, not new capability development.
- Existing smoke and release gates already form the canonical validation path.
- Recent P6 changes must remain independently traceable before P7 edits.
- P7 must preserve P6's downstream projection boundary: forbidden evidence snippets are scrubbed from Eval API responses and must not be reintroduced through demo fixtures, Run Detail, Eval, Observability, reports, or runbooks.

Alternatives considered:
- Build a separate demo-only validation path: rejected because it risks bypassing the release gate.
- Add new Knowledge/RAG or grounding semantics: rejected because P6 already owns the grounding-quality layer.
- Expand to Kubernetes/cloud/installer/ops hardening: rejected as out of scope.

Why chosen:
- It proves the completed capabilities in the handoff path that internal testers will actually use.
- It keeps deterministic demo proof separate from optional credential-gated live provider validation.

Consequences:
- P7 execution must be stricter about file ownership and checkpointing than earlier lanes.
- Default smoke remains no-secret and deterministic.
- Compose migration/restore proof uses a new service-level profile by default; full Compose is manual/nightly.
- Demo seed must be a CLI script over public APIs and mark seeded data using existing writable API fields: deterministic `idempotency_key`, `seed-fixture://...` URI, and clear seed naming/description. Do not require `metadata_json` writes unless a separate API extension is explicitly approved.
- Browser release proof adds a focused `knowledge-demo.smoke.spec.ts` with route fixtures aligned to the seed contract; mocked browser smoke does not consume live seeded backend rows.

Follow-ups:
- If seed or smoke exposes a true release blocker in core Knowledge/RAG code, create a focused blocker repair branch or subtask with explicit justification.
- If live provider validation becomes a release requirement later, plan it as a separate credential-gated lane.

## Execution Plan

### P7-0: P6 Baseline Verification Gate

This is a hard precondition, not a planning preference. No P7 file edits are allowed until the current execution session confirms all applicable items.

1. Record current `git status --short`.
2. Run `git rev-list --left-right --count origin/main...HEAD` or the project-approved branch equivalent.
3. Confirm P6 commit/session evidence is present on the current base: `83c8eee` for the P6 implementation/report and the subsequent P6 wiki handoff commit on `origin/main`.
4. Confirm the relevant CI or equivalent local release gate is green or explicitly recorded as the accepted verification source.
5. Ensure `docs/ai/task-progress.yaml`, `docs/task-progress.md`, and wiki mark P6 done with P6-only evidence.
6. Create or switch to a clean P7 branch after verifying the pushed P6 base.
7. Re-read `git status --short` and `git diff --name-only`; both must show no tracked P6 residue in the P7 working tree.

Acceptance:
- P6 commit/session evidence is pushed and traceable independently from P7.
- CI or the agreed equivalent P6 verification is green.
- P6 status in `docs/ai/task-progress.yaml`, `docs/task-progress.md`, and wiki is done before P7 starts.
- P7 starts from a clean branch/worktree, ignoring only explicitly local untracked IDE/runtime artifacts.

### Phase 1: Deterministic Public-API Demo Seed

Add a one-command seed path under `scripts/`.

Requirements:
- Implement as a CLI script that calls existing public API endpoints.
- Must not directly write database rows for demo data.
- Creates agent-scoped and org-scoped knowledge source coverage.
- Creates deterministic text/Markdown document content.
- Defines a known demo question that can produce retrieval/citation evidence.
- Idempotent through deterministic names/idempotency keys or a cleanup/reset mode.
- No secrets required.
- Marks seeded data with existing public API fields:
  - `idempotency_key`: stable prefix such as `p7-seed-fixture:<agent|org>:<slug>`.
  - `uri`: stable `seed-fixture://agent-knowledge-harness/p7/<slug>` URI.
  - `name`/`description`: explicit P7 demo seed wording.
- Uses existing evidence badges/projections plus the seed naming/URI/idempotency convention to distinguish fixture/local evidence from provider-backed evidence.
- Never labels seeded evidence as provider-verified web evidence.
- Does not require writing `metadata_json`; current public create APIs do not accept metadata fields.

Default out of scope:
- `services/api-server/app/knowledge.py`
- core grounding semantics
- Eval-owned grounding calculations

Core files may only be changed if the seed/smoke exposes a real release blocker and the overlap is documented.

Acceptance:
- One command prepares demo data visible in Agent Studio, Workspace, and Run Detail.
- Re-running the seed is safe.
- The seed can run in local/private environments without Tavily or other external keys.
- The seed script validates its own API writes by reading back the created sources/documents and checking idempotency keys or `seed-fixture://` URIs.

### Phase 2: Docker Compose Migration And Restore Smoke

Add or extend private handoff smoke coverage.

Requirements:
- Keep this separate from the public-API demo seed.
- DB-level checks are allowed here only to prove migration, persistence, restore, and selector continuity.
- Default to a service-level migration/restore profile for fast release validation.
- Full Compose startup remains a nightly/manual switch, not the default P7 pass path.
- Verify clean Postgres migration to head.
- Verify knowledge/source/document/chunk/audit/prompt/retrieval/citation tables exist.
- Verify seeded or restored knowledge evidence survives restart/restore where applicable.
- Verify exact selectors remain resolvable.
- Use existing host-port override guidance.
- Always record cleanup evidence.

Acceptance:
- Service-level migration/restore profile passes.
- Compose config passes.
- Postgres migration reaches head.
- Knowledge evidence survives the intended private deployment smoke path.
- Cleanup completes.

### Phase 3: Mocked Browser Release Smoke Projection

Extend the existing release smoke, not a separate UI-only proof.

Coverage:
- Agent Studio displays seeded knowledge source/document.
- Workspace shows grounded/citation/retrieval indicator for the seeded demo question.
- Run Detail shows knowledge evidence, retrieval hits, citations, prompt manifest, or objective selectors.
- Eval/Observability show Eval-owned grounding quality.
- Forbidden snippet text is not rendered.
- Eval API response fixtures do not include raw `forbidden_evidence_snippets`; they use scrubbed fields or counts/flags only.

Rules:
- Default browser smoke must not require Tavily or any external provider key.
- Browser smoke verifies UI projection, not live factual verification.
- UI must not recompute groundedness.
- Add a focused `knowledge-demo.smoke.spec.ts` and wire it into `npm run e2e:smoke:release`.
- Keep the new spec limited to seeded-data assertions so existing smoke specs do not gain P7-specific coupling.
- Because the release smoke is a mocked browser gate, `knowledge-demo.smoke.spec.ts` uses Playwright route fixtures that mirror the seed contract. The real public-API seed script is verified by its own API readback/smoke, not by mocked browser routes.

Acceptance:
- `npm run e2e:smoke:release` covers the P7 demo projection path through `knowledge-demo.smoke.spec.ts`.
- Failures localize to seed, API, Workspace, Run Detail, Eval, or Observability.
- The seed script API smoke and browser fixture smoke are reported as separate evidence types.
- Fixture review proves no forbidden snippet payload is reintroduced into mocked browser, report, or runbook evidence.

### Phase 4: Optional Live Provider Documentation

Keep Tavily/live provider validation credential-gated and opt-in.

Requirements:
- Document how to run it when credentials are available.
- Do not include it in default P7 pass criteria.
- Keep P3 boundary: web research is source-bound provider evidence, not backend crawling or factual verification.

Acceptance:
- Runbook clearly distinguishes deterministic local demo from optional live provider validation.

### Phase 5: Runbook, Progress, And Wiki Updates

Update:

- `docs/runbooks/deployment.md`
- `docs/runbooks/troubleshooting.md`
- `docs/runbooks/web-research.md`
- `docs/ai/task-progress.yaml`
- `docs/task-progress.md`
- `omx_wiki/agent-knowledge-harness-roadmap.md`
- `omx_wiki/project-handoff-current-state.md`

Acceptance:
- A new internal tester can run the deterministic demo path from the runbook.
- Docs distinguish deterministic local demo, mocked browser release smoke, Compose migration/restore proof, and optional live provider validation.
- P7 is recorded only after verification passes.

## Verification Plan

Run the smallest checks first, then release gates.

Suggested sequence:

```bash
git status --short
git rev-list --left-right --count origin/main...HEAD
git log --oneline -5
git diff --name-only
# P7-0 must show pushed P6 implementation/report + wiki handoff commits,
# accepted P6 verification, and a clean tracked P7 worktree.
cd services/api-server && uv run pytest tests/test_evals.py tests/test_eval_regression.py tests/test_observability.py -q
cd services/api-server && uv run pytest tests/test_knowledge_rag.py tests/test_agents.py -q
cd services/api-server && uv run ruff check app tests
cd services/api-server && DATABASE_URL=sqlite:////tmp/harness-p7-alembic.sqlite uv run alembic upgrade head
docker compose --env-file deploy/docker-compose/.env.example -f deploy/docker-compose/docker-compose.yml config
python3 scripts/<p7-knowledge-demo-seed>.py --check-idempotent
python3 scripts/<p7-knowledge-demo-seed>.py --verify-readback
python3 scripts/<p7-service-migration-restore-smoke>.py
# Optional manual/nightly full compose:
# python3 scripts/smoke-test-docker.py
python3 scripts/smoke-test-agent-run.py
cd apps/agent-console && npm run lint
cd apps/agent-console && npm run build
cd apps/agent-console && npm test
cd apps/agent-console && npm run e2e:smoke:release
python3 scripts/validate-docs.py
git diff --check
```

For private Compose execution, use explicit project name and host-port overrides when defaults are occupied. Always run `docker compose down` cleanup.

## Likely Touchpoints

Primary:

- `scripts/smoke-test-docker.py`
- `scripts/smoke-test-agent-run.py`
- `scripts/validate-harness-flow.sh`
- new `scripts/*knowledge*seed*`
- new `scripts/*migration*restore*smoke*`
- new `apps/agent-console/e2e/knowledge-demo.smoke.spec.ts`
- `apps/agent-console/e2e/agent-studio.smoke.spec.ts`
- `apps/agent-console/e2e/agent-workspace*.spec.ts`
- `apps/agent-console/e2e/run-detail.smoke.spec.ts`
- `apps/agent-console/e2e/observability.smoke.spec.ts`
- runbooks and progress docs/wiki listed above

Secondary only if a release blocker is exposed:

- `services/api-server/app/api/agents.py`
- `services/api-server/app/knowledge.py`
- `services/api-server/tests/test_knowledge_rag.py`

## Non-Goals

- No new core Knowledge/RAG, Eval, Observability, Workspace, MCP, or Skills capability.
- No Stage 07 reopening.
- No Kubernetes, cloud matrix, installer, full operations platform, or complex RBAC.
- No default secret-gated smoke.
- No UI groundedness recomputation.
- No direct DB writes for demo seed.
- No claim that fixture/deterministic evidence is provider-verified evidence.
- No new metadata field requirement for public API seed unless separately approved.
- No raw forbidden snippet text in P7 fixtures, reports, runbooks, Eval UI, Observability, or Run Detail assertions.

## Available Agent Types And Staffing Guidance

Available agent types:

- `explore`: fast codebase lookup and file/symbol mapping.
- `planner`: sequencing and risk flags.
- `architect`: boundary and interface review.
- `executor`: implementation and refactoring.
- `test-engineer`: test strategy and regression coverage.
- `verifier`: completion evidence and claim validation.
- `writer`: runbooks, reports, and progress docs.
- `code-reviewer`: final code review.
- `debugger`: failed gate root cause.
- `researcher`: official docs only if external provider or framework behavior must be checked.

Ralph path:
- Use `$ralph` when one owner should carry P7-0 through verification sequentially.
- Suggested reasoning: high for P7-0 and final verification, medium for seed/e2e/docs implementation.
- Handoff: `$ralph implement .omx/plans/ralplan-agent-knowledge-harness-p7-release-demo-hardening.md`

Team path:
- Use `$team` only after P7-0 is complete and implementation can split cleanly.
- Suggested lanes:
  - executor: public-API seed script and script tests.
  - test-engineer: Compose migration/restore smoke and release smoke wiring.
  - writer: deployment/troubleshooting/web-research runbook and progress updates.
  - verifier: final gate evidence and boundary audit.
- Keep write scopes disjoint; do not let multiple lanes edit the same P6-overlap files without leader approval.
- Launch hint: `$team implement .omx/plans/ralplan-agent-knowledge-harness-p7-release-demo-hardening.md`

Team verification path:
- Verifier must prove P7-0 happened before reviewing any P7 implementation.
- Verifier must check P7 fixtures and reports preserve P6 forbidden-snippet scrubbing.
- Verifier must classify evidence into deterministic API seed/readback, mocked browser release fixture smoke, service-level migration/restore, optional full Compose/live provider, and docs/progress.

## Goal-Mode Follow-Up Suggestions

- `$ultragoal` is the default durable follow-up if P7 should become tracked goal-mode work with checkpoints.
- `$ultragoal` plus `$team` is appropriate if P7-0 is completed and seed/e2e/docs/smoke lanes are split in parallel.
- `$autoresearch-goal` is not the right default because P7 is implementation/release validation, not research.
- `$performance-goal` is not the right default unless P7 later changes into smoke/runtime performance optimization.
