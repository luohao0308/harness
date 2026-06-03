# Session 2026-05-30 Enterprise Sidebar Audit Repair Plans

## Summary

Audited `.omx/plans/enterprise-left-sidebar-functional-test-plan.md` against the current repository and converted the discovered gaps into three focused repair plans.

Update: the three repair plans were executed on 2026-05-30. The original audit findings below remain as historical starting evidence; the current verified state is captured in the "Execution Result" section.

## Repair Plans

- `.omx/plans/repair-enterprise-sidebar-test-coverage-plan.md`
- `.omx/plans/repair-model-pricing-official-source-cost-gate-plan.md`
- `.omx/plans/repair-team-subagent-and-release-smoke-regressions-plan.md`

## Findings

- The planned enterprise test deliverables are still absent, including `sidebar-enterprise.smoke.spec.ts`, `enterprise-harness-chains.spec.ts`, `model-pricing.enterprise.spec.ts`, `enterpriseHarness.ts`, `routeInventory.test.tsx`, backend enterprise chain tests, and `model_pricing_sources.json`.
- Baseline frontend/backend unit tests, lint, Ruff, and frontend build passed, but those gates do not prove sidebar-wide enterprise behavior.
- Release smoke is currently red: `HARNESS_ALLOW_MISSING_PHASE0B_EVIDENCE=1 npm run e2e:smoke:release` reported 16 failed and 33 passed.
- Release-smoke failures cluster around shell API fixture gaps, Knowledge demo click interception, Run Detail fixture/contract drift, and an MCP strict selector collision.
- Team Mode enforces `team_spawn_agent` when claiming teammate creation, but `_tool_spawn_agent` creates TeamAgent state without durable subagent run, output, specialist, Run Detail, and Observability evidence.
- Model pricing currently lacks official-source metadata, current built-in preset coverage, verification status, validity windows, tier/region/mode handling, and explicit missing-pricing release blockers.

## Evidence

- Sidebar inventory: `apps/agent-console/src/app/ConsoleShell.tsx:44`
- Dynamic routes: `apps/agent-console/src/app/routes.tsx:45`
- Built-in model presets: `apps/agent-console/src/features/settings/pages/ModelSettingsPage.tsx:60`
- Backend model defaults: `services/api-server/app/agents/model_gateway.py:97`
- Pricing model schema: `services/api-server/app/db/models.py:1555`
- Stale pricing seed rows: `services/api-server/alembic/versions/20260527_0022_create_model_pricing.py:25`
- Missing-pricing zero fallback: `services/api-server/app/observability/cost_rollup.py:198`
- Eval missing-pricing trace path: `services/api-server/app/api/evals/graders/cost.py:82`
- Team tool protocol: `services/api-server/app/teams/service.py:60`
- Team spawn implementation: `services/api-server/app/teams/service.py:2417`

## Commands

- `cd apps/agent-console && npm test -- --run --pool forks --poolOptions.forks.singleFork` -> 49 files passed, 226 tests passed.
- `cd services/api-server && .venv/bin/python -m pytest tests/test_settings.py tests/test_model_gateway.py tests/test_observability_cost_rollup.py tests/test_evals.py::test_eval_run_grades_cost_contract_with_model_pricing tests/test_evals.py::test_eval_run_cost_missing_pricing_records_zero_cost_and_misses tests/test_teams.py tests/test_agents.py -q` -> 125 passed.
- `cd apps/agent-console && npm run lint -- --pretty false` -> passed.
- `cd services/api-server && .venv/bin/python -m ruff check app tests` -> passed.
- `cd apps/agent-console && npm run build` -> passed.
- `cd apps/agent-console && HARNESS_ALLOW_MISSING_PHASE0B_EVIDENCE=1 npm run e2e:smoke:release` -> failed, 16 failed and 33 passed.
- Official-source reachability checks returned HTTP 200 for DeepSeek and Kimi pages; OpenAI official Developers pages are now the target source for OpenAI pricing capture.

## Execution Result

