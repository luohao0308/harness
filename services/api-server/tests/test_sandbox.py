from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import sandboxes as sandboxes_api
from app.db.models import SandboxInstance, Task, utc_now
from app.events.event_store import EventStore
from app.main import app
from app.sandbox.docker_manager import DockerManager
from app.tools.shell import ShellTool, ShellToolRequest


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

    listed = client.get("/api/sandboxes")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == sandbox.id

    warm_pool = client.get("/api/sandboxes/warm-pool")
    assert warm_pool.status_code == 200
    assert warm_pool.json()["min_size"] == 3

    fetched = client.get(f"/api/sandboxes/{sandbox.id}")
    assert fetched.status_code == 200

    terminated = client.post(f"/api/sandboxes/{sandbox.id}/terminate")
    assert terminated.status_code == 202
    assert terminated.json()["status"] == "DESTROYED"
    refreshed = db_session.get(SandboxInstance, sandbox.id)
    assert refreshed is not None
    assert refreshed.destroyed_at is not None
