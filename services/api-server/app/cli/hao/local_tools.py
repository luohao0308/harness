from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any

from .diffs import unified_diff

MAX_TEXT_BYTES = 64_000
MAX_SEARCH_FILE_BYTES = 1_048_576
MAX_MATCHES = 200
SEARCH_IGNORED_DIRS = {".git", ".venv", "__pycache__", "node_modules"}
SHELL_COMMAND_TOOLS = {"run_shell", "run_tests", "git"}
WRITE_COMMAND_TOOLS = {"write_file", "apply_patch"}
PREVIEW_COMMAND_TOOLS = {"preview_write_file", "preview_apply_patch"}
COMMIT_COMMAND_TOOLS = {"commit_write_file", "commit_apply_patch"}
COMMAND_STATUSES = {"pending", "running", "success", "failed", "timeout", "cancelled"}
COMMAND_STREAM_CHUNK_BYTES = 4_096
COMMAND_STREAM_CAPTURE_BYTES = MAX_TEXT_BYTES
MISSING_FILE_HASH = "__missing__"


@dataclass
class _RunningCommand:
    cancel_event: Event
    process: subprocess.Popen[str] | None = None


@dataclass
class _StreamCaptureState:
    chunks: list[str]
    captured_bytes: int = 0
    truncated: bool = False
    truncation_recorded: bool = False


_RUNNING_COMMANDS: dict[str, _RunningCommand] = {}
_RUNNING_COMMANDS_LOCK = Lock()


@dataclass(frozen=True)
class ToolExecutionResult:
    tool_name: str
    status: str
    input_json: dict[str, Any]
    output_json: dict[str, Any]
    duration_ms: int
    error_message: str | None = None


def command_status_to_tool_status(command_status: str) -> tuple[str, str | None]:
    mapping: dict[str, tuple[str, str | None]] = {
        "success": ("SUCCESS", None),
        "failed": ("FAILED", None),
        "timeout": ("TIMEOUT", None),
        "cancelled": ("FAILED", "cancelled"),
    }
    try:
        return mapping[command_status]
    except KeyError as exc:
        raise ValueError(f"unsupported command status: {command_status}") from exc


def _register_running_command(command_id: str, handle: _RunningCommand) -> None:
    with _RUNNING_COMMANDS_LOCK:
        _RUNNING_COMMANDS[command_id] = handle


def _unregister_running_command(command_id: str) -> None:
    with _RUNNING_COMMANDS_LOCK:
        _RUNNING_COMMANDS.pop(command_id, None)


def cancel_local_command(command_id: str) -> bool:
    with _RUNNING_COMMANDS_LOCK:
        handle = _RUNNING_COMMANDS.get(command_id)
    if handle is None:
        return False
    handle.cancel_event.set()
    process = handle.process
    if process is not None and process.poll() is None:
        _terminate_process(process)
    return True


def _signal_process_group(process: subprocess.Popen[str], sig: int) -> None:
    if os.name == "nt":
        if sig == signal.SIGKILL:
            process.kill()
        else:
            process.terminate()
        return
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        pass
    except OSError:
        if sig == signal.SIGKILL:
            process.kill()
        else:
            process.terminate()


def _terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    _signal_process_group(process, signal.SIGTERM)


def _kill_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    _signal_process_group(process, signal.SIGKILL)


def _append_capped_stream_chunk(
    *,
    session_store: Any,
    command_id: str,
    stream_name: str,
    state: _StreamCaptureState,
    chunk_bytes: bytes,
) -> None:
    if state.captured_bytes >= COMMAND_STREAM_CAPTURE_BYTES:
        state.truncated = True
        if not state.truncation_recorded:
            session_store.record_command_output_truncated(
                command_id,
                stream=stream_name,
                limit_bytes=COMMAND_STREAM_CAPTURE_BYTES,
            )
            state.truncation_recorded = True
        return
    remaining = COMMAND_STREAM_CAPTURE_BYTES - state.captured_bytes
    keep_bytes = chunk_bytes[:remaining]
    if keep_bytes:
        chunk_text = keep_bytes.decode("utf-8", errors="replace")
        session_store.record_command_output(
            command_id,
            stream=stream_name,
            chunk=chunk_text,
        )
        state.chunks.append(chunk_text)
        state.captured_bytes += len(keep_bytes)
    if len(chunk_bytes) > remaining:
        state.truncated = True
        if not state.truncation_recorded:
            session_store.record_command_output_truncated(
                command_id,
                stream=stream_name,
                limit_bytes=COMMAND_STREAM_CAPTURE_BYTES,
            )
            state.truncation_recorded = True


