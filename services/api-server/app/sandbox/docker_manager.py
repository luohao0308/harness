from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import docker
from sqlalchemy.orm import Session

from app.db.models import SandboxInstance, utc_now
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.observability.metrics import (
    sandbox_command_duration_seconds,
    sandbox_command_timeout_total,
    sandbox_containers_running,
    sandbox_containers_total,
)
from app.sandbox.policies import (
    DEFAULT_SANDBOX_IMAGE,
    DEFAULT_SANDBOX_NETWORK,
    DEFAULT_WORKSPACE_MOUNT,
    SandboxPolicyResolver,
    SandboxRuntimePolicy,
    network_enabled_from_mode,
    require_command_timeout,
)


@dataclass(frozen=True)
class SandboxCommandResult:
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int


class SandboxCommandTimeoutError(TimeoutError):
    pass


class DockerManager:
    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    def create_container(
        self,
        *,
        task_id: str,
        image: str = DEFAULT_SANDBOX_IMAGE,
        workspace_root: str | None = None,
        runtime_policy: SandboxRuntimePolicy | None = None,
    ) -> Any:
        policy = runtime_policy or SandboxRuntimePolicy(
            network_mode=DEFAULT_SANDBOX_NETWORK,
            network_enabled=network_enabled_from_mode(DEFAULT_SANDBOX_NETWORK),
            timeout_seconds=60,
        )
        volumes = None
        if workspace_root is not None:
            volumes = {
                str(Path(workspace_root).resolve()): {
                    "bind": DEFAULT_WORKSPACE_MOUNT,
                    "mode": "rw",
                }
            }
        return self.client.containers.run(
            image=image,
            command="sleep infinity",
            detach=True,
            tty=True,
            mem_limit=policy.memory,
            nano_cpus=policy.nano_cpus,
            network_mode=policy.network_mode,
            user=policy.user,
            working_dir=DEFAULT_WORKSPACE_MOUNT,
            volumes=volumes,
            labels={
                "agent-harness.task_id": task_id,
                "agent-harness.managed": "true",
            },
        )

    def create_sandbox(
        self,
        *,
        session: Session,
        task_id: str,
        agent_run_id: str | None = None,
        image: str = DEFAULT_SANDBOX_IMAGE,
        workspace_root: str | None = None,
    ) -> SandboxInstance:
        event_store = EventStore(session)
        runtime_policy = SandboxPolicyResolver(session).runtime_for_task(task_id)
        event_store.append(
            task_id=task_id,
            agent_run_id=agent_run_id,
            event_type=EventType.SANDBOX_REQUESTED,
            payload_json={
                "image": image,
                "network": runtime_policy.network_mode,
                "timeout_seconds": runtime_policy.timeout_seconds,
            },
        )
        container = self.create_container(
            task_id=task_id,
            image=image,
            workspace_root=workspace_root,
            runtime_policy=runtime_policy,
        )
        sandbox = self.record_allocated_container(
            session=session,
            task_id=task_id,
            container_id=container.id,
            agent_run_id=agent_run_id,
            image=image,
            warm_pool_reused=False,
            runtime_policy=runtime_policy,
        )
        return sandbox

    def record_allocated_container(
        self,
        *,
        session: Session,
        task_id: str,
        container_id: str,
        agent_run_id: str | None = None,
        image: str = DEFAULT_SANDBOX_IMAGE,
        warm_pool_reused: bool,
        runtime_policy: SandboxRuntimePolicy | None = None,
    ) -> SandboxInstance:
        event_store = EventStore(session)
        policy = runtime_policy or SandboxPolicyResolver(session).runtime_for_task(task_id)
        if warm_pool_reused:
            event_store.append(
                task_id=task_id,
                agent_run_id=agent_run_id,
                event_type=EventType.SANDBOX_REQUESTED,
                payload_json={
                    "image": image,
                    "network": policy.network_mode,
                    "timeout_seconds": policy.timeout_seconds,
                },
            )
        sandbox = SandboxInstance(
            task_id=task_id,
            agent_run_id=agent_run_id,
            container_id=container_id,
            image=image,
            status="IDLE",
            cpu_limit=policy.cpus,
            memory_limit_mb=policy.memory_mb,
            network_enabled=policy.network_enabled,
            warm_pool_reused=warm_pool_reused,
        )
        session.add(sandbox)
        session.flush()
        sandbox_containers_total.inc()
        sandbox_containers_running.inc()
        event_store.append(
            task_id=task_id,
            agent_run_id=agent_run_id,
            event_type=EventType.SANDBOX_ALLOCATED,
            payload_json={
                "sandbox_id": sandbox.id,
                "container_id": container_id,
                "image": image,
                "memory": policy.memory,
                "cpus": policy.cpus,
                "network": policy.network_mode,
                "user": policy.user,
                "timeout_seconds": policy.timeout_seconds,
            },
        )
        if warm_pool_reused:
            event_store.append(
                task_id=task_id,
                agent_run_id=agent_run_id,
                event_type=EventType.SANDBOX_REUSED_FROM_WARM_POOL,
                payload_json={"sandbox_id": sandbox.id, "container_id": container_id},
            )
        return sandbox

    def run_command(
        self,
        *,
        session: Session,
        sandbox: SandboxInstance,
        command: str,
        timeout_seconds: int | None,
        cwd: str = DEFAULT_WORKSPACE_MOUNT,
    ) -> SandboxCommandResult:
        runtime_policy = SandboxPolicyResolver(session).runtime_for_task(sandbox.task_id)
        effective_timeout = timeout_seconds or runtime_policy.timeout_seconds
        policy = require_command_timeout(effective_timeout)
        if not policy.allowed:
            raise ValueError(policy.reason)

        event_store = EventStore(session)
        event_store.append(
            task_id=sandbox.task_id,
            agent_run_id=sandbox.agent_run_id,
            event_type=EventType.SANDBOX_COMMAND_STARTED,
            payload_json={
                "sandbox_id": sandbox.id,
                "command": command,
                "timeout_seconds": effective_timeout,
            },
        )
        sandbox.status = "BUSY"
        session.flush()

        started = time.monotonic()
        try:
            container = self.client.containers.get(sandbox.container_id)
            executor = ThreadPoolExecutor(max_workers=1)
            try:
                future = executor.submit(container.exec_run, command, workdir=cwd, demux=True)
                exec_result = future.result(timeout=effective_timeout)
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
            stdout, stderr, exit_code = self._decode_exec_result(exec_result)
            duration_ms = int((time.monotonic() - started) * 1000)
            result = SandboxCommandResult(
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                duration_ms=duration_ms,
            )
            event_type = (
                EventType.SANDBOX_COMMAND_COMPLETED
                if exit_code == 0
                else EventType.SANDBOX_COMMAND_FAILED
            )
            event_store.append(
                task_id=sandbox.task_id,
                agent_run_id=sandbox.agent_run_id,
                event_type=event_type,
                payload_json={
                    "sandbox_id": sandbox.id,
                    "exit_code": exit_code,
                    "duration_ms": duration_ms,
                    "stdout_preview": stdout[:1000],
                    "stderr_preview": stderr[:1000],
                },
            )
            sandbox_command_duration_seconds.observe(duration_ms / 1000)
            sandbox.status = "IDLE"
            session.flush()
            return result
        except TimeoutError as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            sandbox_command_timeout_total.inc()
            sandbox.status = "IDLE"
            event_store.append(
                task_id=sandbox.task_id,
                agent_run_id=sandbox.agent_run_id,
                event_type=EventType.SANDBOX_COMMAND_FAILED,
                payload_json={
                    "sandbox_id": sandbox.id,
                    "exit_code": -1,
                    "duration_ms": duration_ms,
                    "stderr_preview": "command timed out",
                },
            )
            session.flush()
            raise SandboxCommandTimeoutError("command timed out") from exc

    def release_sandbox(self, *, session: Session, sandbox: SandboxInstance) -> SandboxInstance:
        sandbox.status = "IDLE"
        EventStore(session).append(
            task_id=sandbox.task_id,
            agent_run_id=sandbox.agent_run_id,
            event_type=EventType.SANDBOX_RELEASED,
            payload_json={"sandbox_id": sandbox.id, "container_id": sandbox.container_id},
        )
        session.flush()
        return sandbox

    def destroy_sandbox(self, *, session: Session, sandbox: SandboxInstance) -> SandboxInstance:
        try:
            container = self.client.containers.get(sandbox.container_id)
            container.remove(force=True)
        except docker.errors.DockerException:
            pass
        sandbox.status = "DESTROYED"
        sandbox.destroyed_at = utc_now()
        sandbox_containers_running.dec()
        EventStore(session).append(
            task_id=sandbox.task_id,
            agent_run_id=sandbox.agent_run_id,
            event_type=EventType.SANDBOX_DESTROYED,
            payload_json={"sandbox_id": sandbox.id, "container_id": sandbox.container_id},
        )
        session.flush()
        return sandbox

    def _decode_exec_result(self, exec_result: Any) -> tuple[str, str, int]:
        exit_code = getattr(exec_result, "exit_code", 0)
        output = getattr(exec_result, "output", exec_result)
        stdout_bytes: bytes | None
        stderr_bytes: bytes | None
        if isinstance(output, tuple):
            stdout_bytes, stderr_bytes = output
        else:
            stdout_bytes, stderr_bytes = output, b""
        stdout = (stdout_bytes or b"").decode("utf-8", errors="replace")
        stderr = (stderr_bytes or b"").decode("utf-8", errors="replace")
        return stdout, stderr, int(exit_code)
