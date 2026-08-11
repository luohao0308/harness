# Session 2026-05-29 Docs Help Performance Scale

Category: `session-log`

Tags: `documentation`, `help-center`, `performance`, `scale`, `pagination`, `query-cache`, `cdn`, `load-test`, `runbook`

## Summary

P4 documentation/help-center and P8 performance/scale are verified locally on branch `p7-release-demo-hardening`.

Delivered P4:

- Reworked `README.md` as the private-operator entry point with links to specs, runbooks, API docs, troubleshooting, screenshots, and demo assets.
- Added in-app Help Center routes plus public help Markdown content, glossary/tooltips, Dashboard walkthrough affordances, and troubleshooting coverage.
- Added OpenAPI metadata, generated `docs/contracts/api-reference/README.md` and `docs/contracts/api-reference/openapi.json`, and a docs workflow that gates help content plus generated API docs.

Delivered P8:

- Added Redis-first query caching with memory fallback, entity-version invalidation, and metrics.
- Added HMAC-signed cursor pagination and applied it to high-volume list surfaces.
- Added N+1 query detection instrumentation, lazy frontend route loading, cursor-based Run History loading, CDN/static asset configs, k6 load scripts, and the performance runbook.

## Review Fixes

Manual dual-lens code review found issues that were fixed before completion:

- Cursor tokens were unsigned base64 JSON. They are now HMAC signed with the auth secret and have tamper regression coverage.
- Agent list cache entries could retain stale capability attachment snapshots after Token Optimizer or capability writes. Cache version bumps now cover those write paths.
- Query cache state could leak between backend tests. Test setup now clears memory cache state and disables Redis fallback around each test.
- Specialist calibration depended on later subagent outputs and was not safe to cache by org/window, so that cache was removed.
- Cost rollup cache/rate-limit behavior is now covered: same-parameter repeat calls use the cache, while different misses still rate-limit.

## Validation

- `cd services/api-server && .venv/bin/pytest tests/test_query_cache.py tests/test_pagination.py tests/test_n_plus_one.py -q` -> passed.
- `cd services/api-server && .venv/bin/ruff check app tests` -> passed.
- `cd services/api-server && .venv/bin/pytest tests -q` -> `527 passed, 2 warnings`.
- `cd apps/agent-console && npm test -- HelpCenter.test.tsx RunHistoryPage.test.tsx ConsoleShell.render.test.tsx --run` -> passed.
- `cd apps/agent-console && npm test -- --run --pool forks --poolOptions.forks.singleFork` -> `49 files / 224 tests` passed.
- `cd apps/agent-console && npm run lint -- --pretty false` -> passed.
- `cd apps/agent-console && npm run build && ../../scripts/check-bundle-size.sh dist` -> passed; largest JavaScript chunk was `479206` bytes under the `512000` byte gate.
- `python3 scripts/check-help-content.py` -> `help content ok: docs=25 troubleshooting_cases=51`.
- `python3 scripts/generate-api-docs.py` -> regenerated API reference docs.
- `python3 scripts/validate-docs.py` -> passed.
- `bash -n scripts/upload-assets-to-s3.sh` -> passed.
- `POSTGRES_PASSWORD=example REDIS_PASSWORD=example SECRET_KEY=example HARNESS_DOMAIN=localhost CADDY_DOMAIN=localhost docker compose -f compose.production.yml config` -> passed.
- `git diff --check` -> passed.

## Remaining Gaps

- Live k6 baseline/spike/soak runs were not executed locally.
- S3/CloudFront upload and invalidation were syntax-checked only.
- Docker image build/push and live CDN/browser smoke were not run in this local environment.
