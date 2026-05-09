from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import sandboxes as sandboxes_api
from app.db.models import SandboxInstance, SystemSetting, Task, utc_now
from app.events.event_store import EventStore
from app.main import app
from app.sandbox.docker_manager import DockerManager
from app.tools.registry import ToolRegistry
from app.tools.shell import ShellTool, ShellToolRequest
from tests.conftest import AUTH_HEADERS


@dataclass
class FakeExecResult:
    exit_code: int
    output: tuple[bytes, bytes]


class FakeContainer:
    def __init__(self, container_id: str, exec_result: FakeExecResult | None = None) -> None:
        self.id = container_id
        self.exec_result = exec_result or FakeExecResult(0, (b"ok\n", b""))
        self.exec_calls: list[dict[str, Any]] = []
        self.removed = False

    def exec_run(self, command: str, **kwargs: Any) -> FakeExecResult:
        self.exec_calls.append({"command": command, **kwargs})
        return self.exec_result

    def remove(self, *, force: bool) -> None:
        self.removed = force


class FakeContainers:
    def __init__(self) -> None:
        self.run_calls: list[dict[str, Any]] = []
        self.containers: dict[str, FakeContainer] = {}

    def run(self, **kwargs: Any) -> FakeContainer:
        container = FakeContainer(f"container-{len(self.containers) + 1}")
        self.containers[container.id] = container
        self.run_calls.append(kwargs)
        return container

    def get(self, container_id: str) -> FakeContainer:
        return self.containers[container_id]


class FakeDockerClient:
    def __init__(self) -> None:
        self.containers = FakeContainers()


