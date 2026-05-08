# Eval Harness Spec

## Purpose

Eval Harness turns successful and failed Agent runs into regression cases. It proves that the platform is not only an Agent runtime, but an engineering harness for measuring Agent quality over time.

## Capabilities

- Dataset management
- Eval Case creation from Agent Run
- Manual Eval Case creation
- Eval Run execution
- Trace Grader
- Regression Gate
- Human Review Queue
- Online Eval sampling
- Agent version comparison

## Current Vertical Slice

The platform supports:

```text
Create Dataset
-> Save existing Run as Eval Case
-> Execute Eval Run
-> Persist Eval Result
-> Show metrics in Console
```

## Metrics

```json
{
  "task_success_rate": 0,
  "tool_selection_accuracy": 0,
  "policy_violation_rate": 0,
  "avg_latency_ms": 0,
  "avg_cost_usd": 0,
  "retry_rate": 0,
  "human_escalation_rate": 0
}
```
