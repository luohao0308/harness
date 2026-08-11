from __future__ import annotations

import docker

from app.sandbox.capabilities import probe_docker_sandbox


class _AvailableDockerClient:
    def ping(self) -> bool:
        return True

    def version(self) -> dict[str, str]:
        return {"Version": "27.1.0"}


class _UnavailableDockerClient:
    def ping(self) -> bool:
        raise docker.errors.DockerException("socket unavailable")


def test_docker_sandbox_capability_is_optional_when_available() -> None:
    capability = probe_docker_sandbox(client=_AvailableDockerClient())

    assert capability == {
        "status": "available",
        "required": False,
        "blocks_core_readiness": False,
        "provider": "docker",
        "version": "27.1.0",
    }


def test_docker_sandbox_capability_is_optional_when_daemon_is_missing() -> None:
    capability = probe_docker_sandbox(client=_UnavailableDockerClient())

    assert capability == {
        "status": "unavailable",
        "required": False,
        "blocks_core_readiness": False,
        "provider": "docker",
        "reason": "docker_daemon_unavailable",
    }
