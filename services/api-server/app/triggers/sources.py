"""Safe local trigger source scanners.

This module deliberately has no ORM dependency.  The trigger service supplies
plain mappings and persists the returned source state/invocation identity.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SourceObservation:
    source_key: str
    identity: str
    metadata: dict[str, Any]

    @property
    def dedupe_key(self) -> str:
        return f"trigger:{self.source_key}:{self.identity}"


def _stable(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _source_key(kind: str, root: Path) -> str:
    return f"{kind}:{hashlib.sha256(str(root).encode()).hexdigest()[:20]}"


def _hash_file(path: Path, *, max_bytes: int, deadline: float) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError("file trigger scan deadline exceeded")
            chunk = stream.read(min(64 * 1024, max_bytes - total + 1))
            if not chunk:
                return digest.hexdigest(), total
            total += len(chunk)
            if total > max_bytes:
                raise ValueError("file trigger per-file byte limit exceeded")
            digest.update(chunk)


def _git_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY"):
        environment.pop(key, None)
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    environment["GIT_TERMINAL_PROMPT"] = "0"
    return environment


def _snapshot_fingerprint(entry: Any) -> str | None:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, Mapping):
        value = entry.get("fingerprint")
        return str(value) if value else None
    return None


def schedule_due(
    trigger: Mapping[str, Any], state: Mapping[str, Any], *, now: float | None = None
) -> bool:
    if not bool(trigger.get("enabled", False)):
        return False
    interval = float(trigger.get("interval_seconds", 0) or 0)
    if interval <= 0:
        return False
    if state.get("next_run_at") is None:
        return False
    current = float(time.time() if now is None else now)
    return current >= float(state["next_run_at"])


def next_schedule_state(
    trigger: Mapping[str, Any],
    state: Mapping[str, Any] | None = None,
    *,
    now: float | None = None,
) -> dict[str, Any]:
    current = float(time.time() if now is None else now)
    interval = float(trigger.get("interval_seconds", 0) or 0)
    prior_due = state.get("next_run_at") if state else None
    if prior_due is None:
        return {"last_run_at": None, "next_run_at": current + interval}
    next_run_at = float(prior_due) + interval
    while next_run_at <= current:
        next_run_at += interval
    return {
        "last_run_at": current,
        "last_scheduled_at": float(prior_due),
        "next_run_at": next_run_at,
    }


def schedule_observation(
    trigger_id: str,
    trigger: Mapping[str, Any],
    *,
    now: float | None = None,
    scheduled_at: float | None = None,
) -> SourceObservation:
    current = float(time.time() if now is None else now)
    interval = float(trigger.get("interval_seconds", 0) or 0)
    scheduled_at = (
        float(scheduled_at)
        if scheduled_at is not None
        else (int(current // interval) * interval if interval > 0 else current)
    )
    identity = _stable({"trigger_id": trigger_id, "scheduled_at": scheduled_at})
    return SourceObservation(
        source_key=f"schedule:{trigger_id}",
        identity=identity,
        metadata={"scheduled_at": scheduled_at, "interval_seconds": interval},
    )


def scan_files(
    trigger: Mapping[str, Any], *, previous: Mapping[str, Any] | None = None
) -> tuple[list[SourceObservation], dict[str, Any]]:
    """Return changed files under an explicitly configured workspace root.

    Initial scans establish a snapshot and never emit observations.  Limits are
    intentionally conservative and all path traversal/symlink escapes are rejected.
    """
    if not bool(trigger.get("enabled", False)):
        return [], dict(previous or {})
    root_raw = trigger.get("workspace_root")
    if not root_raw:
        return [], dict(previous or {})
    root = Path(str(root_raw)).expanduser()
    try:
        root = root.resolve(strict=True)
    except OSError:
        return [], dict(previous or {})
    pattern = str(trigger.get("pattern", "**/*"))
    max_files = max(1, min(int(trigger.get("max_files", 1000)), 10000))
    max_file_bytes = max(
        1,
        min(
            int(trigger.get("max_file_bytes", trigger.get("max_bytes", 1024 * 1024))),
            8 * 1024 * 1024,
        ),
    )
    max_total_bytes = max(
        max_file_bytes,
        min(int(trigger.get("max_total_bytes", 4 * 1024 * 1024)), 64 * 1024 * 1024),
    )
    max_duration_seconds = max(
        0.01,
        min(float(trigger.get("max_duration_seconds", 2.0)), 10.0),
    )
    started_at = time.monotonic()
    deadline = started_at + max_duration_seconds
    total_bytes = 0
    truncated = False
    previous_snapshot = (previous or {}).get("snapshot", {})
    snapshot: dict[str, dict[str, Any]] = {}
    changed: list[tuple[str, str, dict[str, Any]]] = []
    for index, path in enumerate(islice(root.glob(pattern), max_files + 1)):
        if index >= max_files:
            truncated = True
            break
        if time.monotonic() >= deadline:
            truncated = True
            break
        if not path.is_file() or path.is_symlink():
            continue
        try:
            resolved = path.resolve(strict=True)
            if root not in resolved.parents and resolved != root:
                continue
            stat = resolved.stat()
            if stat.st_size > max_file_bytes:
                truncated = True
                continue
            rel = resolved.relative_to(root).as_posix()
            prior = previous_snapshot.get(rel)
            if (
                isinstance(prior, Mapping)
                and prior.get("size") == stat.st_size
                and prior.get("mtime_ns") == stat.st_mtime_ns
                and prior.get("sha256")
                and prior.get("fingerprint")
            ):
                digest = str(prior["sha256"])
                identity = str(prior["fingerprint"])
            else:
                if total_bytes + stat.st_size > max_total_bytes:
                    truncated = True
                    continue
                digest, bytes_read = _hash_file(
                    resolved,
                    max_bytes=max_file_bytes,
                    deadline=deadline,
                )
                total_bytes += bytes_read
                identity = _stable(
                    {
                        "path": rel,
                        "size": stat.st_size,
                        "mtime_ns": stat.st_mtime_ns,
                        "sha256": digest,
                    }
                )
        except (OSError, TimeoutError, ValueError):
            truncated = True
            if time.monotonic() >= deadline:
                break
            continue
        snapshot[rel] = {
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "sha256": digest,
            "fingerprint": identity,
        }
        if previous and _snapshot_fingerprint(previous_snapshot.get(rel)) != identity:
            changed.append(
                (rel, identity, {"path": rel, "sha256": digest, "size": stat.st_size})
            )
    if previous and not truncated:
        for rel, prior_entry in previous_snapshot.items():
            if rel in snapshot:
                continue
            prior_identity = _snapshot_fingerprint(prior_entry) or "unknown"
            identity = _stable({"path": rel, "deleted": True, "prior": prior_identity})
            changed.append(
                (rel, identity, {"path": rel, "change_type": "deleted"})
            )
    if truncated and previous:
        snapshot = {**previous_snapshot, **snapshot}
    was_initialized = bool((previous or {}).get("initialized", previous is not None))
    initialized = was_initialized or not truncated
    emit_changes = was_initialized
    generation = int((previous or {}).get("generation", 0)) + (
        1 if changed and emit_changes else 0
    )
    observations: list[SourceObservation] = []
    if emit_changes and changed:
        ordered_changes = sorted(changed, key=lambda item: item[0])
        change_manifest = [
            {"path": rel, "fingerprint": fingerprint}
            for rel, fingerprint, _metadata in ordered_changes
        ]
        changed_paths = [rel for rel, _fingerprint, _metadata in ordered_changes[:20]]
        metadata: dict[str, Any] = {
            "change_type": "batch",
            "changed_count": len(ordered_changes),
            "changed_paths": changed_paths,
            "changes_sha256": _stable(change_manifest),
            "truncated": len(changed_paths) < len(ordered_changes),
        }
        if len(ordered_changes) == 1:
            metadata.update(ordered_changes[0][2])
        observations = [
            SourceObservation(
                _source_key("file", root),
                _stable({"generation": generation, "changes": change_manifest}),
                metadata,
            )
        ]
    return observations, {
        "snapshot": snapshot,
        "generation": generation,
        "initialized": initialized,
    }


def scan_git(
    trigger: Mapping[str, Any], *, previous: Mapping[str, Any] | None = None
) -> tuple[list[SourceObservation], dict[str, Any]]:
    if not bool(trigger.get("enabled", False)):
        return [], dict(previous or {})
    configured_workspace = trigger.get("workspace_root")
    configured_repo = trigger.get("repo_root")
    workspace_raw = configured_workspace or configured_repo
    if not workspace_raw:
        return [], dict(previous or {})
    workspace = Path(str(workspace_raw)).expanduser()
    try:
        workspace = workspace.resolve(strict=True)
        repo_raw = (configured_repo or ".") if configured_workspace else "."
        candidate = Path(str(repo_raw)).expanduser()
        root = (
            candidate if candidate.is_absolute() else workspace / candidate
        ).resolve(strict=True)
    except OSError:
        return [], dict(previous or {})
    if root != workspace and workspace not in root.parents:
        return [], dict(previous or {})
    git_environment = _git_environment()
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            shell=False,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
            env=git_environment,
        ).stdout.strip()
        branch = subprocess.run(
            ["git", "symbolic-ref", "--short", "-q", "HEAD"],
            cwd=root,
            shell=False,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
            env=git_environment,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return [], dict(previous or {})
    configured_branch = str(trigger.get("branch") or "").strip()
    if configured_branch and branch != configured_branch:
        return [], {
            "configured_branch": configured_branch,
            "branch_matched": False,
            "generation": int((previous or {}).get("generation", 0)),
        }
    fingerprint = _stable({"head": head, "branch": branch})
    previous_fingerprint = (previous or {}).get("fingerprint") or (previous or {}).get(
        "identity"
    )
    previous_matched = (previous or {}).get("branch_matched", True)
    changed = (
        bool(previous)
        and previous_matched is not False
        and previous_fingerprint != fingerprint
    )
    generation = int((previous or {}).get("generation", 0)) + (1 if changed else 0)
    state = {
        "head": head,
        "branch": branch,
        "fingerprint": fingerprint,
        "generation": generation,
        "branch_matched": True,
    }
    if not changed:
        return [], state
    identity = _stable({"fingerprint": fingerprint, "generation": generation})
    return [
        SourceObservation(
            _source_key("git", root),
            identity,
            {"head": head, "branch": branch},
        )
    ], state
