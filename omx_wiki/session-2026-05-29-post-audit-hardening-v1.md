# Session 2026-05-29 Post-Audit Hardening v1

Category: `session-log`

Tags: `agent-knowledge-harness`, `post-audit-hardening`, `migration`, `postgres`, `alembic`, `agent-console`, `task-progress`

## Summary

Post-Audit Hardening v1 is verified locally on `p7-release-demo-hardening`. The slice closes the audit gaps around marketplace id width, FastAPI startup lifecycle, frontend bundle size, large backend files, deployment migration preflight, adapter import bootstrap, and future commit-hygiene guidance.

## Delivered Scope

- Added Alembic patch migration `20260531_0026_widen_marketplace_ids.py` because `20260530_0025` already had git history. The patch widens `specialist_selection_decisions.id`, `specialist_marketplace_listings.id`, `specialist_installations.id`, and `specialist_installations.listing_id` to `String(128)` on non-SQLite.
- Updated marketplace ORM fields to match the patch migration while keeping unrelated UUID-sized ids at `String(36)`.
- Replaced FastAPI `@app.on_event("startup")` with an async lifespan hook that calls adapter bootstrap during app startup.
- Made built-in adapter registration idempotent and exposed `python -m app.cli.registry_info` for import-only registry diagnostics.
- Added Vite manual chunks for vendor and feature bundles. The latest build emits 7 JavaScript chunks and a 77.18 kB main `index-*.js`.
- Split `agent_chat`, `agent_knowledge`, eval endpoint, and provider fallback modules into smaller files while preserving public import paths.
- Added `scripts/migration-preflight.sh` and deployment runbook instructions for full PostgreSQL Alembic preflight. The script prefers Docker and falls back to local PostgreSQL binaries when Docker daemon is unavailable.
- Added local `.omx/plans/_template.md` commit-hygiene guidance for future PRDs. The `.omx/` tree is repository-ignored, so this remains an OMX planning artifact unless later promoted to tracked docs.

## Review And Drift Checks

Code review found and fixed one real issue before completion:

- `TeamAgent.id` and `TeamMailboxMessage.id` had been accidentally widened to `String(128)` even though the PRD and migration only scoped marketplace ids. Both were restored to `String(36)`.

Follow-up review returned `APPROVE`.

Architecture review returned `WATCH` with no merge blocker:

- bundle splitting is artifact-level manual chunking, not route-level `React.lazy`;
- split modules still use wildcard compatibility re-exports in several public entry points.

Both watch items match the PRD boundary and are follow-up hardening, not current blockers.

## Validation Evidence

```text
cd services/api-server && .venv/bin/python -m pytest tests/test_teams.py tests/test_subagent_marketplace.py tests/test_specialist_calibration.py tests/test_adapter_registry.py -q
44 passed

cd services/api-server && .venv/bin/python -m ruff check app tests
All checks passed

cd services/api-server && .venv/bin/python -m pytest tests -q
500 passed, 2 warnings

cd services/api-server && DATABASE_URL=sqlite:////tmp/harness-post-audit-hardening-after-review.sqlite .venv/bin/python -m alembic upgrade head
passed through 20260531_0026

bash scripts/migration-preflight.sh
passed through 20260531_0026 on PostgreSQL; Docker daemon was unavailable, so the script used local PostgreSQL binaries

cd apps/agent-console && npm test -- --run --pool forks --poolOptions.forks.singleFork
48 files / 223 tests passed

cd apps/agent-console && npm run lint -- --pretty false
passed

cd apps/agent-console && npm run build
passed; 7 JavaScript chunks; main index asset 77.18 kB

python3 scripts/validate-docs.py
passed

git diff --check
passed
```

## Next Work

- Route-level `React.lazy` can further reduce initial route evaluation in a bundle v2.
- Replace compatibility wildcard re-exports with explicit public APIs once callers are audited.
- Promote commit-hygiene DoD from `.omx/` into a tracked docs path if it should become repository-enforced.

## Related Pages

- [[agent-knowledge-harness-roadmap]]
- [[session-2026-05-28-large-file-refactor-v1]]
- [[session-2026-05-29-agent-knowledge-observability-v1]]
- [[session-2026-05-29-real-tool-adapters-v2]]
- [[session-2026-05-29-subagent-specialists-v3]]
