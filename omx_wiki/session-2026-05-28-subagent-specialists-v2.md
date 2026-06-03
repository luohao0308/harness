# Subagent Specialists v2

Category: `session-log`

Tags: `agent-knowledge-harness`, `subagents`, `specialists`, `fanout`, `eval`, `ranking`, `agent-console`

## Summary

Subagent Specialists v2 is implemented locally on branch `p7-release-demo-hardening`.

This slice extends v1 specialist contracts with bounded parallel fanout, nested-depth protection, deterministic Eval specialist contracts, real-time specialist performance stats, success-rate ranking for ambiguous keyword matches, and console evidence for fanout batches.

## Delivered

- Added `fanout_specialist_slugs` and `fanout_aggregation` to plan-step contracts and API projections.
- Added bounded `SubagentManager.spawn_fanout(...)` with shared `fanout_batch_id`, per-run `fanout_index`, `fanout_total`, and `MAX_FANOUT_PER_STEP=5`.
- Added `MAX_SPECIALIST_DEPTH=3`, `SubagentDepthExceededError`, `SUBAGENT_DEPTH_REJECTED` audit events, and API 409 mapping for over-nested specialist spawns.
- Added `GET /api/subagent-specialists/{id}/stats?window=7d|30d|all` with invocation, success, runtime, cost, tool-call, output-size, and failure-reason metrics.
- Added success-rate ranking for multi-candidate keyword matches, with trace metadata for `success_rate_ranking` and recency fallback.
- Added deterministic Eval `specialist_contract` grading for expected/forbidden specialists, output assertions, budget limits, fanout assertions, aggregate metrics, role distribution, and regression delta/gate fields.
- Added `GET /api/tasks/{task_id}/fanout-batches` and extended subagent list/detail responses with fanout metadata.
- Extended Agent Console specialist list/detail pages with success rate, invocation counts, performance windows, and recent failure reasons.
- Extended subagent list/detail, execution plan, Run Detail, and Eval UI with fanout badges, batch filters, sibling links, grouped expert evidence, specialist contract metrics, and a `专家契约` preset.

## Validation

```text
cd services/api-server && uv run pytest tests/test_subagent_specialists.py tests/test_subagents.py tests/test_evals.py tests/test_eval_regression.py -q
55 passed, 1 warning

cd services/api-server && uv run pytest -q
435 passed, 1 warning

cd services/api-server && uv run ruff check app tests
All checks passed

cd apps/agent-console && npm test -- SubagentSpecialistsPage.test.tsx SubagentDetailPage.test.tsx EvalRunResults.contracts.test.tsx
5 tests passed

cd apps/agent-console && npm run lint -- --pretty false
passed

cd apps/agent-console && npm run build
passed, with existing Vite large-chunk warning

cd apps/agent-console && npm test -- --run
44 files passed, 214 tests passed

python3 scripts/validate-docs.py
docs validation passed

git diff --check
passed
```

## Notes

- No new tables, migrations, or DB columns were added. Fanout metadata uses `agent_runs.context_json`; output/Eval contracts use existing JSON columns.
- V1 async semantics were preserved. Fanout spawning is bounded and evidence-backed, but this slice does not redesign the executor into a synchronous parent wait loop.
- `synthesizer_chain`, `concat`, and `first_success` are represented in the contract and evidence. Aggregation behavior follows the current async execution boundary.
- Full frontend Vitest emits existing React `act(...)` warnings in Knowledge/Team tests, but all 44 files and 214 tests passed on rerun.

## Next

- Decide whether fanout needs a fully blocking parent aggregation loop in a later executor redesign.
- Profile real `fanout_batch_id` JSON queries before adding a persisted indexed column.
- Browser smoke for the new specialist stats and fanout evidence pages remains optional follow-up.
