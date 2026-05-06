#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, request
from urllib.parse import urlencode


API_BASE_URL = "http://127.0.0.1:8000"
CONSOLE_BASE_URL = "http://127.0.0.1:5173"
WEBSITE_BASE_URL = "http://127.0.0.1:3000"
NGINX_BASE_URL = "http://127.0.0.1:8080"
PROMETHEUS_BASE_URL = "http://127.0.0.1:9091"
GRAFANA_BASE_URL = "http://127.0.0.1:3001"
LOKI_BASE_URL = "http://127.0.0.1:3100"
AUTH_HEADERS = {"Authorization": "Bearer dev-engineer-token"}


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

    def get_json(self, path: str, *, auth: bool = True) -> dict:
        return self.request_json("GET", path, auth=auth)

    def post_json(self, path: str, payload: dict | None = None, *, auth: bool = True) -> dict:
        return self.request_json("POST", path, payload=payload or {}, auth=auth)

    def request_json(
        self,
        method: str,
        path: str,
        *,
        payload: dict | None = None,
        auth: bool = True,
    ) -> dict:
        headers = {"Content-Type": "application/json"}
        if auth:
            headers.update(AUTH_HEADERS)
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        http_request = request.Request(
            API_BASE_URL + path,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with request.urlopen(http_request, timeout=15) as response:
                body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise AssertionError(f"{method} {path} -> {exc.code}: {body}") from exc
        return json.loads(body)

    def get_text_url(self, url: str) -> str:
        with request.urlopen(url, timeout=15) as response:
            return response.read().decode("utf-8", errors="replace")

    def get_json_url(self, url: str, headers: dict[str, str] | None = None) -> dict:
        http_request = request.Request(url, headers=headers or {}, method="GET")
        with request.urlopen(http_request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))

    def print_summary(self) -> None:
        for result in self.results:
            mark = "PASS" if result.ok else "FAIL"
            print(f"{mark} {result.name} {result.detail}")


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    client = SmokeClient()
    try:
        health = client.check("API health", lambda: client.get_json("/health", auth=False))
        assert_true(health["status"] == "ok", "API health status is not ok")

        client.check("Console index", lambda: assert_true("root" in client.get_text_url(CONSOLE_BASE_URL), "console html missing root"))
        client.check("Website index", lambda: assert_true("html" in client.get_text_url(WEBSITE_BASE_URL).lower(), "website html missing html"))
        client.check("Nginx health", lambda: assert_true("ok" in client.get_text_url(NGINX_BASE_URL + "/health"), "nginx health missing ok"))
        client.check("Prometheus health", lambda: assert_true("Healthy" in client.get_text_url(PROMETHEUS_BASE_URL + "/-/healthy"), "prometheus unhealthy"))
        client.check("Grafana health", lambda: assert_true("database" in client.get_text_url(GRAFANA_BASE_URL + "/api/health"), "grafana health missing database"))
        client.check("Loki ready", lambda: assert_true("ready" in client.get_text_url(LOKI_BASE_URL + "/ready").lower(), "loki not ready"))

        openapi = client.check("OpenAPI", lambda: client.get_json("/openapi.json", auth=False))
        assert_true("/api/tasks" in openapi["paths"], "OpenAPI missing /api/tasks")

        task = client.check(
            "Task create",
            lambda: client.post_json(
                "/api/tasks",
                {
                    "title": f"Docker smoke {int(time.time())}",
                    "goal": "验证任务、计划、事件、Replay、Subagent、工具和观测链路",
                    "model_provider": "openai-compatible",
                    "model_name": "default",
                    "max_runtime_seconds": 1800,
                    "max_subagents": 5,
                    "enable_sandbox": True,
                    "enable_network": False,
                },
            ),
        )
        task_id = task["id"]

        started = client.check("Task start", lambda: client.post_json(f"/api/tasks/{task_id}/start"))
        assert_true(started["status"] in {"COMPLETED", "WAITING_SUBAGENTS", "RUNNING"}, f"unexpected task status {started['status']}")

        plan = client.check("Plan query", lambda: client.get_json(f"/api/tasks/{task_id}/plan"))
        assert_true(len(plan["steps"]) >= 1, "plan has no steps")

        steps = client.check("Step query", lambda: client.get_json(f"/api/tasks/{task_id}/steps"))
        assert_true(len(steps["items"]) >= 1, "steps empty")

        events = client.check("Event query", lambda: client.get_json(f"/api/tasks/{task_id}/events"))
        assert_true(len(events["items"]) >= 1, "events empty")
        last_sequence = events["items"][-1]["sequence"]

        replay = client.check(
            "Replay",
            lambda: client.post_json(f"/api/tasks/{task_id}/replay", {"sequence": last_sequence}),
        )
        assert_true(replay["sequence"] == last_sequence, "replay sequence mismatch")

        tool_execution = client.check(
            "Tool execute",
            lambda: client.post_json(
                f"/api/tasks/{task_id}/tools/execute",
                {"tool_name": "list_files", "input_json": {"root": ".", "glob": "*.py"}},
            ),
        )
        assert_true(tool_execution["tool_call"]["status"] == "SUCCESS", "tool execution failed")

        tool_calls = client.check("Tool audit", lambda: client.get_json(f"/api/tasks/{task_id}/tool-calls"))
        assert_true(len(tool_calls["items"]) >= 1, "tool audit empty")

        model_calls = client.check("Model audit", lambda: client.get_json(f"/api/tasks/{task_id}/model-calls"))
        assert_true(len(model_calls["items"]) >= 1, "model audit empty")

        subagent = client.check(
            "Subagent create",
            lambda: client.post_json(
                f"/api/tasks/{task_id}/subagents",
                {
                    "assignment": {
                        "step_key": "smoke_subagent",
                        "description": "验证子 Agent 创建与恢复接口",
                    },
                    "timeout_seconds": 120,
                    "enqueue": False,
                },
            ),
        )
        assert_true(subagent["status"] == "PENDING", "subagent not pending")

        subagents = client.check("Subagent list", lambda: client.get_json(f"/api/tasks/{task_id}/subagents"))
        assert_true(any(item["id"] == subagent["id"] for item in subagents["items"]), "created subagent missing")

        recovery = client.check(
            "Subagent recovery",
            lambda: client.post_json(
                f"/api/tasks/{task_id}/subagents/recover",
                {"stale_after_seconds": 1, "enqueue": False},
            ),
        )
        assert_true("recovered" in recovery, "recovery response missing recovered")

        result = client.check("Task result", lambda: client.get_json(f"/api/tasks/{task_id}/result"))
        assert_true(result["last_sequence"] >= last_sequence, "result sequence did not advance")

        summary = client.check("Observability summary", lambda: client.get_json("/api/observability/summary"))
        assert_true("task_total" in summary, "observability summary missing task_total")

        service_health = client.check(
            "Observability service health",
            lambda: client.get_json("/api/observability/services/health"),
        )
        assert_true(len(service_health["services"]) >= 1, "service health empty")
        assert_true(
            any(item["status"] in {"ok", "healthy"} for item in service_health["services"]),
            "all observability services are unreachable",
        )

        metrics = client.check("Metrics", lambda: client.get_text_url(API_BASE_URL + "/metrics"))
        assert_true("agent_tasks_total" in metrics, "metrics missing agent_tasks_total")

        prometheus_targets = client.check(
            "Prometheus targets",
            lambda: client.get_text_url(PROMETHEUS_BASE_URL + "/api/v1/targets"),
        )
        assert_true(
            "subagent-recovery" in prometheus_targets,
            "prometheus missing subagent-recovery target",
        )

        prometheus_rules = client.check(
            "Prometheus alert rules",
            lambda: client.get_text_url(PROMETHEUS_BASE_URL + "/api/v1/rules"),
        )
        assert_true(
            "HarnessSubagentRecoveryServiceDown" in prometheus_rules,
            "prometheus missing recovery alert rule",
        )

        grafana_dashboards = client.check(
            "Grafana provisioned dashboard",
            lambda: client.get_json_url(
                GRAFANA_BASE_URL + "/api/search?query=Agent%20Harness",
                headers={"Authorization": "Basic YWRtaW46YWRtaW4="},
            ),
        )
        assert_true(
            any(item.get("uid") == "agent-harness" for item in grafana_dashboards),
            "grafana missing provisioned Agent Harness dashboard",
        )

        grafana_datasources = client.check(
            "Grafana provisioned datasources",
            lambda: client.get_json_url(
                GRAFANA_BASE_URL + "/api/datasources",
                headers={"Authorization": "Basic YWRtaW46YWRtaW4="},
            ),
        )
        datasource_uids = {item.get("uid") for item in grafana_datasources}
        assert_true({"prometheus", "loki"}.issubset(datasource_uids), "grafana datasources missing")

        def query_loki_api_logs() -> dict:
            now_ns = int(time.time() * 1_000_000_000)
            params = urlencode(
                {
                    "query": '{app="agent-harness",service="api-server"}',
                    "limit": "20",
                    "start": str(now_ns - 15 * 60 * 1_000_000_000),
                    "end": str(now_ns),
                }
            )
            return client.get_json_url(LOKI_BASE_URL + f"/loki/api/v1/query_range?{params}")

        loki_logs = None
        for _ in range(12):
            loki_logs = client.check("Loki API logs", query_loki_api_logs)
            if loki_logs.get("data", {}).get("result"):
                break
            time.sleep(5)
        assert_true(
            bool(loki_logs and loki_logs.get("data", {}).get("result")),
            "loki has no api-server logs",
        )
    except Exception as exc:
        client.print_summary()
        print(f"FAIL detail {exc}")
        return 1

    client.print_summary()
    return 0


if __name__ == "__main__":
    sys.exit(main())
