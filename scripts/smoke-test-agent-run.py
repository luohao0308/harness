#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, request


API_BASE_URL = os.environ.get("HARNESS_API_BASE_URL", "http://127.0.0.1:8000")
HTTP_TIMEOUT_SECONDS = 120


def _bearer_headers(env_name: str, default_token: str) -> dict[str, str]:
    token = os.environ.get(env_name, "").strip() or default_token
    return {"Authorization": f"Bearer {token}"}


AUTH_HEADERS = _bearer_headers("HARNESS_AUTH_TOKEN", "dev-engineer-token")
ADMIN_HEADERS = _bearer_headers("HARNESS_ADMIN_TOKEN", "dev-admin-token")
OPERATOR_HEADERS = _bearer_headers("HARNESS_OPERATOR_TOKEN", "dev-operator-token")

REQUIRED_EVENT_CATEGORIES = {
    "planning": {"PLAN_REQUESTED", "PLAN_GENERATED"},
    "execution": {"STEP_STARTED", "STEP_COMPLETED", "STEP_FAILED"},
    "model_call": {"MODEL_CALLED", "MODEL_RESPONSE_RECEIVED"},
    "tool_call": {"TOOL_CALLED", "TOOL_RESULT_RECEIVED", "TOOL_APPROVAL_REQUESTED"},
    "sandbox": {
        "SANDBOX_REQUESTED",
        "SANDBOX_ALLOCATED",
        "SANDBOX_REUSED_FROM_WARM_POOL",
        "SANDBOX_RELEASED",
    },
    "subagent": {"SUBAGENT_SPAWNED", "SUBAGENT_STARTED", "SUBAGENT_COMPLETED"},
    "eval": {"EVAL_CASE_CREATED", "EVAL_RUN_STARTED", "EVAL_RUN_COMPLETED"},
}


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


class SmokeClient:
    def __init__(self) -> None:
        self.results: list[CheckResult] = []

    def check(self, name: str, func) -> Any:
        started_at = time.monotonic()
        try:
            value = func()
        except Exception as exc:
            self.results.append(CheckResult(name=name, ok=False, detail=str(exc)))
            raise
        duration_ms = int((time.monotonic() - started_at) * 1000)
        self.results.append(CheckResult(name=name, ok=True, detail=f"{duration_ms}ms"))
        return value

    def get_json(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        auth: bool = True,
    ) -> dict:
        return self.request_json("GET", path, headers=headers, auth=auth)

    def post_json(
        self,
        path: str,
        payload: dict | None = None,
        *,
        headers: dict[str, str] | None = None,
        auth: bool = True,
    ) -> dict:
        return self.request_json("POST", path, payload=payload or {}, headers=headers, auth=auth)

    def request_json(
        self,
        method: str,
        path: str,
        *,
        payload: dict | None = None,
        headers: dict[str, str] | None = None,
        auth: bool = True,
    ) -> dict:
        request_headers = {"Content-Type": "application/json"}
        if headers is not None:
            request_headers.update(headers)
        elif auth:
            request_headers.update(AUTH_HEADERS)

        data = None if payload is None else json.dumps(payload).encode("utf-8")
        http_request = request.Request(
            API_BASE_URL + path,
            data=data,
            headers=request_headers,
            method=method,
        )
        try:
            with request.urlopen(http_request, timeout=HTTP_TIMEOUT_SECONDS) as response:
                body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise AssertionError(f"{method} {path} -> {exc.code}: {body}") from exc
        return json.loads(body)

    def get_text_url(self, url: str) -> str:
        with request.urlopen(url, timeout=HTTP_TIMEOUT_SECONDS) as response:
            return response.read().decode("utf-8", errors="replace")

    def request_text(
        self,
        method: str,
        path: str,
        *,
        payload: dict | None = None,
        headers: dict[str, str] | None = None,
        auth: bool = True,
    ) -> str:
        request_headers = {"Content-Type": "application/json"}
        if headers is not None:
            request_headers.update(headers)
        elif auth:
            request_headers.update(AUTH_HEADERS)

        data = None if payload is None else json.dumps(payload).encode("utf-8")
        http_request = request.Request(
            API_BASE_URL + path,
            data=data,
            headers=request_headers,
            method=method,
        )
        try:
            with request.urlopen(http_request, timeout=HTTP_TIMEOUT_SECONDS) as response:
                return response.read().decode("utf-8", errors="replace")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise AssertionError(f"{method} {path} -> {exc.code}: {body}") from exc

    def print_summary(self) -> None:
        for result in self.results:
            mark = "PASS" if result.ok else "FAIL"
            print(f"{mark} {result.name} {result.detail}")


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def first_trace_id(events: list[dict]) -> str | None:
    for event in events:
        trace_id = event.get("trace_id")
        if isinstance(trace_id, str) and trace_id:
            return trace_id
    return None


