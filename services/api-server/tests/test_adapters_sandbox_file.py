from pathlib import Path

from app.tools.adapters.sandbox_file_adapter import SandboxFileAdapter
from app.tools.registry import ToolRegistry


def _adapter(method: str, risk_level="medium") -> SandboxFileAdapter:
    return SandboxFileAdapter(
        slug=f"sandbox.{method}",
        method=method,
        description=method,
        input_schema={},
        output_schema={},
        risk_level=risk_level,
    )


def _metadata(name: str):
    return ToolRegistry.default().tools[name]


def test_sandbox_read_file_truncates_and_reports_mime(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("abcdef", encoding="utf-8")

    result = _adapter("read_file").execute(
        metadata=_metadata("sandbox.read_file"),
        input_json={"path": "notes.txt", "max_bytes": 3},
        config_json=None,
        secret_value=None,
        sandbox_workspace_root=tmp_path,
    )

    assert result.output_json == {
        "path": "notes.txt",
        "content": "abc",
        "size_bytes": 3,
        "total_size": 6,
        "mime_type": "text/plain",
        "truncated": True,
    }


def test_sandbox_list_files_respects_depth_and_pattern(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "b").mkdir()
    (tmp_path / "a" / "b" / "c").mkdir()
    (tmp_path / "a" / "b" / "c" / "d").mkdir()
    (tmp_path / "a" / "keep.md").write_text("ok", encoding="utf-8")

    listed = _adapter("list_files").execute(
        metadata=_metadata("sandbox.list_files"),
        input_json={"path": "a", "pattern": "*.md"},
        config_json=None,
        secret_value=None,
        sandbox_workspace_root=tmp_path,
    )
    too_deep = _adapter("list_files").execute(
        metadata=_metadata("sandbox.list_files"),
        input_json={"path": "a/b/c/d"},
        config_json=None,
        secret_value=None,
        sandbox_workspace_root=tmp_path,
    )

    assert listed.output_json["entries"][0]["path"] == "a/keep.md"
    assert too_deep.output_json["error"] == "depth_exceeded"


def test_sandbox_write_and_delete_file(tmp_path: Path) -> None:
    written = _adapter("write_file", risk_level="high").execute(
        metadata=_metadata("sandbox.write_file"),
        input_json={"path": "out/result.txt", "content": "hello"},
        config_json=None,
        secret_value=None,
        sandbox_workspace_root=tmp_path,
    )
    deleted = _adapter("delete_file", risk_level="high").execute(
        metadata=_metadata("sandbox.delete_file"),
        input_json={"path": "out/result.txt"},
        config_json=None,
        secret_value=None,
        sandbox_workspace_root=tmp_path,
    )

    assert written.output_json["bytes_written"] == 5
    assert len(written.output_json["sha256"]) == 64
    assert deleted.output_json == {"path": "out/result.txt", "deleted": True}
    assert not (tmp_path / "out" / "result.txt").exists()


def test_sandbox_file_adapter_fails_closed_without_workspace() -> None:
    result = _adapter("read_file").execute(
        metadata=_metadata("sandbox.read_file"),
        input_json={"path": "notes.txt"},
        config_json=None,
        secret_value=None,
        sandbox_workspace_root=None,
    )

    assert result.output_json["error"] == "sandbox_not_ready"


def test_sandbox_file_adapter_blocks_path_traversal_and_absolute_path(tmp_path: Path) -> None:
    traversal = _adapter("read_file").execute(
        metadata=_metadata("sandbox.read_file"),
        input_json={"path": "../secret.txt"},
        config_json=None,
        secret_value=None,
        sandbox_workspace_root=tmp_path,
    )
    absolute = _adapter("write_file", risk_level="high").execute(
        metadata=_metadata("sandbox.write_file"),
        input_json={"path": "/tmp/secret.txt", "content": "no"},
        config_json=None,
        secret_value=None,
        sandbox_workspace_root=tmp_path,
    )

    assert traversal.output_json["error"] == "path_traversal"
    assert absolute.output_json["error"] == "path_traversal"