def create_task(db_session: Session) -> Task:
    task = Task(
        organization_id="dev-org",
        created_by="dev-engineer",
        title="Sandbox demo",
        goal="Run isolated command",
        status="RUNNING",
        model_provider="openai-compatible",
        model_name="default",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(task)
    db_session.flush()
    return task


def test_docker_manager_creates_container_with_required_defaults(
    db_session: Session,
) -> None:
    task = create_task(db_session)
    fake_client = FakeDockerClient()
    manager = DockerManager(client=fake_client)

    sandbox = manager.create_sandbox(session=db_session, task_id=task.id)

    run_call = fake_client.containers.run_calls[0]
    assert run_call["image"] == "agent-runtime:latest"
    assert run_call["mem_limit"] == "1024m"
    assert run_call["nano_cpus"] == 1_000_000_000
    assert run_call["network_mode"] == "none"
    assert run_call["user"] == "non-root"
    assert sandbox.memory_limit_mb == 1024
    assert sandbox.cpu_limit == "1.0"
    assert sandbox.network_enabled is False
    events = EventStore(db_session).list_by_task(task_id=task.id)
    assert [event.event_type for event in events] == [
        "SANDBOX_REQUESTED",
        "SANDBOX_ALLOCATED",
    ]


def test_docker_manager_reads_sandbox_policy_settings(db_session: Session) -> None:
    task = create_task(db_session)
    db_session.add(
        SystemSetting(
            organization_id=task.organization_id,
            key="settings.policies",
            value_json={
                "risk_levels": [
                    {"name": "high", "requires_sandbox": True, "approval": "admin"}
                ],
                "approvals": {"manual_review": True, "deny_on_missing_policy": True},
                "sandbox": {
                    "default_network": True,
                    "default_timeout_seconds": 7,
                    "memory_mb": 2048,
                    "cpus": "2.5",
                    "workspace_quota_mb": 4096,
                    "network_allowlist": ["api.example.test", "*.internal.test"],
                },
                "audit": {"model_calls": True, "tool_calls": True, "policy_actions": True},
            },
            updated_by="dev-admin",
            updated_at=utc_now(),
        )
    )
    db_session.flush()
    fake_client = FakeDockerClient()
    manager = DockerManager(client=fake_client)

    sandbox = manager.create_sandbox(session=db_session, task_id=task.id)

    run_call = fake_client.containers.run_calls[0]
    assert run_call["network_mode"] == "bridge"
    assert run_call["mem_limit"] == "2048m"
    assert run_call["nano_cpus"] == 2_500_000_000
    assert run_call["labels"]["agent-harness.workspace_quota_mb"] == "4096"
    assert run_call["labels"]["agent-harness.network_allowlist"] == (
        "api.example.test,*.internal.test"
    )
    assert sandbox.network_enabled is True
    assert sandbox.memory_limit_mb == 2048
    assert sandbox.cpu_limit == "2.5"
    events = EventStore(db_session).list_by_task(task_id=task.id)
    assert events[0].payload_json["network"] == "bridge"
    assert events[0].payload_json["timeout_seconds"] == 7
    assert events[0].payload_json["workspace_quota_mb"] == 4096
    assert events[0].payload_json["network_allowlist"] == [
        "api.example.test",
        "*.internal.test",
    ]
    assert events[1].payload_json["timeout_seconds"] == 7
    assert events[1].payload_json["memory_mb"] == 2048
    assert events[1].payload_json["cpus"] == "2.5"


def test_shell_tool_runs_command_through_docker_and_records_result(
    db_session: Session,
) -> None:
    task = create_task(db_session)
    fake_client = FakeDockerClient()
    manager = DockerManager(client=fake_client)
    sandbox = manager.create_sandbox(session=db_session, task_id=task.id)
    tool = ShellTool(docker_manager=manager)

    result = tool.run(
        session=db_session,
        sandbox=sandbox,
        request=ShellToolRequest(command="pytest", timeout_seconds=10),
    )

    container = fake_client.containers.get(sandbox.container_id)
    assert container.exec_calls == [{"command": "pytest", "workdir": "/workspace", "demux": True}]
    assert result.exit_code == 0
    assert result.stdout == "ok\n"
    events = EventStore(db_session).list_by_task(task_id=task.id)
    assert [event.event_type for event in events] == [
        "SANDBOX_REQUESTED",
        "SANDBOX_ALLOCATED",
        "SANDBOX_COMMAND_STARTED",
        "SANDBOX_COMMAND_COMPLETED",
    ]


def test_docker_manager_uses_policy_timeout_when_command_timeout_missing(
    db_session: Session,
) -> None:
    task = create_task(db_session)
    db_session.add(
        SystemSetting(
            organization_id=task.organization_id,
            key="settings.policies",
            value_json={
                "risk_levels": [
                    {"name": "high", "requires_sandbox": True, "approval": "admin"}
                ],
                "approvals": {"manual_review": True, "deny_on_missing_policy": True},
                "sandbox": {"default_network": False, "default_timeout_seconds": 9},
                "audit": {"model_calls": True, "tool_calls": True, "policy_actions": True},
            },
            updated_by="dev-admin",
            updated_at=utc_now(),
        )
    )
    db_session.flush()
    fake_client = FakeDockerClient()
    manager = DockerManager(client=fake_client)
    sandbox = manager.create_sandbox(session=db_session, task_id=task.id)

    result = manager.run_command(
        session=db_session,
        sandbox=sandbox,
        command="pytest",
        timeout_seconds=None,
    )

    assert result.exit_code == 0
    events = EventStore(db_session).list_by_task(task_id=task.id)
    started = [event for event in events if event.event_type == "SANDBOX_COMMAND_STARTED"][0]
    assert started.payload_json["timeout_seconds"] == 9


def test_tool_registry_matches_stage12_required_tools() -> None:
    registry = ToolRegistry.default()

    assert {
        "read_file",
        "list_files",
        "write_file",
        "run_shell",
        "run_tests",
        "network_request",
        "git_command",
    }.issubset(set(registry.tools))
    assert registry.tools["mcp_context_search"].source == "mcp"
    assert registry.tools["mcp_artifact_put"].source == "mcp"
    for name in ["write_file", "run_shell", "run_tests", "network_request", "git_command"]:
        assert registry.tools[name].requires_sandbox is True


def test_sandbox_api_list_warm_pool_get_and_terminate(
    db_session: Session,
    monkeypatch,
) -> None:
    task = create_task(db_session)
    fake_client = FakeDockerClient()
    manager = DockerManager(client=fake_client)
    sandbox = manager.create_sandbox(session=db_session, task_id=task.id)
    db_session.commit()
    monkeypatch.setattr(sandboxes_api, "docker_manager", manager)

    client = TestClient(app)

    listed = client.get("/api/sandboxes", headers=AUTH_HEADERS)
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == sandbox.id

    warm_pool = client.get("/api/sandboxes/warm-pool", headers=AUTH_HEADERS)
    assert warm_pool.status_code == 200
    assert warm_pool.json()["min_size"] == 2

    fetched = client.get(f"/api/sandboxes/{sandbox.id}", headers=AUTH_HEADERS)
    assert fetched.status_code == 200

    terminated = client.post(f"/api/sandboxes/{sandbox.id}/terminate", headers=AUTH_HEADERS)
    assert terminated.status_code == 202
    assert terminated.json()["status"] == "DESTROYED"
    refreshed = db_session.get(SandboxInstance, sandbox.id)
    assert refreshed is not None
    assert refreshed.destroyed_at is not None


def test_sandbox_quota_usage_and_history_aggregate_policy_and_instances(
    db_session: Session,
) -> None:
    task = create_task(db_session)
    db_session.add(
        SystemSetting(
            organization_id=task.organization_id,
            key="settings.policies",
            value_json={
                "risk_levels": [
                    {"name": "high", "requires_sandbox": True, "approval": "admin"}
                ],
                "approvals": {"manual_review": True, "deny_on_missing_policy": True},
                "sandbox": {
                    "default_network": True,
                    "default_timeout_seconds": 7,
                    "memory_mb": 2048,
                    "cpus": "2.5",
                    "workspace_quota_mb": 4096,
                    "network_allowlist": ["api.example.test"],
                },
                "audit": {"model_calls": True, "tool_calls": True, "policy_actions": True},
            },
            updated_by="dev-admin",
            updated_at=utc_now(),
        )
    )
    running = SandboxInstance(
        task_id=task.id,
        container_id="running-container",
        image="agent-runtime:latest",
        status="RUNNING",
        cpu_limit="2.5",
        memory_limit_mb=2048,
        network_enabled=True,
        warm_pool_reused=True,
        created_at=utc_now(),
    )
    destroyed = SandboxInstance(
        task_id=task.id,
        container_id="destroyed-container",
        image="agent-runtime:latest",
        status="DESTROYED",
        cpu_limit="1.0",
        memory_limit_mb=1024,
        network_enabled=False,
        warm_pool_reused=False,
        created_at=utc_now(),
        destroyed_at=utc_now(),
    )
    db_session.add_all([running, destroyed])
    db_session.commit()
    client = TestClient(app)

    usage = client.get("/api/sandboxes/quota/usage", headers=AUTH_HEADERS)
    history = client.get("/api/sandboxes/quota/history", headers=AUTH_HEADERS)

    assert usage.status_code == 200
    payload = usage.json()
    assert payload["configured_memory_mb"] == 2048
    assert payload["configured_cpus"] == "2.5"
    assert payload["configured_workspace_quota_mb"] == 4096
    assert payload["configured_network_enabled"] is True
    assert payload["configured_network_allowlist"] == ["api.example.test"]
    assert payload["sandbox_total"] == 2
    assert payload["running_total"] == 1
    assert payload["destroyed_total"] == 1
    assert payload["memory_limit_mb_total"] == 3072
    assert payload["running_memory_limit_mb_total"] == 2048
    assert payload["cpu_limit_total"] == 3.5
    assert payload["running_cpu_limit_total"] == 2.5
    assert payload["network_enabled_total"] == 1
    assert payload["warm_pool_reused_total"] == 1
    assert history.status_code == 200
    items = history.json()["items"]
    assert {item["container_id"] for item in items} == {
        "running-container",
        "destroyed-container",
    }
    assert any(item["lifetime_seconds"] == 0 for item in items)
