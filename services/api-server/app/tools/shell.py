from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.models import SandboxInstance
from app.sandbox.docker_manager import DockerManager, SandboxCommandResult


@dataclass(frozen=True)
class ShellToolRequest:
    command: str
    cwd: str = "/workspace"
    timeout_seconds: int = 60


class ShellTool:
    def __init__(self, docker_manager: DockerManager | None = None) -> None:
        self.docker_manager = docker_manager or DockerManager()

    def run(
        self,
        *,
        session: Session,
        sandbox: SandboxInstance,
        request: ShellToolRequest,
    ) -> SandboxCommandResult:
        return self.docker_manager.run_command(
            session=session,
            sandbox=sandbox,
            command=request.command,
            timeout_seconds=request.timeout_seconds,
            cwd=request.cwd,
        )
