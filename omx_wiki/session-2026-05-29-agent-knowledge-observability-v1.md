# Session: Agent Knowledge Observability v1

Date: 2026-05-29
Branch: `p7-release-demo-hardening`
Scope: Observability v1 PRD execution for cost dashboard, local OpenTelemetry trace UI, and Alert/SLO rules.

## Delivered

- Added `otel_spans`, `alert_rules`, and `alert_events` with seeded default alert rules and 90-day local span retention.
- Added `/api/observability/cost-rollup` with windows `24h`, `7d`, `30d`, and `all`, grouped by agent, provider, specialist, or adapter.
- Added local SQL-backed trace listing/detail before existing Tempo/Event Store fallbacks, plus HTTP/model/tool/subagent/eval grader span emission.
- Added alert rule CRUD, default-rule org clone editing, manual and worker evaluation, event list, SSE stream, and in-app console bell.
- Added console pages for Cost, Trace, and Alerts, plus Run Detail trace deep links.

## Code Review Findings Fixed

- Real nested trace spans initially stored custom child span ids while parent ids came from OTel context; fixed with a local span stack and a regression test.
- SQLite migration initially could not seed JSON list values through an untyped `bulk_insert`; fixed by typing the seed table columns.
- Invalid cost-rollup query strings could be masked by the 10-second org rate limit; validation now runs before rate limiting.
- A stray frontend `listToolCalls` filter behavior change was outside the PRD and was reverted.
- Same `trace_id` values across organizations initially risked detail/list leakage after one accessible-span check; local trace queries now filter every span by org/task, with regression coverage.

## Drift Review

- Eval remains the owner of grounding and regression quality; Observability only projects existing Eval metrics and does not recompute grounding.
- Alert v1 remains in-app only; no Slack, PagerDuty, webhook, email, or external notification channel was added.
- Trace v1 remains private/local; no Jaeger/Grafana deployment dependency was introduced for the new pages.
- No cost budget enforcement, SLO burn-rate engine, or P5-P8/Subagent/Adapter core semantic changes were added.

## Verification

- `cd services/api-server && uv run ruff check app tests` -> passed.
- `cd services/api-server && uv run pytest tests/test_observability.py tests/test_observability_cost_rollup.py tests/test_observability_tracing.py tests/test_observability_alerts.py tests/test_evals.py tests/test_eval_regression.py -q` -> `60 passed`.
- `cd services/api-server && uv run pytest -q` -> `465 passed`.
- `cd services/api-server && DATABASE_URL=sqlite:////tmp/harness-observability-v1.sqlite uv run alembic upgrade head` -> passed through `20260529_0024`.
- `cd apps/agent-console && npm test -- ObservabilityV1Pages` -> `3 passed`.
- `cd apps/agent-console && npm test -- --run` -> `47 files / 222 tests passed`.
- `cd apps/agent-console && npm run lint -- --pretty false` -> passed.
- `cd apps/agent-console && npm run build` -> passed with the existing Vite large-chunk warning.
- `python3 scripts/validate-docs.py` -> passed.
- `git diff --check` -> passed.

## Handoff Notes

- `opentelemetry-instrumentation-fastapi` is now an explicit API-server dependency.
- The local HTTP root span is best-effort: commit failures are rolled back and do not fail API requests.
- Cost rollup is still real-time and bounded by existing query limits; daily pre-aggregation remains a future performance lane.
