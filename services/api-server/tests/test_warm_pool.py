from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.models import SystemSetting, Task, utc_now
from app.events.event_store import EventStore
from app.sandbox.docker_manager import DockerManager
from app.sandbox.warm_pool import (
    WARM_POOL_IDLE_TTL_SECONDS,
    WARM_POOL_MAX_SIZE,
    WARM_POOL_MIN_SIZE,
    WarmPoolManager,
)


class FakeContainer:
    def __init__(self, container_id: str) -> None:
        self.id = container_id

    def remove(self, *, force: bool) -> None:
        return None


class FakeContainers:
    def __init__(self) -> None:
        self.run_calls: list[dict[str, Any]] = []
        self.containers: dict[str, FakeContainer] = {}

    def run(self, **kwargs: Any) -> FakeContainer:
        container = FakeContainer(f"warm-container-{len(self.containers) + 1}")
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
        title="Warm pool demo",
        goal="Acquire sandbox quickly",
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


def test_warm_pool_prewarm_acquire_and_release(db_session: Session) -> None:
    task = create_task(db_session)
    fake_client = FakeDockerClient()
    manager = WarmPoolManager(docker_manager=DockerManager(client=fake_client))

    manager.prewarm(session=db_session)

    assert WARM_POOL_MIN_SIZE == 3
    assert WARM_POOL_MAX_SIZE == 10
    assert WARM_POOL_IDLE_TTL_SECONDS == 600
    assert len(fake_client.containers.run_calls) == 3
    assert manager.status(session=db_session).idle == 3

    sandbox = manager.acquire(session=db_session, task_id=task.id)

    assert sandbox.warm_pool_reused is True
    assert manager.status(session=db_session).hit_total == 1
    assert manager.status(session=db_session).idle == 2
    assert manager.status(session=db_session).busy == 1
    events = EventStore(db_session).list_by_task(task_id=task.id)
    assert [event.event_type for event in events] == [
        "SANDBOX_REQUESTED",
        "SANDBOX_ALLOCATED",
        "SANDBOX_REUSED_FROM_WARM_POOL",
    ]

    manager.release(session=db_session, sandbox=sandbox)

    assert manager.status(session=db_session).idle == 3
    assert manager.status(session=db_session).busy == 0
    assert EventStore(db_session).list_by_task(task_id=task.id)[-1].event_type == "SANDBOX_RELEASED"


def test_warm_pool_bypasses_pool_when_policy_requires_network(db_session: Session) -> None:
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
                "sandbox": {"default_network": True, "default_timeout_seconds": 60},
                "audit": {"model_calls": True, "tool_calls": True, "policy_actions": True},
            },
            updated_by="dev-admin",
            updated_at=utc_now(),
        )
    )
    db_session.flush()
    fake_client = FakeDockerClient()
    manager = WarmPoolManager(docker_manager=DockerManager(client=fake_client))
    manager.prewarm(session=db_session)

    sandbox = manager.acquire(session=db_session, task_id=task.id)

    assert sandbox.warm_pool_reused is False
    assert sandbox.network_enabled is True
    assert len(fake_client.containers.run_calls) == 4
    assert fake_client.containers.run_calls[-1]["network_mode"] == "bridge"
    assert manager.status(session=db_session).miss_total == 1


def test_warm_pool_bypasses_pool_for_custom_resources(db_session: Session) -> None:
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
                    "default_network": False,
                    "default_timeout_seconds": 60,
                    "memory_mb": 2048,
                    "cpus": "2.0",
                    "workspace_quota_mb": 2048,
                    "network_allowlist": [],
                },
                "audit": {"model_calls": True, "tool_calls": True, "policy_actions": True},
            },
            updated_by="dev-admin",
            updated_at=utc_now(),
        )
    )
    db_session.flush()
    fake_client = FakeDockerClient()
    manager = WarmPoolManager(docker_manager=DockerManager(client=fake_client))
    manager.prewarm(session=db_session)

    sandbox = manager.acquire(session=db_session, task_id=task.id)

    assert sandbox.warm_pool_reused is False
    assert sandbox.memory_limit_mb == 2048
    assert sandbox.cpu_limit == "2.0"
    assert len(fake_client.containers.run_calls) == 4
    assert fake_client.containers.run_calls[-1]["mem_limit"] == "2048m"
    assert fake_client.containers.run_calls[-1]["nano_cpus"] == 2_000_000_000
