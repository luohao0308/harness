# P7 Release And Demo Hardening

Category: session-log
Tags: `agent-knowledge-harness`, `release`, `demo`, `knowledge-grounding`, `browser-smoke`, `migration`, `runbook`, `task-progress`

## Summary

Agent Knowledge Harness P7 is completed, split into atomic commits, and pushed to `origin/p7-release-demo-hardening` through `c404603`.

The same branch also has a follow-up console UI hardening commit through `a5d046b`: shared accessible selectors replaced the remaining native/one-off dropdowns, required English terms now carry small Chinese explanations, and the review fixes were validated and pushed.

P7 keeps the private handoff release gate current while preserving P1-P6 evidence boundaries. It adds deterministic local demo seed data through public Knowledge APIs, a service-level Knowledge/RAG migration/restore smoke, and mocked release browser coverage across Agent Studio, Workspace, Run Detail, Eval, and Observability.

2026-05-31 follow-up: the Dashboard Demo load state mismatch is fixed. When `一键加载 Demo` succeeds or returns `already_loaded`, the yellow `Demo 数据未加载` banner now disappears immediately, and `/api/onboarding/state` reconciles the current user's `demo_loaded` / `demo_task_id` from existing organization-level Demo artifacts so refreshes stay consistent. This specifically fixes the dev-token split where Dashboard read the engineer onboarding state while the Demo load call used the dev-admin token.

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
- Updated `docs/development/ai/task-progress.yaml`, `docs/工作日志/archive/task-progress-legacy.md`, [[agent-knowledge-harness-roadmap]], and [[project-handoff-current-state]].
- Added follow-up console UI hardening:
  - new shared `MenuSelect` for model, knowledge, run, and settings selectors;
  - keyboard/focus behavior, disabled-option skipping, grouping, top/bottom placement, and exact selector test coverage;
  - `TermHint` small-text explanations for required English terms such as MCP, RAG, API, Trace, WarmPool, JSON, Markdown, Prompt, and Provider;
  - Chinese-first copy across Agent Studio, Workspace, Eval, Observability, Run Detail, Sandboxes, Tool Registry, and settings surfaces.

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

cd apps/agent-console && npm run lint
passed after the selector/term UI follow-up

cd apps/agent-console && npm test
30 files / 148 tests passed after the selector/term UI follow-up

cd apps/agent-console && npm run build
passed after the selector/term UI follow-up

git diff --check
passed after the selector/term UI follow-up

git push origin p7-release-demo-hardening
pushed branch through a5d046b

Local service check after restart on a non-default frontend port:
frontend http://127.0.0.1:18082/ -> ok
API http://127.0.0.1:8000/health -> {"status":"ok","service":"api-server"}
```

The first release-smoke attempt failed because Playwright's configured webServer did not leave a reachable page on `127.0.0.1:5177`; all failures were `ERR_CONNECTION_REFUSED`. Manual Vite startup on the same port plus rerun passed. A second failure exposed an existing Eval smoke fixture gap for P6 regression-delta fields; after fixture repair, the release smoke passed.

Push commits:

```text
a5d046b Make console selectors and terms usable for Chinese-first UI
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

## 2026-06-21 Demo Artifact Refresh

Branch `chore/demo-artifacts` refreshed the demo evidence files only.

```text
POST /api/sandboxes/warm-pool/benchmark
request: {"iterations":30}
environment: local-dev, isolated SQLite database, one seeded IDLE WarmPoolContainer
status: PASS
warm_p95_ms: 1
warm_avg_ms: 0
cold_avg_ms: 275 synthetic baseline
hit_rate: 100
sample_size: 30
```

Updated files:

```text
docs/工作日志/reports/benchmark-report.md
docs/design/media/gifs/README.md
docs/design/media/gifs/first-agent-run.gif
docs/design/media/gifs/first-agent-run-screenshot.png
```

Capture notes: `ffmpeg` and Docker Compose were available. macOS
`screencapture` initially produced a short test recording, then returned
`capture error` during the full-flow attempt, so the final GIF uses Playwright
Chromium `recordVideo` converted with `ffmpeg`. The GIF exercises the real
Agent Console UI with mocked local API/SSE responses and does not require
external model-provider credentials or a Docker worker.

## Boundaries

- P7 does not reopen Stage 07.
- P7 seed data is deterministic local fixture evidence, not Tavily/live provider verification.
- Browser smoke is mocked route-fixture coverage and does not consume live seeded backend rows.
- P7 does not introduce new Knowledge/RAG, Eval, Observability, or provider semantics beyond release/demo hardening.
- P7 fixtures and runbooks must not reintroduce raw forbidden evidence snippet payloads.
- The `a5d046b` UI follow-up is presentation/accessibility hardening only; it does not change Knowledge/RAG, Eval, Observability, provider, or release-gate semantics.
