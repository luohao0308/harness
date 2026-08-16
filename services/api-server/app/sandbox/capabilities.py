from __future__ import annotations

from typing import Any

import docker


def probe_docker_sandbox(*, client: Any | None = None) -> dict[str, object]:
    """Report Docker as an optional sandbox capability without exposing daemon errors."""

    docker_client = client
    try:
        if docker_client is None:
            docker_client = docker.from_env()
        if not docker_client.ping():
            raise docker.errors.DockerException("Docker ping returned false")
        version_payload = docker_client.version()
        version = str(version_payload.get("Version") or "unknown")
    except (docker.errors.DockerException, OSError, RuntimeError):
        return {
            "status": "unavailable",
            "required": False,
            "blocks_core_readiness": False,
            "provider": "docker",
            "reason": "docker_daemon_unavailable",
        }
    return {
        "status": "available",
        "required": False,
        "blocks_core_readiness": False,
        "provider": "docker",
        "version": version,
    }