def parse_sse_events(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for frame in body.strip().split("\n\n"):
        event_line = next((line for line in frame.splitlines() if line.startswith("event:")), None)
        data_line = next((line for line in frame.splitlines() if line.startswith("data:")), None)
        if event_line is None or data_line is None:
            continue
        event_name = event_line.removeprefix("event:").strip()
        payload = json.loads(data_line.removeprefix("data:").strip())
        events.append((event_name, payload))
    return events


def require_event_categories(event_types: set[str]) -> dict[str, list[str]]:
    missing: dict[str, list[str]] = {}
    for category, category_types in REQUIRED_EVENT_CATEGORIES.items():
        if not (event_types & category_types):
            missing[category] = sorted(category_types)
    return missing


def maybe_tempo_trace(client: SmokeClient, trace_id: str) -> dict | None:
    last_payload: dict | None = None
    for _ in range(12):
        payload = client.get_json(f"/api/observability/traces/{trace_id}")
        last_payload = payload
        if payload.get("source") == "tempo" and payload.get("spans"):
            return payload
        time.sleep(5)
    return last_payload


def maybe_loki_logs(client: SmokeClient, task_id: str, trace_id: str) -> dict | None:
    last_payload: dict | None = None
    for _ in range(12):
        payload = client.get_json(
            f"/api/observability/logs?task_id={task_id}&trace_id={trace_id}&event_type=TASK_CREATED&limit=20"
        )
        last_payload = payload
        if payload.get("source") == "loki" and payload.get("items"):
            return payload
        time.sleep(5)
    return last_payload


def main() -> int:
    client = SmokeClient()
    evidence: dict[str, Any] = {}
    try:
        health = client.check("API health", lambda: client.get_json("/health", auth=False))
        assert_true(health.get("status") == "ok", "API health status is not ok")

        openapi = client.check("OpenAPI", lambda: client.get_json("/openapi.json", auth=False))
        paths = openapi.get("paths", {})
        assert_true(
            "/api/agents/{agent_id}/runs" in paths,
            "OpenAPI missing /api/agents/{agent_id}/runs",
        )
        assert_true(
            "/api/agents/runs/{run_id}/workspace" in paths,
            "OpenAPI missing /api/agents/runs/{run_id}/workspace",
        )

        goal_text = (
            "Stage 07 canonical smoke: generate a real plan, run execution, "
            "exercise subagent path, and include sandbox-related steps."
        )
        run_title = f"Stage07 Agent Run Smoke {int(time.time())}"

        run_entrypoint = "POST /api/agents/default/runs"
        run_id: str
        started_at = time.monotonic()
        created = client.post_json(
            "/api/agents/default/runs",
            {
                "goal": goal_text,
                "title": run_title,
                "model_provider": "openai-compatible",
                "model_name": "default",
                "max_runtime_seconds": 1800,
                "max_subagents": 5,
                "enable_sandbox": True,
                "enable_network": False,
            },
        )
        client.results.append(
            CheckResult(
                name="Agent Run create",
                ok=True,
                detail=f"{int((time.monotonic() - started_at) * 1000)}ms",
            )
        )
        run_id = str(created["run_id"])

        task_id = run_id
        evidence["run_id"] = run_id
        evidence["task_id"] = task_id
        evidence["run_entrypoint"] = run_entrypoint

        run_list = client.check("Agent Run list", lambda: client.get_json("/api/agents/runs"))
        assert_true(
            any(item.get("id") == run_id for item in run_list.get("items", [])),
            "created run missing in /api/agents/runs",
        )

        workspace = client.check(
            "Agent Run workspace (pre-execute)",
            lambda: client.get_json(f"/api/agents/runs/{run_id}/workspace"),
        )
        assert_true(workspace.get("run", {}).get("id") == run_id, "workspace run mismatch")
        plan = workspace.get("plan")
        assert_true(plan is not None, "workspace plan is missing")
        steps = plan.get("steps", [])
        assert_true(len(steps) >= 1, "workspace plan has no steps")
        first_step = steps[0]
        assert_true("acceptance_criteria" in first_step, "plan step missing acceptance_criteria")
        assert_true("risk_level" in first_step, "plan step missing risk_level")
        assert_true("execution_trace" in first_step, "plan step missing execution_trace")

        executed = client.check(
            "Agent Run execute",
            lambda: client.post_json(f"/api/agents/runs/{run_id}/execute"),
        )
        assert_true(
            executed.get("status") == "COMPLETED",
            f"unexpected run status after execute: {executed.get('status')}",
        )

        plan_after = client.check("Plan query", lambda: client.get_json(f"/api/tasks/{task_id}/plan"))
        assert_true(len(plan_after.get("steps", [])) >= 1, "plan query returned no steps")

        steps_state = client.check(
            "Step query",
            lambda: client.get_json(f"/api/tasks/{task_id}/steps"),
        )
        assert_true(len(steps_state.get("items", [])) >= 1, "step query returned no items")

        events = client.check(
            "Event query",
            lambda: client.get_json(f"/api/tasks/{task_id}/events"),
        )
        event_items = events.get("items", [])
        assert_true(len(event_items) >= 1, "events list is empty")
        last_sequence = int(event_items[-1]["sequence"])
        evidence["event_sequence"] = last_sequence

        replay = client.check(
            "Replay",
            lambda: client.post_json(f"/api/tasks/{task_id}/replay", {"sequence": last_sequence}),
        )
        assert_true(
            int(replay.get("sequence", -1)) == last_sequence,
            "replay sequence mismatch",
        )
        evidence["replay_sequence"] = int(replay["sequence"])

        shell_exec = client.check(
            "Sandboxed tool execute",
            lambda: client.post_json(
                f"/api/tasks/{task_id}/tools/execute",
                {
                    "tool_name": "run_shell",
                    "input_json": {"command": "echo stage07_agent_run_smoke", "cwd": "/workspace"},
                    "create_sandbox": True,
                },
                headers=ADMIN_HEADERS,
                auth=False,
            ),
        )
        tool_call = shell_exec.get("tool_call", {})
        assert_true(tool_call.get("status") == "SUCCESS", "run_shell did not succeed")
        evidence["tool_call_id"] = str(tool_call["id"])
        evidence["sandbox_id"] = tool_call.get("sandbox_id")

        tool_calls = client.check(
            "Tool audit",
            lambda: client.get_json(f"/api/tasks/{task_id}/tool-calls"),
        )
        assert_true(len(tool_calls.get("items", [])) >= 1, "tool audit is empty")

        model_calls = client.check(
            "Model audit",
            lambda: client.get_json(f"/api/tasks/{task_id}/model-calls"),
        )
        assert_true(len(model_calls.get("items", [])) >= 1, "model audit is empty")

        subagent = client.check(
            "Subagent create",
            lambda: client.post_json(
                f"/api/tasks/{task_id}/subagents",
                {
                    "assignment": {
                        "step_key": "stage07_subagent_smoke",
                        "description": "Verify subagent projection and recovery path",
                    },
                    "timeout_seconds": 120,
                    "enqueue": False,
                },
            ),
        )
        evidence["subagent_id"] = str(subagent["id"])

        subagents = client.check(
            "Subagent list",
            lambda: client.get_json(f"/api/tasks/{task_id}/subagents"),
        )
        assert_true(
            any(item.get("id") == evidence["subagent_id"] for item in subagents.get("items", [])),
            "created subagent missing from list",
        )

        recovery = client.check(
            "Subagent recover",
            lambda: client.post_json(
                f"/api/tasks/{task_id}/subagents/recover",
                {"stale_after_seconds": 1, "enqueue": False},
            ),
        )
        assert_true("recovered" in recovery, "subagent recover response missing 'recovered'")

        workspace_after = client.check(
            "Agent Run workspace (post-execute)",
            lambda: client.get_json(f"/api/agents/runs/{run_id}/workspace"),
        )
        assert_true(len(workspace_after.get("events", [])) >= 1, "workspace events are empty")
        assert_true(
            len(workspace_after.get("tool_calls", [])) >= 1,
            "workspace tool_calls are empty",
        )
        assert_true(
            len(workspace_after.get("model_calls", [])) >= 1,
            "workspace model_calls are empty",
        )

        dataset = client.check(
            "Eval dataset create",
            lambda: client.post_json(
                "/api/evals/datasets",
                {
                    "name": f"Stage07 Dataset {int(time.time())}",
                    "description": "Canonical run smoke evidence dataset",
                },
            ),
        )
        eval_case = client.check(
            "Eval case from run",
            lambda: client.post_json(
                f"/api/evals/datasets/{dataset['id']}/cases/from-run/{task_id}",
                {"expected_json": {"status": "COMPLETED"}, "tags_json": ["stage07", "smoke"]},
            ),
        )
        evidence["eval_case_id"] = str(eval_case["id"])
        eval_run = client.check(
            "Eval run",
            lambda: client.post_json(
                f"/api/evals/datasets/{dataset['id']}/runs",
                {"agent_id": "default"},
            ),
        )
        evidence["eval_run_id"] = str(eval_run["id"])
        assert_true(
            eval_run.get("status") == "COMPLETED",
            f"eval run status is not COMPLETED: {eval_run.get('status')}",
        )

        summary = client.check(
            "Observability summary",
            lambda: client.get_json("/api/observability/summary"),
        )
        assert_true("task_total" in summary, "observability summary missing task_total")

        service_health = client.check(
            "Observability service health",
            lambda: client.get_json(
                "/api/observability/services/health",
                headers=OPERATOR_HEADERS,
                auth=False,
            ),
        )
        services = service_health.get("services", [])
        assert_true(len(services) >= 1, "observability service health is empty")

        metrics = client.check("Metrics", lambda: client.get_text_url(API_BASE_URL + "/metrics"))
        assert_true("agent_tasks_total" in metrics, "metrics missing agent_tasks_total")

        event_items = client.check(
            "Event query (refresh)",
            lambda: client.get_json(f"/api/tasks/{task_id}/events"),
        ).get("items", [])
        event_types = {str(item.get("event_type")) for item in event_items}
        missing_event_categories = require_event_categories(event_types)
        assert_true(
            not missing_event_categories,
            f"missing required event categories: {missing_event_categories}",
        )

        warm_pool_markers = [
            item
            for item in event_items
            if item.get("event_type")
            in {"SANDBOX_REUSED_FROM_WARM_POOL", "SANDBOX_ALLOCATED", "SANDBOX_RELEASED"}
        ]
        assert_true(
            len(warm_pool_markers) >= 1,
            "missing sandbox/warm-pool lifecycle markers in run events",
        )
        evidence["warm_pool_marker"] = str(warm_pool_markers[-1]["event_type"])

        trace_id = first_trace_id(event_items)
        assert_true(trace_id is not None, "missing trace_id from run events")
        evidence["trace_id"] = trace_id

        tempo_trace = client.check(
            "Observability trace",
            lambda: maybe_tempo_trace(client, trace_id),
        )
        assert_true(
            bool(tempo_trace and tempo_trace.get("source") == "tempo" and tempo_trace.get("spans")),
            "observability trace did not return tempo spans",
        )

        logs = client.check(
            "Observability logs",
            lambda: maybe_loki_logs(client, task_id, trace_id),
        )
        assert_true(
            bool(logs and logs.get("source") == "loki" and logs.get("items")),
            "observability logs did not return loki entries",
        )

        required_evidence_keys = [
            "run_id",
            "task_id",
            "trace_id",
            "event_sequence",
            "replay_sequence",
            "tool_call_id",
            "sandbox_id",
            "subagent_id",
            "eval_case_id",
            "eval_run_id",
            "warm_pool_marker",
        ]
        missing_keys = [key for key in required_evidence_keys if not evidence.get(key)]
        assert_true(not missing_keys, f"missing evidence keys: {missing_keys}")

        print("EVIDENCE " + json.dumps(evidence, ensure_ascii=False, sort_keys=True))
    except Exception as exc:
        client.print_summary()
        print(f"FAIL detail {exc}")
        return 1

    client.print_summary()
    return 0


if __name__ == "__main__":
    sys.exit(main())
