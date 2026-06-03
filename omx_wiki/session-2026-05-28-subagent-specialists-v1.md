# Subagent Specialists v1

Category: `session-log`

Tags: `agent-knowledge-harness`, `subagents`, `specialists`, `orchestration`, `structured-output`, `budget`, `agent-console`

## Summary

Subagent Specialists v1 is implemented locally on branch `p7-release-demo-hardening`.

This slice upgrades subagents from anonymous async workers into specialist templates with explicit role prompts, capability whitelists, output schemas, budgets, planner hints, immutable structured outputs, and console evidence views.

## Delivered

- Added `subagent_specialists` and `subagent_outputs` plus nullable `agent_runs.specialist_id`.
- Seeded four system specialists: `code-reviewer`, `researcher`, `safety-checker`, and `synthesizer`.
- Added `SubagentSpecialistRegistry`, schema validation, schema hashing, budget normalization/checking, system-specialist bootstrap helpers, default structured output helpers, and output collection.
- Added `/api/subagent-specialists` list/create/get/update/archive/preflight API.
- Extended `/api/subagents` with specialist-aware list/detail/create responses and `POST /api/subagents/{id}/output`.
- Extended `SubagentManager.spawn(..., specialist=...)` to snapshot specialist contracts without redesigning manager behavior.
- Added `finalize_with_output(...)` for write-once structured outputs while preserving legacy `context_json.result`.
- Extended worker execution with specialist prompt overrides, capability whitelist denial, budget checks after model/tool calls, `BUDGET_EXCEEDED`, and structured output writes.
- Extended planner/executor/task result contracts with `recommended_specialist_slug`, deterministic specialist selection, parent output collection, and specialist output/budget fields.
- Added Agent Console `/subagent-specialists` and `/subagent-specialists/:id`, sidebar `专家库`, specialist filtering on `/subagents`, structured output and budget evidence on subagent detail, plan-step specialist badges, and Run Detail `专家证据`.

## Validation

```text
cd services/api-server && uv run pytest tests/test_subagent_specialists.py tests/test_subagents.py -q
20 passed, 1 warning

cd services/api-server && uv run pytest tests -q
426 passed, 1 warning

cd services/api-server && uv run ruff check app tests
All checks passed

cd services/api-server && DATABASE_URL=sqlite:////tmp/harness-subagent-specialists-alembic-upgrade.sqlite uv run alembic upgrade head
upgraded through 20260528_0023

cd services/api-server && DATABASE_URL=sqlite:////tmp/harness-subagent-specialists-alembic-upgrade.sqlite uv run alembic downgrade 20260527_0022
downgraded 20260528_0023 -> 20260527_0022

cd apps/agent-console && npm test -- SubagentSpecialistsPage SubagentDetailPage --run
2 files passed, 3 tests passed

cd apps/agent-console && npm run lint -- --pretty false
passed

cd apps/agent-console && npm run build
passed, with existing Vite large-chunk warning

python3 scripts/validate-docs.py
docs validation passed

git diff --check
passed
```

## Notes

- `SubagentOutput` is additive and write-once; existing subagent result consumers can still read `context_json.result`.
- System specialists are protected from direct user edits and deletion; organization/private templates remain user-managed.
- Budget cost accounting uses model-call `cost_usd` when present; runtime, token, and tool-call guards are active.
- `BUDGET_EXCEEDED` stops the subagent and is treated as terminal for waiting logic, but parent tasks can still use fallback behavior.
- Capability whitelist v1 is enforced before `ToolRunner.execute`, using existing P5 capability slugs rather than introducing a parallel capability model.

## Next

- Eval contract integration for expected specialists and specialist output schemas remains v2.
- Parallel fanout, nested specialist depth limits, marketplace sharing, and ranking by historical success rate remain out of scope for v1.
