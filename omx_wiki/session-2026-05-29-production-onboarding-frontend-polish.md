# Session 2026-05-29 Production Onboarding Frontend Polish

Category: `session-log`

Tags: `agent-knowledge-harness`, `production`, `deployment`, `onboarding`, `frontend-polish`, `observability`, `task-progress`

## Summary

P1 Production Deployment Hardening v1, P2 Onboarding & First-Run Experience v1, and P5 Frontend Polish & UX v1 are implemented and verified locally on `p7-release-demo-hardening`.

The slice makes the private Harness easier to hand to customers: production compose and Caddy assets exist, readiness/liveness and migrations are covered, onboarding and demo data now have API/UI flows, and the console has ErrorBoundary, frontend error capture, reconnecting SSE, skeleton/empty states, and virtualized run history.

## Delivered Scope

- Added production deployment assets:
  - `compose.production.yml`;
  - `deploy/caddy/Caddyfile`;
  - `deploy/helm/harness/`;
  - `scripts/backup-postgres.sh`;
  - `scripts/restore-postgres.sh`.
- Added backend health and lifecycle hardening:
  - `/api/health/liveness`;
  - `/api/health/readiness`;
  - FastAPI lifespan shutdown marker;
  - SSE Last-Event-ID replay support.
- Added external alert notification channels:
  - `notification_channels` migration/model/API;
  - Slack, email, and webhook dispatch;
  - alert evaluator dispatch evidence in `AlertEvent.context_json`;
  - Console CRUD UI in the Alert Rules surface.
- Added onboarding and demo loading:
  - `user_onboarding_state` migration/model/API;
  - `/api/demo/load` and `/api/demo/reset`;
  - deterministic demo Agents, Knowledge sources, Eval dataset/cases, and historical task;
  - Dashboard first route and four-step onboarding wizard.
- Added frontend resilience and polish:
  - app-level and route-level ErrorBoundary;
  - frontend error reporter, `/api/frontend-errors`, and `/settings/frontend-errors`;
  - reconnecting SSE client and `useSSE`;
  - localized error feedback;
  - Skeleton, EmptyState, QuickActionFAB, and VirtualList components;
  - Run History virtualized rendering.

## Code Review Fixes

Code review found and fixed two real issues before completion:

- Notification channels accepted arbitrary URL schemes for Slack/Webhook targets. Verified Slack/Webhook channels now require absolute HTTP(S) URLs, and dispatch validates the URL again before sending.
- The Caddy config originally used `handle_path /api/*`, which would strip the `/api` prefix before proxying to FastAPI. It now uses `handle /api/*` so backend routes stay intact.

The TeamPages full-suite concurrency failure was also resolved by excluding transient streaming placeholders from persisted branch groups. Real assistant turns still form branches after they land in session history.

## Validation Evidence

```text
cd services/api-server && .venv/bin/python -m pytest tests/test_health_probes.py tests/test_notification_dispatcher.py tests/test_onboarding.py tests/test_demo_load.py tests/test_frontend_errors.py tests/test_events_stream.py tests/test_observability_alerts.py -q
18 passed

cd services/api-server && .venv/bin/python -m ruff check app tests
All checks passed

cd services/api-server && .venv/bin/python -m pytest tests -q
509 passed, 2 warnings

cd services/api-server && DATABASE_URL=sqlite:////tmp/harness-p1-p2-p5-validation.sqlite .venv/bin/python -m alembic upgrade head
passed through 20260603_0029

cd apps/agent-console && npm test -- --pool=threads
48 files / 223 tests passed

cd apps/agent-console && npm run lint -- --pretty false
passed

cd apps/agent-console && npm run build
passed

POSTGRES_PASSWORD=example REDIS_PASSWORD=example SECRET_KEY=example HARNESS_DOMAIN=localhost CADDY_DOMAIN=localhost docker compose -f compose.production.yml config
passed
```

Environment gaps:

```text
helm template harness deploy/helm/harness
not run: helm is not installed

docker run --rm -v "$PWD/deploy/caddy/Caddyfile:/etc/caddy/Caddyfile:ro" caddy:2.8-alpine caddy validate --config /etc/caddy/Caddyfile
not run: Docker daemon is unavailable
```

Docs and whitespace validation are run as final delivery checks after this page is written.

## Boundaries

- Helm assets are static chart scaffolding; live cluster install was not run.
- Caddy config was compose-rendered locally; container validation needs a running Docker daemon.
- Live Slack/email/webhook delivery was not run with real credentials; dispatcher tests cover URL validation, redaction, selector matching, and verified webhook dispatch with mocked HTTP.
- Demo seed data is deterministic local fixture data and remains marker-scoped for reset.

## Related Pages

- [[session-2026-05-18-agent-knowledge-p7-release-demo-hardening]]
- [[session-2026-05-29-post-audit-hardening-v1]]
- [[workspace-demo-ready-constraints]]
