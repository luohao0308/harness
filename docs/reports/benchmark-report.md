# WarmPool Benchmark Report

## Scope

WarmPool Benchmark records the reserve path latency for prewarmed sandbox capacity and compares it against a cold start baseline.

## Target

```text
WarmPool reserve target: <50 ms
Cold start baseline: 100-500 ms
Default min_ready: 3
Default max_ready: 10
```

## Implemented Flow

```text
Open Sandboxes page
-> read WarmPool status
-> run Benchmark
-> store benchmark report
-> show warm avg, warm p95, cold avg, hit rate, status
```

## API Surface

```text
GET  /api/sandboxes/warm-pool
POST /api/sandboxes/warm-pool/benchmark
GET  /api/sandboxes/warm-pool/benchmarks
```

## Stored Report Fields

```ts
{
  target_startup_ms: number
  iteration_count: number
  warm_avg_ms: number
  warm_p95_ms: number
  cold_avg_ms: number
  hit_rate: number
  status: "PASS" | "WARN"
  report_json: object
}
```

## Verification

```text
cd services/api-server && .venv/bin/python -m pytest tests/test_warm_pool.py tests/test_sandbox.py
cd apps/agent-console && npm run build
```

## Portfolio Signal

The project demonstrates performance engineering inside the Agent Harness: sandbox startup is measured, benchmarked, stored, and visible in the console.
