# API Spec

## Agent Run Console

- `GET /api/agents`
- `GET /api/agents/{agent_id}`
- `POST /api/agents/{agent_id}/sessions`
- `POST /api/agents/sessions/{session_id}/messages`
- `POST /api/agents/plan`
- `POST /api/agents/auto`
- `POST /api/agents/runs/{run_id}/execute`
- `POST /api/agents/runs/{run_id}/orchestrate`
- `POST /api/agents/runs/{run_id}/orchestrate/execute`
- `POST /api/agents/runs/{run_id}/orchestrate/enqueue`
- `GET /api/agents/runs/{run_id}/assignments`
- `GET /api/agents/runs/{run_id}/handoffs`

## Tasks, Events, Replay

- `GET /api/tasks`
- `POST /api/tasks`
- `GET /api/tasks/{task_id}`
- `POST /api/tasks/{task_id}/start`
- `POST /api/tasks/{task_id}/cancel`
- `POST /api/tasks/{task_id}/resume`
- `POST /api/tasks/{task_id}/steps/resume`
- `GET /api/tasks/{task_id}/events`
- `GET /api/tasks/{task_id}/events/stream`
- `POST /api/tasks/{task_id}/replay`
- `GET /api/tasks/{task_id}/plan`
- `GET /api/tasks/{task_id}/plans`
- `GET /api/tasks/{task_id}/plans/diff`

## Tools And Sandboxes

- `POST /api/tasks/{task_id}/tools/execute`
- `GET /api/tasks/{task_id}/tool-calls`
- `GET /api/sandboxes`
- `GET /api/sandboxes/warm-pool`
- `GET /api/sandboxes/quota/usage`
- `GET /api/sandboxes/quota/history`

## Eval Harness

- `POST /api/evals/datasets`
- `GET /api/evals/datasets`
- `POST /api/evals/datasets/{dataset_id}/cases`
- `POST /api/evals/datasets/{dataset_id}/cases/from-run/{task_id}`
- `GET /api/evals/datasets/{dataset_id}/cases`
- `POST /api/evals/datasets/{dataset_id}/runs`
- `GET /api/evals/runs`
- `GET /api/evals/runs/{eval_run_id}`

## Settings And Observability

- `GET /api/settings/models`
- `PUT /api/settings/models`
- `GET /api/settings/models/health`
- `GET /api/settings/policies`
- `GET /api/observability/summary`
- `GET /api/observability/architecture`
- `GET /api/observability/logs`
- `GET /api/observability/traces/{trace_id}`