def _truncate(value: str, limit: int = MAX_TEXT_BYTES) -> tuple[str, bool]:
    encoded = value.encode("utf-8", errors="replace")
    if len(encoded) <= limit:
        return value, False
    truncated = encoded[:limit].decode("utf-8", errors="replace")
    return truncated, True


def _require_session(
    session_store: Any | None,
    session_id: str | None,
) -> tuple[Any, str]:
    if session_store is None or session_id is None:
        raise ValueError("session_store and session_id are required for pending changes")
    return session_store, session_id


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _file_hash(path: Path) -> str:
    if not path.exists():
        return MISSING_FILE_HASH
    return _sha256_bytes(path.read_bytes())


def _relative_path(workspace_root: Path, path: Path) -> str:
    return str(path.resolve().relative_to(workspace_root.resolve()))


def safe_join(workspace_root: Path, raw_path: str) -> Path:
    if not raw_path.strip():
        raise PermissionError("path is required")
    candidate = (workspace_root / raw_path).expanduser().resolve()
    root = workspace_root.expanduser().resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PermissionError("path must stay inside workspace") from exc
    return candidate


def _read_file(workspace_root: Path, input_json: dict[str, Any]) -> dict[str, Any]:
    path = safe_join(workspace_root, str(input_json.get("path", "")))
    raw = path.read_bytes()
    text, truncated = _truncate(raw.decode("utf-8", errors="replace"))
    return {
        "path": str(path.relative_to(workspace_root.resolve())),
        "content": text,
        "size_bytes": len(raw),
        "truncated": truncated,
    }


def _list_files(workspace_root: Path, input_json: dict[str, Any]) -> dict[str, Any]:
    root = safe_join(workspace_root, str(input_json.get("root", ".")))
    glob = str(input_json.get("glob", "**/*"))
    limit = max(1, min(int(input_json.get("limit", 200)), 1000))
    files: list[dict[str, Any]] = []
    for path in root.glob(glob):
        if len(files) >= limit:
            break
        if path == root:
            continue
        try:
            relative = path.resolve().relative_to(workspace_root.resolve())
        except ValueError:
            continue
        files.append(
            {
                "path": str(relative),
                "type": "dir" if path.is_dir() else "file",
                "size_bytes": path.stat().st_size if path.is_file() else 0,
            }
        )
    return {"root": str(root.relative_to(workspace_root.resolve())), "files": files}


def _path_matches_glob(relative_path: str, glob: str) -> bool:
    if glob in {"", "*", "**/*"}:
        return True
    return Path(relative_path).match(glob) or fnmatch.fnmatch(relative_path, glob)


def _is_ignored_relative(relative_path: Path) -> bool:
    return any(part in SEARCH_IGNORED_DIRS for part in relative_path.parts)


def _normalize_rg_path(path_text: str) -> str:
    if path_text.startswith("./"):
        return path_text[2:]
    return path_text


