# WarmPool Benchmark Report

## Latest Local Run

```yaml
timestamp: "2026-06-20T19:59:55.705068"
environment: local-dev
api_server: "uvicorn app.main:app --host 127.0.0.1 --port 18080"
database: "isolated SQLite file seeded with 1 IDLE WarmPoolContainer"
endpoint: "POST /api/sandboxes/warm-pool/benchmark"
request_body:
  iterations: 30
mode: projection
sample_size: 30
target:
  warm_p95_ms: "<50"
result:
  status: PASS
  warm_p95_ms: 1
  warm_avg_ms: 0
  cold_avg_ms: 275
  cold_avg_note: "synthetic baseline"
  hit_rate: 100
```

Pass/fail: **PASS**. The measured warm reserve p95 was `1ms`, below the
`<50ms` target.

The cold-start comparison is the benchmark runner's deterministic synthetic
baseline (`100-500ms`) rather than a live Docker cold allocation.

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
