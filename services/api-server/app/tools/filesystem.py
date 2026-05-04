from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ReadFileResult:
    content: str
    size_bytes: int


@dataclass(frozen=True)
class ListFilesResult:
    files: list[str]


class WorkspaceFileTool:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()

    def read_file(self, path: str) -> ReadFileResult:
        target = self._resolve_workspace_path(path)
        content = target.read_text(encoding="utf-8")
        return ReadFileResult(content=content, size_bytes=target.stat().st_size)

    def list_files(self, root: str = ".", glob: str = "**/*") -> ListFilesResult:
        target = self._resolve_workspace_path(root)
        files = [
            str(path.relative_to(self.workspace_root))
            for path in sorted(target.glob(glob))
            if path.is_file()
        ]
        return ListFilesResult(files=files)

    def _resolve_workspace_path(self, path: str) -> Path:
        target = (self.workspace_root / path).resolve()
        if target != self.workspace_root and self.workspace_root not in target.parents:
            raise ValueError("path escapes task workspace")
        return target
