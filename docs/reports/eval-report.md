# Eval Harness Report

## Scope

Eval Harness validates Agent Runs through datasets, cases, deterministic trace grading, metrics, and regression records.

## Implemented Flow

```text
Dataset created
-> Run saved as Eval Case
-> Eval Run starts
-> Grader checks expected status, trace evidence, tool usage, and policy violations
-> Eval Result stored
-> Metrics returned to Console
```

## Metrics

```ts
{
  task_success_rate: number
  tool_selection_accuracy: number
  policy_violation_rate: number
  avg_latency_ms: number
  avg_cost_usd: number
  retry_rate: number
  human_escalation_rate: number
}
```

## API Surface

```text
POST /api/evals/datasets
GET  /api/evals/datasets
POST /api/evals/datasets/{dataset_id}/cases
POST /api/evals/datasets/{dataset_id}/cases/from-run/{task_id}
GET  /api/evals/datasets/{dataset_id}/cases
POST /api/evals/datasets/{dataset_id}/runs
GET  /api/evals/runs
GET  /api/evals/runs/{eval_run_id}
```

## Verification

```text
cd services/api-server && .venv/bin/python -m pytest tests/test_evals.py
cd apps/agent-console && npm run build
```

## Portfolio Signal

The project includes an Eval Harness, not only an Agent Runtime. This proves regression testing, trace grading, and measurable quality control for Agent infrastructure.
