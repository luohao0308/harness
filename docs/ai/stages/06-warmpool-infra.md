# Stage 6: WarmPool And Infra Display

## Goal

Show production infrastructure value: fast sandbox startup, tenant boundaries, API surface, and release readiness.

## Input

- WarmPool status.
- Sandbox instances.
- Benchmark reports.
- Model and service health.

## Output

- `/sandboxes` displays WarmPool and sandbox lifecycle state.
- Benchmark records warm avg, warm p95, cold baseline, hit rate, and target status.
- Infra entries for tenant, API Gateway, version, and rollout are visible with real readiness state.

## Modules

- WarmPool Manager
- Sandbox Manager
- Benchmark Runner
- Observability health
- Settings models

## API And Schema Changes

- Keep `GET /api/sandboxes/warm-pool`.
- Keep `POST /api/sandboxes/warm-pool/benchmark`.
- Keep `GET /api/sandboxes/warm-pool/benchmarks`.
- Keep service health and model health APIs.

## Event Types

- `SANDBOX_REQUESTED`
- `SANDBOX_ALLOCATED`
- `SANDBOX_REUSED_FROM_WARM_POOL`
- `SANDBOX_RELEASED`
- `SANDBOX_DESTROYED`
- WarmPool benchmark records are persisted report rows.

## Frontend Display

- `/sandboxes` shows idle, busy, failed, hit, miss, benchmark reports, and sandbox rows.
- Infra entries for multi-tenant isolation, API Gateway, and rollout render with API-backed state or disabled state.
- No fake benchmark metrics.

## Tests

- Backend sandbox and WarmPool tests cover acquire, release, status, benchmark.
- Frontend build covers `/sandboxes` and observability health display.
- Docker smoke verifies service wiring.

## Acceptance

- WarmPool target is visible.
- Benchmark result persists and reloads.
- Sandbox state comes from API.
- Docker smoke passes with website retained.

## Not Doing

- No Firecracker runtime implementation.
- No Kubernetes deployment path.
- No fake multi-region rollout.

## Vertical Slice Demo

```text
Open /sandboxes
-> run WarmPool benchmark
-> inspect persisted benchmark result
-> create Agent Run needing sandbox
-> inspect sandbox and event records
```
