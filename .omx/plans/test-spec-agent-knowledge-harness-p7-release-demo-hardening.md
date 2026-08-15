# Test Spec: Agent Knowledge Harness P7 Release Demo Hardening

## P7-0 Baseline Gate

- Run `git status --short`.
- Run `git rev-list --left-right --count origin/main...HEAD`.
- Confirm P6 implementation/report commit `83c8eee` and the later P6 wiki handoff commit are on the current base.
- Confirm `docs/ai/task-progress.yaml`, `docs/task-progress.md`, and wiki mark P6 complete.
- Confirm no tracked P6 residue exists before P7 edits.

## Seed Verification

- Run the P7 seed command against a local API server in dry-run or explicit base-url mode.
- Verify the command uses public API calls only.
- Verify agent-scoped and org-scoped sources include deterministic names, `p7-seed-fixture:` idempotency keys, and `seed-fixture://agent-knowledge-harness/p7/...` URIs.
- Re-run seed verification to prove idempotency/readback.

## Migration/Restore Smoke

- Run the service-level migration/restore smoke script.
- Verify Alembic reaches head on a private handoff database.
- Verify knowledge source/document/chunk/audit/prompt/retrieval/citation tables exist.
- Verify selector/evidence rows remain resolvable after the restore/reopen step.
- Verify cleanup evidence is printed.

## Browser Release Smoke

- Run `cd apps/agent-console && npm run e2e:smoke:release`.
- Verify the new Knowledge demo smoke uses route fixtures aligned with the seed contract.
- Verify it covers Agent Studio, Workspace, Run Detail, Eval, and Observability projections.
- Verify fixtures and assertions do not include raw `forbidden_evidence_snippets`.

## Regression Gates

- Backend targeted tests for Knowledge/RAG and P6 grounding/observability.
- Backend ruff.
- Frontend lint, build, unit tests, and release smoke.
- Compose config validation.
- Docs validation.
- `git diff --check`.
