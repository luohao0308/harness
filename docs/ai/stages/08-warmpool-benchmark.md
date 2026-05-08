# Stage 8: WarmPool + Benchmark

## Goal

Prove WarmPool performance and operational behavior.

## Input

Sandbox allocation requests and benchmark config.

## Output

Benchmark report, WarmPool metrics, reserve/release trace, and console summary.

## Modules

WarmPool Manager, Sandbox Manager, benchmark scripts, metrics, console.

## API And Schema Changes

Expose `POST /api/sandboxes/warm-pool/benchmark` for persisted benchmark reports.
Expose `GET /api/sandboxes/warm-pool/benchmarks` for report history.

## Event Types

`SANDBOX_REQUESTED`, `SANDBOX_ALLOCATED`, `SANDBOX_REUSED_FROM_WARM_POOL`, `SANDBOX_RELEASED`, `SANDBOX_DESTROYED`.

## Frontend Display

Sandboxes page shows idle, busy, failed, hit rate, miss rate, benchmark status, warm avg, warm p95, cold avg, and iterations.

## Tests

WarmPool unit tests, sandbox API tests, and benchmark API smoke test.

## Acceptance

WarmPool reserve target is less than 50 ms under projection benchmark when ready capacity exists.

## Not Doing

Kubernetes cluster-level pool management is outside this stage.

## Vertical Slice Demo

```text
Start WarmPool
-> run benchmark
-> inspect hit rate and latency
-> benchmark report is stored
```