def _search_files_rg(
    workspace_root: Path,
    root: Path,
    *,
    query: str,
    glob: str,
    limit: int,
) -> dict[str, Any] | None:
    rg = shutil.which("rg")
    if rg is None:
        return None
    try:
        root_arg = str(root.resolve().relative_to(workspace_root.resolve())) or "."
    except ValueError:
        return None
    command = [
        rg,
        "--json",
        "--fixed-strings",
        "--ignore-case",
        "--max-filesize",
        str(MAX_SEARCH_FILE_BYTES),
    ]
    if glob not in {"", "*", "**/*"}:
        command.extend(["--glob", glob])
    for directory in sorted(SEARCH_IGNORED_DIRS):
        command.extend(["--glob", f"!**/{directory}/**"])
    command.extend(["--", query, root_arg])
    try:
        completed = subprocess.run(
            command,
            cwd=workspace_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode not in {0, 1}:
        return None

    matches: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        if len(matches) >= limit:
            break
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("type") != "match":
            continue
        data = record.get("data")
        if not isinstance(data, dict):
            continue
        path_data = data.get("path")
        lines_data = data.get("lines")
        if not isinstance(path_data, dict) or not isinstance(lines_data, dict):
            continue
        path_text = str(path_data.get("text") or "")
        line_text = str(lines_data.get("text") or "").rstrip("\n")
        line_number = int(data.get("line_number") or 0)
        if not path_text or line_number < 1:
            continue
        matches.append(
            {
                "path": _normalize_rg_path(path_text),
                "line": line_number,
                "text": line_text[:500],
            }
        )
    return {
        "query": query,
        "matches": matches,
        "truncated": len(matches) >= limit,
        "engine": "rg",
    }


def _search_files_python(
    workspace_root: Path,
    root: Path,
    *,
    query: str,
    glob: str,
    limit: int,
) -> dict[str, Any]:
    query_folded = query.casefold()
    matches: list[dict[str, Any]] = []
    workspace = workspace_root.resolve()

    def iter_paths() -> Iterator[Path]:
        if root.is_file():
            yield root
            return
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(
                dirname for dirname in dirnames if dirname not in SEARCH_IGNORED_DIRS
            )
            for filename in sorted(filenames):
                yield Path(dirpath) / filename

    for path in iter_paths():
        if len(matches) >= limit:
            break
        try:
            relative = path.resolve().relative_to(workspace)
        except ValueError:
            continue
        if _is_ignored_relative(relative) or not _path_matches_glob(str(relative), glob):
            continue
        try:
            if path.stat().st_size > MAX_SEARCH_FILE_BYTES:
                continue
            raw = path.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw[:8192]:
            continue
        text = raw.decode("utf-8", errors="ignore")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if query_folded not in line.casefold():
                continue
            matches.append(
                {
                    "path": str(relative),
                    "line": line_number,
                    "text": line[:500],
                }
            )
            if len(matches) >= limit:
                break
    return {
        "query": query,
        "matches": matches,
        "truncated": len(matches) >= limit,
        "engine": "python",
    }


def _search_files(workspace_root: Path, input_json: dict[str, Any]) -> dict[str, Any]:
    query = str(input_json.get("query", "")).strip()
    if not query:
        raise ValueError("query is required")
    root = safe_join(workspace_root, str(input_json.get("root", ".")))
    glob = str(input_json.get("glob", "**/*"))
    limit = max(1, min(int(input_json.get("limit", MAX_MATCHES)), MAX_MATCHES))
    if not root.exists():
        return {"query": query, "matches": [], "truncated": False, "engine": "python"}
    rg_result = _search_files_rg(
        workspace_root,
        root,
        query=query,
        glob=glob,
        limit=limit,
    )
    if rg_result is not None:
        return rg_result
    return _search_files_python(
        workspace_root,
        root,
        query=query,
        glob=glob,
        limit=limit,
    )



def _write_file(workspace_root: Path, input_json: dict[str, Any]) -> dict[str, Any]:
    path = safe_join(workspace_root, str(input_json.get("path", "")))
    content = str(input_json.get("content", ""))
    before = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    relative = str(path.relative_to(workspace_root.resolve()))
    return {
        "path": relative,
        "bytes_written": len(content.encode("utf-8")),
        "diff": unified_diff(before, content, fromfile=f"a/{relative}", tofile=f"b/{relative}"),
    }


def _preview_write_file(
    workspace_root: Path,
    input_json: dict[str, Any],
    *,
    session_store: Any,
    session_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = safe_join(workspace_root, str(input_json.get("path", "")))
    content = str(input_json.get("content", ""))
    content_bytes = content.encode("utf-8")
    relative = _relative_path(workspace_root, path)
    before_hash = _file_hash(path)
    before = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    diff = unified_diff(before, content, fromfile=f"a/{relative}", tofile=f"b/{relative}")
    change = session_store.create_pending_change(
        session_id,
        tool_name="write_file",
        target_paths=[relative],
        before_hashes={relative: before_hash},
        after_hashes={relative: _sha256_bytes(content_bytes)},
        diff=diff,
        proposed_content={relative: content},
        input_json=input_json,
        tool_call_id=input_json.get("tool_call_id"),
        metadata=metadata,
    )
    return {
        "change_id": change["id"],
        "change_status": change["status"],
        "target_paths": change["target_paths"],
        "before_hashes": change["before_hashes"],
        "after_hashes": change["after_hashes"],
        "diff": change["diff"],
    }


def _patch_paths(patch: str) -> list[str]:
    paths: list[str] = []
    for line in patch.splitlines():
        if line.startswith(("--- ", "+++ ")):
            raw = line[4:].strip()
            if raw == "/dev/null":
                continue
            if raw.startswith(("a/", "b/")):
                raw = raw[2:]
            path = raw.split("\t", 1)[0]
            if path not in paths:
                paths.append(path)
    return paths


def _copy_patch_targets(
    workspace_root: Path,
    preview_root: Path,
    target_paths: list[str],
) -> None:
    for relative in target_paths:
        source = safe_join(workspace_root, relative)
        destination = preview_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.exists():
            if source.is_dir():
                shutil.copytree(source, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(source, destination)


def _current_hashes(workspace_root: Path, target_paths: list[str]) -> dict[str, str]:
    return {
        relative: _file_hash(safe_join(workspace_root, relative))
        for relative in target_paths
    }


def _stale_paths(
    workspace_root: Path,
    before_hashes: dict[str, str],
) -> list[dict[str, str]]:
    stale: list[dict[str, str]] = []
    for relative, expected in before_hashes.items():
        actual = _file_hash(safe_join(workspace_root, relative))
        if actual != expected:
            stale.append({"path": relative, "expected": expected, "actual": actual})
    return stale


def _run_command(
    command: list[str] | str,
    workspace_root: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    shell = isinstance(command, str)
    completed = subprocess.run(
        command,
        cwd=workspace_root,
        shell=shell,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    stdout, stdout_truncated = _truncate(completed.stdout)
    stderr, stderr_truncated = _truncate(completed.stderr)
    return {
        "command": command if isinstance(command, str) else " ".join(command),
        "exit_code": completed.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "truncated": stdout_truncated or stderr_truncated,
    }


def _apply_patch(workspace_root: Path, input_json: dict[str, Any]) -> dict[str, Any]:
    patch = str(input_json.get("patch", ""))
    if not patch.strip():
        raise ValueError("patch is required")
    for raw_path in _patch_paths(patch):
        safe_join(workspace_root, raw_path)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        handle.write(patch)
        patch_path = handle.name
    try:
        return _run_command(["git", "apply", "--whitespace=nowarn", patch_path], workspace_root, 30)
    finally:
        Path(patch_path).unlink(missing_ok=True)


def _preview_apply_patch(
    workspace_root: Path,
    input_json: dict[str, Any],
    *,
    session_store: Any,
    session_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    patch = str(input_json.get("patch", ""))
    if not patch.strip():
        raise ValueError("patch is required")
    target_paths = _patch_paths(patch)
    if not target_paths:
        raise ValueError("patch must include at least one file path")
    for relative in target_paths:
        safe_join(workspace_root, relative)
    before_hashes = _current_hashes(workspace_root, target_paths)
    with tempfile.TemporaryDirectory() as temp_dir:
        preview_root = Path(temp_dir)
        _copy_patch_targets(workspace_root, preview_root, target_paths)
        preview_result = _apply_patch(preview_root, {"patch": patch})
        if int(preview_result.get("exit_code", 1)) != 0:
            error = str(preview_result.get("stderr") or preview_result.get("stdout") or "")
            raise ValueError(error.strip() or "patch did not apply")
        after_hashes = _current_hashes(preview_root, target_paths)
    change = session_store.create_pending_change(
        session_id,
        tool_name="apply_patch",
        target_paths=target_paths,
        before_hashes=before_hashes,
        after_hashes=after_hashes,
        diff=patch,
        patch=patch,
        input_json=input_json,
        tool_call_id=input_json.get("tool_call_id"),
        metadata=metadata,
    )
    return {
        "change_id": change["id"],
        "change_status": change["status"],
        "target_paths": change["target_paths"],
        "before_hashes": change["before_hashes"],
        "after_hashes": change["after_hashes"],
        "diff": change["diff"],
    }


def _commit_pending_change(
    workspace_root: Path,
    input_json: dict[str, Any],
    *,
    session_store: Any,
    session_id: str,
    expected_tool_name: str,
) -> dict[str, Any]:
    change_id = str(input_json.get("change_id") or "").strip()
    if not change_id:
        raise ValueError("change_id is required")
    change = session_store.get_pending_change(change_id)
    if change is None:
        raise ValueError(f"pending change not found: {change_id}")
    if change["session_id"] != session_id:
        raise ValueError(f"pending change does not belong to session: {change_id}")
    if change["tool_name"] != expected_tool_name:
        raise ValueError(
            f"pending change is for {change['tool_name']}, not {expected_tool_name}"
        )
    if change["status"] != "pending":
        raise ValueError(f"pending change is not pending: {change_id}")
    stale = _stale_paths(workspace_root, change["before_hashes"])
    if stale:
        updated = session_store.update_pending_change_status(
            change_id,
            status="stale",
            error_message="workspace changed before pending change commit",
        )
        return {
            "change_id": change_id,
            "change_status": updated["status"],
            "target_paths": updated["target_paths"],
            "diff": updated["diff"],
            "stale_paths": stale,
            "error": updated["error_message"],
        }
    if expected_tool_name == "write_file":
        proposed_content = change["proposed_content"] or {}
        for relative in change["target_paths"]:
            if relative not in proposed_content:
                raise ValueError(f"missing proposed content for {relative}")
            path = safe_join(workspace_root, relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(proposed_content[relative]), encoding="utf-8")
    else:
        patch = str(change.get("patch") or "")
        if not patch.strip():
            raise ValueError("pending patch content is missing")
        patch_result = _apply_patch(workspace_root, {"patch": patch})
        if int(patch_result.get("exit_code", 1)) != 0:
            error = str(patch_result.get("stderr") or patch_result.get("stdout") or "")
            updated = session_store.update_pending_change_status(
                change_id,
                status="failed",
                error_message=error.strip() or "patch did not apply",
            )
            return {
                "change_id": change_id,
                "change_status": updated["status"],
                "target_paths": updated["target_paths"],
                "diff": updated["diff"],
                "error": updated["error_message"],
                "patch_result": patch_result,
            }
    after_hashes = _current_hashes(workspace_root, change["target_paths"])
    if after_hashes != change["after_hashes"]:
        updated = session_store.update_pending_change_status(
            change_id,
            status="failed",
            error_message="committed file hashes did not match pending preview",
        )
        return {
            "change_id": change_id,
            "change_status": updated["status"],
            "target_paths": updated["target_paths"],
            "diff": updated["diff"],
            "after_hashes": after_hashes,
            "expected_after_hashes": change["after_hashes"],
            "error": updated["error_message"],
        }
    updated = session_store.update_pending_change_status(change_id, status="committed")
    return {
        "change_id": change_id,
        "change_status": updated["status"],
        "target_paths": updated["target_paths"],
        "before_hashes": updated["before_hashes"],
        "after_hashes": updated["after_hashes"],
        "diff": updated["diff"],
    }


def _shell_command(input_json: dict[str, Any], *, default: str = "") -> str:
    return str(input_json.get("command") or input_json.get("cmd") or default).strip()


def _normalize_shell_command(command: str) -> str:
    if command == "python":
        return sys.executable
    if command.startswith("python "):
        return f"{sys.executable} {command.removeprefix('python ')}"
    return command


def _run_process_with_lifecycle(
    *,
    tool_name: str,
    command_id: str,
    command: str,
    workspace_root: Path,
    timeout_seconds: int,
    session_store: Any,
    session_id: str,
    cancel_check: Callable[[str], bool] | None = None,
) -> ToolExecutionResult:
    workspace_root = workspace_root.expanduser().resolve()
    started_build = time.monotonic()
    handle = _RunningCommand(cancel_event=Event())
    _register_running_command(command_id, handle)
    process: subprocess.Popen[str] | None = None
    stdout_state = _StreamCaptureState(chunks=[])
    stderr_state = _StreamCaptureState(chunks=[])
    output_error_message: str | None = None
    try:
        started = session_store.start_command(command_id)
        started_at = str(started["started_at"])
        try:
            process = subprocess.Popen(
                command,
                cwd=workspace_root,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
                bufsize=0,
                start_new_session=True,
            )
        except Exception as exc:
            finished = session_store.finish_command(
                command_id,
                status="failed",
                exit_code=None,
                stdout_truncated=False,
                stderr_truncated=False,
                error_message=str(exc),
            )
            duration_ms = int((time.monotonic() - started_build) * 1000)
            return ToolExecutionResult(
                tool_name=tool_name,
                status="FAILED",
                input_json={"command": command, "timeout_seconds": timeout_seconds},
                output_json={
                    "command_id": command_id,
                    "command": command,
                    "command_status": "failed",
                    "started_at": started_at,
                    "finished_at": str(finished["finished_at"] or started_at),
                    "exit_code": None,
                    "stdout": "",
                    "stderr": "",
                    "stdout_truncated": False,
                    "stderr_truncated": False,
                    "timeout_seconds": timeout_seconds,
                    "error": str(exc),
                },
                duration_ms=duration_ms,
                error_message=str(exc),
            )

        handle.process = process

        def _drain_stream(
            stream,
            stream_name: str,
            state: _StreamCaptureState,
        ) -> None:
            try:
                if stream is None:
                    return
                fd = stream.fileno()
                while True:
                    try:
                        chunk_bytes = os.read(fd, COMMAND_STREAM_CHUNK_BYTES)
                    except OSError:
                        break
                    if not chunk_bytes:
                        break
                    _append_capped_stream_chunk(
                        session_store=session_store,
                        command_id=command_id,
                        stream_name=stream_name,
                        state=state,
                        chunk_bytes=chunk_bytes,
                    )
            finally:
                try:
                    if stream is not None:
                        stream.close()
                except OSError:
                    pass

        stdout_thread = Thread(
            target=_drain_stream,
            args=(process.stdout, "stdout", stdout_state),
            daemon=True,
        )
        stderr_thread = Thread(
            target=_drain_stream,
            args=(process.stderr, "stderr", stderr_state),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        terminal_status: str
        exit_code: int | None
        while True:
            if process.poll() is not None:
                exit_code = process.returncode
                terminal_status = "success" if exit_code == 0 else "failed"
                break
            if handle.cancel_event.is_set() or (
                cancel_check is not None and cancel_check(command_id)
            ):
                terminal_status = "cancelled"
                output_error_message = "cancelled"
                _terminate_process(process)
                break
            elapsed = time.monotonic() - started_build
            if elapsed >= timeout_seconds:
                terminal_status = "timeout"
                output_error_message = f"timeout after {timeout_seconds}s"
                _terminate_process(process)
                break
            time.sleep(0.05)

        if process.poll() is None:
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                _kill_process(process)
                process.wait(timeout=2)
        exit_code = process.returncode

        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)

        stdout_text = "".join(stdout_state.chunks)
        stderr_text = "".join(stderr_state.chunks)
        stdout_text, stdout_truncated = _truncate(stdout_text)
        stderr_text, stderr_truncated = _truncate(stderr_text)
        stdout_truncated = stdout_truncated or stdout_state.truncated
        stderr_truncated = stderr_truncated or stderr_state.truncated
        if terminal_status == "success" and exit_code != 0:
            terminal_status = "failed"
        tool_status, mapped_error = command_status_to_tool_status(terminal_status)
        if terminal_status in {"timeout", "cancelled"} and exit_code is None:
            exit_code = process.returncode
        finished = session_store.finish_command(
            command_id,
            status=terminal_status,
            exit_code=exit_code,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            error_message=output_error_message,
        )
        output_json: dict[str, Any] = {
            "command_id": command_id,
            "command": command,
            "command_status": terminal_status,
            "started_at": started_at,
            "finished_at": finished["finished_at"],
            "exit_code": exit_code,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
            "timeout_seconds": timeout_seconds,
        }
        if output_error_message is not None:
            output_json["error"] = output_error_message
        elif mapped_error is not None:
            output_json["error"] = mapped_error
        duration_ms = int((time.monotonic() - started_build) * 1000)
        return ToolExecutionResult(
            tool_name=tool_name,
            status=tool_status,
            input_json={"command": command, "timeout_seconds": timeout_seconds},
            output_json=output_json,
            duration_ms=duration_ms,
            error_message=output_error_message or mapped_error,
        )
    finally:
        _unregister_running_command(command_id)
        if process is not None:
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass


def execute_local_command_tool(
    tool_name: str,
    input_json: dict[str, Any],
    workspace_root: Path,
    *,
    session_store: Any,
    session_id: str,
    cancel_check: Callable[[str], bool] | None = None,
) -> ToolExecutionResult:
    if tool_name not in SHELL_COMMAND_TOOLS:
        return execute_local_tool(tool_name, input_json, workspace_root)
    if session_store is None or session_id is None:
        raise ValueError("session_store and session_id are required for command lifecycle")
    command = _shell_command(input_json)
    timeout_seconds: int
    if tool_name == "run_tests":
        command = _shell_command(input_json, default="pytest")
        if not command:
            raise ValueError("command is required")
        command = _normalize_shell_command(command)
        timeout_seconds = max(1, min(int(input_json.get("timeout_seconds", 300)), 900))
    elif tool_name == "git":
        if not command:
            args = " ".join(map(str, input_json.get("args") or []))
            command = f"git {args}".strip()
        if not command.startswith("git"):
            command = f"git {command}"
        timeout_seconds = max(1, min(int(input_json.get("timeout_seconds", 120)), 600))
    else:
        if not command:
            raise ValueError("command is required")
        command = _normalize_shell_command(command)
        timeout_seconds = max(1, min(int(input_json.get("timeout_seconds", 60)), 600))
    created = session_store.create_command(
        session_id,
        tool_name=tool_name,
        command=command,
        command_json=input_json,
        timeout_seconds=timeout_seconds,
    )
    return _run_process_with_lifecycle(
        tool_name=tool_name,
        command_id=created["id"],
        command=command,
        workspace_root=workspace_root,
        timeout_seconds=timeout_seconds,
        session_store=session_store,
        session_id=session_id,
        cancel_check=cancel_check,
    )


def retry_local_command_tool(
    command_id: str,
    workspace_root: Path,
    *,
    session_store: Any,
    cancel_check: Callable[[str], bool] | None = None,
) -> ToolExecutionResult:
    command = session_store.retry_command(command_id)
    return _run_process_with_lifecycle(
        tool_name=str(command["tool_name"]),
        command_id=str(command["id"]),
        command=str(command["command"]),
        workspace_root=workspace_root,
        timeout_seconds=int(command["timeout_seconds"]),
        session_store=session_store,
        session_id=str(command["session_id"]),
        cancel_check=cancel_check,
    )


def execute_local_tool(
    tool_name: str,
    input_json: dict[str, Any],
    workspace_root: Path,
    *,
    session_store: Any | None = None,
    session_id: str | None = None,
    cancel_check: Callable[[str], bool] | None = None,
    pending_change_metadata: dict[str, Any] | None = None,
) -> ToolExecutionResult:
    if tool_name in SHELL_COMMAND_TOOLS and (session_store is not None or session_id is not None):
        if session_store is None or session_id is None:
            raise ValueError("session_store and session_id must be provided together")
        return execute_local_command_tool(
            tool_name,
            input_json,
            workspace_root,
            session_store=session_store,
            session_id=session_id,
            cancel_check=cancel_check,
        )
    pending_change_tools = PREVIEW_COMMAND_TOOLS | COMMIT_COMMAND_TOOLS
    if tool_name in pending_change_tools or (
        tool_name in WRITE_COMMAND_TOOLS
        and (session_store is not None or session_id is not None)
    ):
        session_store, session_id = _require_session(session_store, session_id)
    workspace_root = workspace_root.expanduser().resolve()
    started_at = time.monotonic()
    status = "SUCCESS"
    error_message: str | None = None
    try:
        if tool_name == "read_file":
            output = _read_file(workspace_root, input_json)
        elif tool_name == "list_files":
            output = _list_files(workspace_root, input_json)
        elif tool_name == "search_files":
            output = _search_files(workspace_root, input_json)
        elif tool_name in {"write_file", "preview_write_file"} and session_store is not None:
            output = _preview_write_file(
                workspace_root,
                input_json,
                session_store=session_store,
                session_id=str(session_id),
                metadata=pending_change_metadata,
            )
        elif tool_name == "commit_write_file":
            output = _commit_pending_change(
                workspace_root,
                input_json,
                session_store=session_store,
                session_id=str(session_id),
                expected_tool_name="write_file",
            )
            status = "SUCCESS" if output.get("change_status") == "committed" else "FAILED"
            error_message = output.get("error")
        elif tool_name == "write_file":
            output = _write_file(workspace_root, input_json)
        elif tool_name in {"apply_patch", "preview_apply_patch"} and session_store is not None:
            output = _preview_apply_patch(
                workspace_root,
                input_json,
                session_store=session_store,
                session_id=str(session_id),
                metadata=pending_change_metadata,
            )
        elif tool_name == "commit_apply_patch":
            output = _commit_pending_change(
                workspace_root,
                input_json,
                session_store=session_store,
                session_id=str(session_id),
                expected_tool_name="apply_patch",
            )
            status = "SUCCESS" if output.get("change_status") == "committed" else "FAILED"
            error_message = output.get("error")
        elif tool_name == "apply_patch":
            output = _apply_patch(workspace_root, input_json)
            status = "SUCCESS" if int(output.get("exit_code", 1)) == 0 else "FAILED"
        elif tool_name == "run_shell":
            command = _shell_command(input_json)
            if not command:
                raise ValueError("command is required")
            timeout_seconds = max(1, min(int(input_json.get("timeout_seconds", 60)), 600))
            output = _run_command(command, workspace_root, timeout_seconds)
            status = "SUCCESS" if int(output.get("exit_code", 1)) == 0 else "FAILED"
        elif tool_name == "run_tests":
            command = _shell_command(input_json, default="pytest")
            timeout_seconds = max(1, min(int(input_json.get("timeout_seconds", 300)), 900))
            output = _run_command(command, workspace_root, timeout_seconds)
            status = "SUCCESS" if int(output.get("exit_code", 1)) == 0 else "FAILED"
        elif tool_name == "git":
            command = _shell_command(input_json)
            if not command:
                args = " ".join(map(str, input_json.get("args") or []))
                command = f"git {args}".strip()
            if not command.startswith("git"):
                command = f"git {command}"
            output = _run_command(command, workspace_root, 120)
            status = "SUCCESS" if int(output.get("exit_code", 1)) == 0 else "FAILED"
        else:
            raise ValueError(f"unknown local tool: {tool_name}")
    except subprocess.TimeoutExpired as exc:
        status = "TIMEOUT"
        error_message = str(exc)
        output = {"error": str(exc), "timeout_seconds": exc.timeout}
    except Exception as exc:
        status = "FAILED"
        error_message = str(exc)
        output = {"error": str(exc)}
    duration_ms = int((time.monotonic() - started_at) * 1000)
    return ToolExecutionResult(
        tool_name=tool_name,
        status=status,
        input_json=input_json,
        output_json=output,
        duration_ms=duration_ms,
        error_message=error_message,
    )