- Added deterministic enterprise sidebar and cross-feature coverage:
  - `apps/agent-console/e2e/sidebar-enterprise.smoke.spec.ts`
  - `apps/agent-console/e2e/enterprise-harness-chains.spec.ts`
  - `apps/agent-console/e2e/model-pricing.enterprise.spec.ts`
  - `apps/agent-console/e2e/fixtures/enterpriseHarness.ts`
  - `apps/agent-console/src/app/__tests__/routeInventory.test.tsx`
  - `services/api-server/tests/test_enterprise_harness_chains.py`
  - `services/api-server/tests/test_workspace_subagent_enterprise_flow.py`
  - `services/api-server/tests/test_team_subagent_enterprise_flow.py`
- Added official-source pricing data and seed coverage:
  - `services/api-server/app/settings/model_pricing_sources.json`
  - `services/api-server/app/settings/model_pricing_sources.py`
  - `services/api-server/alembic/versions/20260606_0033_seed_builtin_model_pricing_sources.py`
  - `services/api-server/tests/test_model_pricing_sources.py`
- Current source-backed rows cover DeepSeek Flash/Pro, OpenAI `gpt-5.5` only, Kimi `kimi-k2.6`, Moonshot `moonshot-v1-8k`, and Z.AI `glm-5.1` / `glm-5-turbo`. Stale OpenAI variants and removed provider-family target rows must not be reintroduced.
- The previously listed legacy provider preset was removed from the target app/test surface by user direction and must not be reintroduced as a blocked pricing row.
- Observability and Eval cost paths now require exact pricing rows for official-source models; fallback/default pricing remains allowed only for custom models without an official-source row.
- Team Mode assigned work now creates durable subagent projection evidence with AdminAuditEvent rows and lifecycle coverage for completion, owner removal, reassignment, and deletion.
- The enterprise browser fixture now fails closed with structured unhandled API records containing `method`, `path`, `query`, and caller `pageUrl`.
- Code review blockers were addressed:
  - Verified source rows are exactly mirrored by the migration seed, including Kimi, Moonshot, and Z.AI.
  - Official-source models cannot use fallback/default pricing in Observability or Eval cost paths.
  - Source hashes are asserted as `sha256(source_excerpt)`.
  - Cancelled Team projections cannot be reactivated on reassignment.
  - The temporary older OpenAI official seed row is removed by id during upgrade if a local database saw it before the latest-model correction.
  - Generated Python bytecode was removed from the workspace.
  - OpenAI frontend presets now use `272000` context tokens to match the official `<272K context length` pricing rows instead of advertising a longer context against short-context costs.
  - `team_task_update` now passes the explicit owner-update guard when tool args include `owner`, `owner_slot_id`, or `ownerSlotId`, with regression coverage for `owner_slot_id` reassignment.

## Execution Validation

- `cd services/api-server && .venv/bin/python -m pytest tests/test_model_pricing_sources.py tests/test_observability_cost_rollup.py tests/test_team_subagent_enterprise_flow.py tests/test_enterprise_harness_chains.py tests/test_workspace_subagent_enterprise_flow.py tests/test_evals.py::test_eval_run_enterprise_cost_gate_blocks_unresolved_pricing tests/test_evals.py::test_eval_run_cost_missing_pricing_records_zero_cost_and_misses tests/test_evals.py::test_eval_run_grades_cost_contract_with_model_pricing tests/test_evals.py::test_eval_run_cost_contract_allows_custom_model_with_org_pricing tests/test_evals.py::test_eval_run_cost_contract_blocks_builtin_source_model_from_fallback_pricing -q` -> `23 passed`.
- `cd services/api-server && .venv/bin/python -m ruff check app/settings/model_pricing_sources.py app/teams/service.py app/api/settings.py app/api/evals/graders/cost.py app/observability/cost_rollup.py tests/test_model_pricing_sources.py tests/test_observability_cost_rollup.py tests/test_evals.py tests/test_team_subagent_enterprise_flow.py tests/test_enterprise_harness_chains.py tests/test_workspace_subagent_enterprise_flow.py alembic/versions/20260606_0033_seed_builtin_model_pricing_sources.py` -> passed.
- `cd services/api-server && DATABASE_URL=sqlite:////tmp/harness-pricing-0033.sqlite AUTH_JWT_SECRET=test-harness-jwt-secret-32-characters-min .venv/bin/python -m alembic upgrade head` -> reached `20260606_0033`.
- `python3 scripts/check-migration-ids.py services/api-server/alembic/versions/` -> passed.
- `cd apps/agent-console && npm test -- ModelSettingsPage.test.tsx routeInventory.test.tsx --run --pool forks --poolOptions.forks.singleFork` -> `7 passed`.
- `cd apps/agent-console && npm run lint -- --pretty false` -> passed.
- `cd apps/agent-console && npm run build` -> passed.
- `cd apps/agent-console && npx playwright test --project=chromium e2e/model-pricing.enterprise.spec.ts e2e/enterprise-harness-chains.spec.ts` -> `8 passed`.
- `cd apps/agent-console && HARNESS_ALLOW_MISSING_PHASE0B_EVIDENCE=1 npm run e2e:smoke:release` -> `49 passed`.
- `cd apps/agent-console && npx playwright test --project=chromium e2e/sidebar-enterprise.smoke.spec.ts` -> `38 passed`.
- `cd apps/agent-console && npx playwright test --project=chromium e2e/model-pricing.enterprise.spec.ts e2e/enterprise-harness-chains.spec.ts e2e/sidebar-enterprise.smoke.spec.ts` -> `46 passed` after the structured unhandled-API fixture and OpenAI context-window review fix.

