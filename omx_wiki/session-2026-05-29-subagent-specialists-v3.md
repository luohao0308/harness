# Session 2026-05-29 Subagent Specialists v3

Category: `session-log`

Tags: `agent-knowledge-harness`, `subagents`, `specialists`, `marketplace`, `calibration`, `fanout`, `agent-console`, `task-progress`

## Summary

Subagent Specialists v3 is verified locally on `p7-release-demo-hardening`. This slice upgrades the v1/v2 specialist layer with LLM-based specialist selection, selection calibration reporting, a signed/admin-reviewed specialist marketplace, and bounded dynamic fanout extension.

## Delivered Scope

- Added `specialist_selection_decisions`, `specialist_marketplace_listings`, and `specialist_installations` through Alembic revision `20260530_0025`.
- Added `SpecialistLLMSelector` with model-gateway JSON selection, confidence thresholds, org-level disable setting, and keyword/success-rate/recency fallback when the model is unavailable, invalid, low confidence, or selects an unknown slug.
- Executor specialist routing now records selection decision ids in subagent context for later calibration.
- Added `GET /api/subagent-specialists/calibration?window=7d|30d|all` with confidence buckets, low-sample state, and ECE derived from same-task subagent outcomes.
- Added `/api/subagent-marketplace` listing browse/detail/create/update/approve/install/uninstall APIs with HMAC manifest signatures, output-schema and budget validation, prompt blacklist scanning, and capability allowlist checks.
- Marketplace install creates an org-local `SubagentSpecialist` copy and a `SpecialistInstallation` row rather than runtime-linking to the marketplace listing.
- Added `SubagentManager.extend_fanout(...)` and `POST /api/subagents/{id}/fanout/extend` with requester/batch checks, running-batch guard, `MAX_DYNAMIC_FANOUT=10`, max 3 extensions per batch, max 1 extension per requester, and `FANOUT_EXTENDED` events.
- Added Agent Console specialist marketplace list/detail pages, calibration panel, sidebar route, dynamic fanout badges, and fanout history display.

## Review And Drift Checks

Code review found and fixed three real issues before completion:

- Updating a verified listing's manifest, signature, or version left `verified=true`. The update path now resets `verified=false` whenever those review-sensitive fields materially change.
- Marketplace uninstall initially hard-deleted the installed specialist copy. It now deletes the installation link but archives the specialist, preserving historical `agent_runs` / `subagent_outputs` foreign-key evidence.
- Calibration run lookup initially scanned all subagent runs and matched only by decision id in context. It now also restricts run lookup to the decision task ids so abnormal or stale context cannot influence another task's calibration bucket.

Drift review confirmed the implementation stayed in the v3 lane:

- LLM selection has a deterministic fallback path and cannot choose a non-existent slug as final output.
- Marketplace installs remain org-local specialist copies; listing manifests are revalidated and re-signed before install.
- Dynamic fanout is bounded and requires the requester to already be a subagent in the target fanout batch. The HTTP API approximates the PRD's "same task subagent caller" boundary through existing bearer auth plus path requester identity; there is no separate subagent runtime credential in the current architecture.
- `MARKETPLACE_INSTALLED` remains an enum reservation rather than an emitted event because the existing `EventStore` is task-scoped while marketplace install is org-scoped.
- P5-P8 capability, adapter, and observability semantics were not changed.

## Validation Evidence

```text
cd services/api-server && uv run pytest tests/test_subagent_marketplace.py tests/test_specialist_calibration.py tests/test_fanout_extend.py tests/test_specialist_llm_selector.py -q
10 passed

cd services/api-server && uv run ruff check app tests
All checks passed

cd services/api-server && uv run pytest tests/test_specialist_llm_selector.py tests/test_specialist_calibration.py tests/test_subagent_marketplace.py tests/test_fanout_extend.py tests/test_subagent_specialists.py tests/test_subagents.py -q
34 passed

cd services/api-server && DATABASE_URL=sqlite:////tmp/harness-subagent-specialists-v3.sqlite uv run alembic upgrade head
passed through 20260530_0025

cd services/api-server && uv run pytest tests -q
497 passed, 4 warnings

cd apps/agent-console && npm test -- SubagentSpecialistsPage.test.tsx SubagentDetailPage.test.tsx SubagentMarketplacePage.test.tsx --run
3 files / 4 tests passed

cd apps/agent-console && npm test -- src/features/teams/__tests__/TeamPages.test.tsx --run
19 passed

cd apps/agent-console && npm test -- --run --pool forks --poolOptions.forks.singleFork
48 files / 223 tests passed

cd apps/agent-console && npm run lint -- --pretty false
passed

cd apps/agent-console && npm run build
passed with existing Vite large-chunk warning

python3 scripts/validate-docs.py
passed

git diff --check
passed
```

The default parallel frontend Vitest run previously reproduced the known unrelated TeamPages branch-switch flaky around `分支 1/2`. The same file passed when run directly, and the full suite passed under single-fork isolation, so the risk is recorded as existing test isolation rather than v3 drift.

## Next Work

- Add a true subagent-runtime credential or signed internal callback if dynamic fanout needs to distinguish model/subagent-originated calls from user-initiated API calls beyond current path identity checks.
- Add an org-scoped audit stream for marketplace install/uninstall if marketplace lifecycle needs durable non-task events.
- Run live model-selector latency/cost calibration and real cross-org marketplace admin workflow smoke when provider credentials and multiple org fixtures are available.

## Related Pages

- [[project-handoff-current-state]]
- [[agent-knowledge-harness-roadmap]]
- [[session-2026-05-28-subagent-specialists-v1]]
- [[session-2026-05-28-subagent-specialists-v2]]
