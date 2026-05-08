# Benchmark Spec

## WarmPool Targets

- Cold start baseline: 100-500 ms
- WarmPool target: less than 50 ms
- `min_ready`: 2
- `max_ready`: 5

## Benchmark Scenarios

- Sandbox cold allocation latency
- WarmPool reserve latency
- Subagent fanout latency
- Assignment queue wait time
- Eval run grading latency

## Required Report

Benchmark report includes p50, p95, p99, sample size, environment, and pass/fail against target.