## OpenAI 5.5 And Chinese Help Final Review

- Model Settings now presents the visible OpenAI preset as `OpenAI GPT-5.5` with a single OpenAI built-in target, while the internal `openai-compatible/gpt-5.5` key remains only in backend source-contract internals and tests.
- Final review fixed the built-in model cost table so pricing `mode=openai-compatible` no longer appears as user-facing copy; it now renders as Chinese text.
- Dashboard/onboarding help-entry copy and the Help Center corpus were tightened to Chinese-first wording. Necessary identifiers such as API, Docker, MCP, RAG, Eval, Trace, RBAC, JWT, SSE, Postgres, Redis, USD, SKU, JSON, paths, commands, and status enum values remain searchable technical terms.
- `scripts/check-help-content.py` now blocks old English help/product phrases including `Run Detail`, `Prompt Manifest`, `Run Manifest`, `Context Manifest`, `Tool Call`, `Demo Run`, `Demo Task`, and `Team Mode`.
- Final validation for this follow-up:
  - `rg -n "\b(Agent Console|Agent Studio|Agent Workspace|Agent Run|Run Detail|Prompt Manifest|Run Manifest|Context Manifest|Tool Call|Demo Run|Demo Task|Team Mode|Help Center|Quickstart|Troubleshooting|Specialist routing|Retention, export|Cost dashboard|Trace explorer)\b" apps/agent-console/public/help apps/agent-console/src/features/help apps/agent-console/src/features/dashboard/pages/DashboardPage.tsx apps/agent-console/src/features/onboarding/pages/OnboardingWizardPage.tsx` -> no matches.
  - `cd apps/agent-console && npm test -- ModelSettingsPage.test.tsx HelpCenter.test.tsx --run --pool forks --poolOptions.forks.singleFork` -> `5 passed`.
  - `cd services/api-server && .venv/bin/python -m pytest tests/test_model_pricing_sources.py tests/test_observability_cost_rollup.py tests/test_evals.py::test_eval_run_cost_contract_blocks_builtin_source_model_from_fallback_pricing tests/test_settings.py -q` -> `20 passed`.
  - `cd apps/agent-console && npm run lint -- --pretty false` -> passed.
  - `cd apps/agent-console && npm run build` -> passed.
  - `cd services/api-server && .venv/bin/python -m ruff check app/settings/model_pricing_sources.py app/agents/model_gateway.py app/api/settings.py tests/test_model_pricing_sources.py tests/test_observability_cost_rollup.py tests/test_evals.py tests/test_settings.py` -> passed.
  - `python3 scripts/check-help-content.py` -> passed.
  - `python3 scripts/validate-docs.py` -> passed.
  - `git diff --check` -> passed.

## Residual Risk

- Live provider pricing refresh is still a manual official-source capture path; normal CI validates the checked-in source contract and exact seed projection.
- Team Mode projections are explicit `team_mode_enterprise_projection` evidence, not live specialist execution output; UI/API consumers should keep that source label visible when interpreting metrics.
