# Python Agent SDK Example

## Purpose

This example shows the Agent Run flow through HTTP calls. It is a lightweight SDK shape for portfolio review and integration tests.

## Example

```python
from __future__ import annotations

import requests

BASE_URL = "http://127.0.0.1:8000"
TOKEN = "dev-engineer-token"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def api(method: str, path: str, payload: dict | None = None) -> dict:
    response = requests.request(
        method,
        f"{BASE_URL}{path}",
        headers=HEADERS,
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


run = api(
    "POST",
    "/api/agents/auto",
    {
        "agent_id": "default",
        "title": "Portfolio GitHub issue demo",
        "goal": "Analyze a GitHub issue, plan the fix, run safe tools, and produce a regression-ready report.",
        "model_provider": "default",
        "model_name": "default",
        "max_runtime_seconds": 1800,
        "max_subagents": 5,
        "enable_sandbox": True,
        "enable_network": False,
    },
)

run_id = run["run_id"]
context = api("POST", f"/api/tasks/{run_id}/context/route")
events = api("GET", f"/api/tasks/{run_id}/events")
result = api("GET", f"/api/tasks/{run_id}/result")

print("run", run_id)
print("model route", context["model_routing"])
print("event count", len(events["items"]))
print("status", result["status"])
```

## SDK Contract

```text
Create Agent Run: POST /api/agents/auto
Read events: GET /api/tasks/{task_id}/events
Route context: POST /api/tasks/{task_id}/context/route
Replay: POST /api/tasks/{task_id}/replay
Save Eval Case: POST /api/evals/datasets/{dataset_id}/cases/from-run/{task_id}
Run Eval: POST /api/evals/datasets/{dataset_id}/runs
Run WarmPool Benchmark: POST /api/sandboxes/warm-pool/benchmark
```
