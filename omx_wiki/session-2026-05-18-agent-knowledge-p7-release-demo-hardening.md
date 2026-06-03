# P7 Release And Demo Hardening

Category: session-log
Tags: `agent-knowledge-harness`, `release`, `demo`, `knowledge-grounding`, `browser-smoke`, `migration`, `runbook`, `task-progress`

## Summary

Agent Knowledge Harness P7 is completed, split into atomic commits, and pushed to `origin/p7-release-demo-hardening` through `c404603`.

P7 keeps the private handoff release gate current while preserving P1-P6 evidence boundaries. It adds deterministic local demo seed data through public Knowledge APIs, a service-level Knowledge/RAG migration/restore smoke, and mocked release browser coverage across Agent Studio, Workspace, Run Detail, Eval, and Observability.

## Delivered

- Added `scripts/seed-knowledge-demo.py`:
  - seeds agent-scoped and org-scoped Markdown knowledge through `POST /api/agents/{agent_id}/knowledge/sources`;
  - adds an agent-scoped grounding support document so the demo question satisfies the backend `min_hits=2` local-grounding threshold;
  - marks fixture origin with deterministic source names, `p7-seed-fixture:*` idempotency keys, and `seed-fixture://agent-knowledge-harness/p7/...` document URIs;
  - supports print-plan, readback verification, and idempotency checks;
  - avoids direct database writes and `metadata_json` writes.
- Added `scripts/smoke-test-knowledge-migration-restore.py`:
  - runs Alembic to head against a temporary SQLite database by default;
  - checks required Knowledge/RAG tables;
  - verifies retrieval-hit and citation selector continuity after engine reopen.
- Added `apps/agent-console/e2e/knowledge-demo.smoke.spec.ts`.
- Wired `knowledge-demo.smoke.spec.ts` into `npm run e2e:smoke:release`.
- Updated `apps/agent-console/e2e/eval-page.smoke.spec.ts` for P6 regression-delta fields so the release gate stays compatible with groundedness metrics.
- Updated deployment, troubleshooting, and web-research runbooks for P7 seed/readback, service-level migration/restore smoke, release browser smoke, and the local-fixture versus live-provider boundary.
- Updated `docs/ai/task-progress.yaml`, `docs/task-progress.md`, [[agent-knowledge-harness-roadmap]], and [[project-handoff-current-state]].

## Validation

```text
python3 -m py_compile scripts/seed-knowledge-demo.py scripts/smoke-test-knowledge-migration-restore.py
passed

python3 scripts/seed-knowledge-demo.py --print-plan
passed

HARNESS_API_BASE_URL=http://127.0.0.1:18007 python3 scripts/seed-knowledge-demo.py --verify-readback --check-idempotent
passed against a temporary local API server

python3 scripts/smoke-test-knowledge-migration-restore.py
passed

cd services/api-server && uv run ruff check ../../scripts/seed-knowledge-demo.py ../../scripts/smoke-test-knowledge-migration-restore.py app tests
All checks passed

cd services/api-server && uv run pytest tests/test_knowledge_rag.py tests/test_agents.py tests/test_evals.py tests/test_eval_regression.py tests/test_observability.py -q
123 passed

cd apps/agent-console && npm run lint
passed

cd apps/agent-console && npm run build
passed

cd apps/agent-console && npm test
147 passed

cd apps/agent-console && npm run e2e:smoke:release
36 passed

HARNESS_API_BASE_URL=http://127.0.0.1:18008 python3 scripts/seed-knowledge-demo.py --verify-readback --check-idempotent
passed on the non-default local API, returning agent_grounding-evidence_document_id c56df7d0-d084-4014-9119-12f8100e5dc6

POST /api/agents/default/runs/chat/stream with the demo question on http://127.0.0.1:18008
returned knowledge_grounding: Local knowledge grounded the answer.

git push -u origin p7-release-demo-hardening
pushed branch through c404603
```

The first release-smoke attempt failed because Playwright's configured webServer did not leave a reachable page on `127.0.0.1:5177`; all failures were `ERR_CONNECTION_REFUSED`. Manual Vite startup on the same port plus rerun passed. A second failure exposed an existing Eval smoke fixture gap for P6 regression-delta fields; after fixture repair, the release smoke passed.

Push commits:

```text
c404603 Record P7 release demo handoff
40026b3 Add P7 release demo review report
f8ba7cf Document P7 release demo runbooks
a561d4e Add P7 browser release smoke
7a15f1e Guard P7 service smoke scripts
d6478b7 Add P7 Knowledge demo seed
```

Pull request URL:

```text
https://github.com/luohao0308/harness/pull/new/p7-release-demo-hardening
```

## Boundaries

- P7 does not reopen Stage 07.
- P7 seed data is deterministic local fixture evidence, not Tavily/live provider verification.
- Browser smoke is mocked route-fixture coverage and does not consume live seeded backend rows.
- P7 does not introduce new Knowledge/RAG, Eval, Observability, or provider semantics beyond release/demo hardening.
- P7 fixtures and runbooks must not reintroduce raw forbidden evidence snippet payloads.
