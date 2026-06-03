from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

COMMAND_TERMINAL_STATUSES = {"success", "failed", "timeout", "cancelled"}
PENDING_CHANGE_STATUSES = {"pending", "committed", "rejected", "stale", "failed"}
TODO_STATUSES = {"pending", "in_progress", "done", "failed", "blocked"}
VERIFICATION_STATUSES = {"pending", "passed", "failed", "blocked"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class StoredSession:
    id: str
    cwd: str
    agent_id: str
    mode: str
    target: str
    run_id: str | None
    active_leaf_id: str | None
    title: str
    created_at: str
    updated_at: str
    cli_mode: str = "chat"


class SessionStore:
    def __init__(self, db_path: Path, sessions_dir: Path) -> None:
        self.db_path = db_path
        self.sessions_dir = sessions_dir
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                create table if not exists sessions (
                    id text primary key,
                    cwd text not null,
                    agent_id text not null,
                    mode text not null,
                    cli_mode text not null,
                    target text not null,
                    run_id text,
                    active_leaf_id text,
                    title text not null,
                    created_at text not null,
                    updated_at text not null
                );
                create table if not exists messages (
                    id text primary key,
                    session_id text not null references sessions(id) on delete cascade,
                    seq integer not null,
                    parent_id text,
                    branch_id text not null,
                    role text not null,
                    content text not null,
                    state text not null,
                    run_id text,
                    source_message_id text,
                    tool_event_id text,
                    metadata_json text not null,
                    created_at text not null
                );
                create table if not exists tool_events (
                    id text primary key,
                    session_id text not null references sessions(id) on delete cascade,
                    run_id text,
                    tool_call_id text,
                    tool_name text not null,
                    status text not null,
                    input_json text not null,
                    output_json text not null,
                    duration_ms integer not null,
                    created_at text not null
                );
                create table if not exists commands (
                    id text primary key,
                    session_id text not null references sessions(id) on delete cascade,
                    tool_name text not null,
                    command text not null,
                    command_json text not null,
                    timeout_seconds integer not null,
                    status text not null,
                    started_at text,
                    finished_at text,
                    exit_code integer,
                    stdout_truncated integer not null default 0,
                    stderr_truncated integer not null default 0,
                    retry_of_id text,
                    tool_event_id text,
                    created_at text not null,
                    updated_at text not null
                );
                create table if not exists pending_changes (
                    id text primary key,
                    session_id text not null references sessions(id) on delete cascade,
                    tool_name text not null,
                    status text not null,
                    target_paths_json text not null,
                    before_hashes_json text not null,
                    after_hashes_json text not null,
                    diff text not null,
                    proposed_content_json text,
                    patch text,
                    input_json text not null,
                    tool_call_id text,
                    tool_event_id text,
                    error_message text,
                    metadata_json text not null default '{}',
                    created_at text not null,
                    updated_at text not null
                );
                create table if not exists todos (
                    id text primary key,
                    session_id text not null references sessions(id) on delete cascade,
                    branch_id text,
                    leaf_id text,
                    title text not null,
                    status text not null,
                    source text not null,
                    message_id text,
                    command_id text,
                    tool_event_id text,
                    verification_id text,
                    metadata_json text not null default '{}',
                    created_at text not null,
                    updated_at text not null
                );
                create table if not exists verifications (
                    id text primary key,
                    session_id text not null references sessions(id) on delete cascade,
                    branch_id text,
                    leaf_id text,
                    label text not null,
                    status text not null,
                    command_id text,
                    tool_event_id text,
                    evidence_summary text not null,
                    metadata_json text not null default '{}',
                    created_at text not null,
                    updated_at text not null
                );
                """
            )
            self._ensure_column(connection, "sessions", "cli_mode", "cli_mode text")
            self._ensure_column(connection, "sessions", "active_leaf_id", "active_leaf_id text")
            self._ensure_column(connection, "messages", "parent_id", "parent_id text")
            self._ensure_column(connection, "messages", "branch_id", "branch_id text")
            self._ensure_column(
                connection,
                "messages",
                "source_message_id",
                "source_message_id text",
            )
            self._ensure_column(connection, "messages", "tool_event_id", "tool_event_id text")
            self._ensure_column(connection, "commands", "tool_event_id", "tool_event_id text")
            self._ensure_column(connection, "commands", "retry_of_id", "retry_of_id text")
            self._ensure_column(connection, "commands", "started_at", "started_at text")
            self._ensure_column(connection, "commands", "finished_at", "finished_at text")
            self._ensure_column(connection, "commands", "exit_code", "exit_code integer")
            self._ensure_column(
                connection,
                "pending_changes",
                "metadata_json",
                "metadata_json text not null default '{}'",
            )
            self._ensure_column(
                connection,
                "commands",
                "stdout_truncated",
                "stdout_truncated integer not null default 0",
            )
            self._ensure_column(
                connection,
                "commands",
                "stderr_truncated",
                "stderr_truncated integer not null default 0",
            )
            self._backfill_session_columns(connection)
            self._backfill_tree_columns(connection)

    def _active_leaf_context(
        self,
        connection: sqlite3.Connection,
        session_id: str,
    ) -> tuple[str | None, str | None]:
        row = connection.execute(
            """
            select messages.id, messages.branch_id
            from sessions
            left join messages on messages.id = sessions.active_leaf_id
                and messages.session_id = sessions.id
            where sessions.id = ?
            """,
            (session_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"session not found: {session_id}")
        leaf_id = row["id"]
        branch_id = row["branch_id"]
        return (
            str(branch_id) if branch_id is not None else None,
            str(leaf_id) if leaf_id is not None else None,
        )

    def _ensure_column(
        self,
        connection: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        rows = connection.execute(f"pragma table_info({table})").fetchall()
        columns = {str(row["name"]) for row in rows}
        if column not in columns:
            connection.execute(f"alter table {table} add column {definition}")

    def _backfill_session_columns(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            "update sessions set cli_mode = 'chat' where cli_mode is null or trim(cli_mode) = ''"
        )

    def _backfill_tree_columns(self, connection: sqlite3.Connection) -> None:
        session_rows = connection.execute("select id, active_leaf_id from sessions").fetchall()
        for session_row in session_rows:
            rows = connection.execute(
                """
                select id, parent_id, branch_id
                from messages
                where session_id = ?
                order by seq asc, created_at asc, id asc
                """,
                (session_row["id"],),
            ).fetchall()
            if not rows:
                continue
            branch_id = str(rows[0]["branch_id"] or rows[0]["id"])
            previous_id: str | None = None
            for index, row in enumerate(rows):
                parent_id = row["parent_id"]
                if parent_id is None and index > 0:
                    parent_id = previous_id
                row_branch_id = str(row["branch_id"] or branch_id)
                if parent_id != row["parent_id"] or row_branch_id != row["branch_id"]:
                    connection.execute(
                        "update messages set parent_id = ?, branch_id = ? where id = ?",
                        (parent_id, row_branch_id, row["id"]),
                    )
                previous_id = str(row["id"])
            if session_row["active_leaf_id"] is None:
                connection.execute(
                    "update sessions set active_leaf_id = ? where id = ?",
                    (rows[-1]["id"], session_row["id"]),
                )

    def session_dir(self, session_id: str) -> Path:
        path = self.sessions_dir / session_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _append_jsonl(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, default=str))
            handle.write("\n")

    def _artifact_name(self, event_id: str, tool_name: str, suffix: str) -> str:
        safe_tool = "".join(
            char if char.isalnum() or char in {"-", "_"} else "-"
            for char in tool_name
        ).strip("-")
        return f"{event_id}-{safe_tool or 'tool'}{suffix}"

    def _commands_jsonl_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "commands.jsonl"

    def _append_command_event(self, session_id: str, payload: dict[str, Any]) -> None:
        self._append_jsonl(self._commands_jsonl_path(session_id), payload)

    def _pending_change_artifact_path(self, session_id: str, change_id: str) -> Path:
        return self.session_dir(session_id) / "pending-changes" / f"{change_id}.json"

    def _pending_change_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "session_id": row["session_id"],
            "tool_name": row["tool_name"],
            "status": row["status"],
            "target_paths": json.loads(row["target_paths_json"] or "[]"),
            "before_hashes": json.loads(row["before_hashes_json"] or "{}"),
            "after_hashes": json.loads(row["after_hashes_json"] or "{}"),
            "diff": row["diff"],
            "proposed_content": (
                json.loads(row["proposed_content_json"])
                if row["proposed_content_json"]
                else None
            ),
            "patch": row["patch"],
            "input_json": json.loads(row["input_json"] or "{}"),
            "tool_call_id": row["tool_call_id"],
            "tool_event_id": row["tool_event_id"],
            "error_message": row["error_message"],
            "metadata": json.loads(row["metadata_json"] or "{}"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _write_pending_change_artifact(self, change: dict[str, Any]) -> None:
        path = self._pending_change_artifact_path(change["session_id"], change["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(change, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )

    def _fetch_pending_change_row(
        self,
        connection: sqlite3.Connection,
        change_id: str,
    ) -> sqlite3.Row | None:
        return connection.execute(
            "select * from pending_changes where id = ?",
            (change_id,),
        ).fetchone()

    def get_pending_change(self, change_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = self._fetch_pending_change_row(connection, change_id)
        if row is None:
            return None
        return self._pending_change_from_row(row)

    def list_pending_changes(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                select * from pending_changes
                where session_id = ?
                order by created_at asc, id asc
                """,
                (session_id,),
            ).fetchall()
        return [self._pending_change_from_row(row) for row in rows]

    def create_pending_change(
        self,
        session_id: str,
        *,
        tool_name: str,
        target_paths: list[str],
        before_hashes: dict[str, str],
        after_hashes: dict[str, str],
        diff: str,
        proposed_content: dict[str, Any] | None = None,
        patch: str | None = None,
        input_json: dict[str, Any] | None = None,
        tool_call_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = _now()
        change_id = f"change-{uuid4()}"
        with self._connect() as connection:
            session_row = connection.execute(
                "select id from sessions where id = ?",
                (session_id,),
            ).fetchone()
            if session_row is None:
                raise ValueError(f"session not found: {session_id}")
            connection.execute(
                """
                insert into pending_changes
                (id, session_id, tool_name, status, target_paths_json,
                 before_hashes_json, after_hashes_json, diff, proposed_content_json,
                 patch, input_json, tool_call_id, tool_event_id, error_message,
                 metadata_json, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, null, null, ?, ?, ?)
                """,
                (
                    change_id,
                    session_id,
                    tool_name,
                    "pending",
                    json.dumps(target_paths, ensure_ascii=False),
                    json.dumps(before_hashes, ensure_ascii=False),
                    json.dumps(after_hashes, ensure_ascii=False),
                    diff,
                    (
                        json.dumps(proposed_content, ensure_ascii=False)
                        if proposed_content is not None
                        else None
                    ),
                    patch,
                    json.dumps(input_json or {}, ensure_ascii=False),
                    tool_call_id,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        change = self.get_pending_change(change_id)
        if change is None:
            raise ValueError(f"pending change not found after create: {change_id}")
        self._write_pending_change_artifact(change)
        return change

    def update_pending_change_status(
        self,
        change_id: str,
        *,
        status: str,
        error_message: str | None = None,
        tool_event_id: str | None = None,
    ) -> dict[str, Any]:
        if status not in PENDING_CHANGE_STATUSES:
            raise ValueError(f"unsupported pending change status: {status}")
        now = _now()
        with self._connect() as connection:
            row = self._fetch_pending_change_row(connection, change_id)
            if row is None:
                raise ValueError(f"pending change not found: {change_id}")
            connection.execute(
                """
                update pending_changes
                set status = ?, error_message = ?, tool_event_id = coalesce(?, tool_event_id),
                    updated_at = ?
                where id = ?
                """,
                (status, error_message, tool_event_id, now, change_id),
            )
        change = self.get_pending_change(change_id)
        if change is None:
            raise ValueError(f"pending change not found after update: {change_id}")
        self._write_pending_change_artifact(change)
        return change

    def link_pending_change_tool_event(
        self,
        change_id: str,
        tool_event_id: str,
    ) -> dict[str, Any]:
        now = _now()
        with self._connect() as connection:
            row = self._fetch_pending_change_row(connection, change_id)
            if row is None:
                raise ValueError(f"pending change not found: {change_id}")
            connection.execute(
                """
                update pending_changes
                set tool_event_id = ?, updated_at = ?
                where id = ?
                """,
                (tool_event_id, now, change_id),
            )
        change = self.get_pending_change(change_id)
        if change is None:
            raise ValueError(f"pending change not found after link: {change_id}")
        self._write_pending_change_artifact(change)
        return change

    def _command_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "session_id": row["session_id"],
            "tool_name": row["tool_name"],
            "command": row["command"],
            "command_json": json.loads(row["command_json"] or "{}"),
            "timeout_seconds": row["timeout_seconds"],
            "status": row["status"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "exit_code": row["exit_code"],
            "stdout_truncated": bool(row["stdout_truncated"]),
            "stderr_truncated": bool(row["stderr_truncated"]),
            "retry_of_id": row["retry_of_id"],
            "tool_event_id": row["tool_event_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _fetch_command_row(
        self,
        connection: sqlite3.Connection,
        command_id: str,
    ) -> sqlite3.Row | None:
        return connection.execute(
            "select * from commands where id = ?",
            (command_id,),
        ).fetchone()

    def get_command(self, command_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = self._fetch_command_row(connection, command_id)
        if row is None:
            return None
        return self._command_from_row(row)

    def list_commands(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "select * from commands where session_id = ? order by created_at asc, id asc",
                (session_id,),
            ).fetchall()
        return [self._command_from_row(row) for row in rows]

    def create_command(
        self,
        session_id: str,
        *,
        tool_name: str,
        command: str,
        command_json: dict[str, Any],
        timeout_seconds: int,
        retry_of_id: str | None = None,
    ) -> dict[str, Any]:
        now = _now()
        command_id = str(uuid4())
        with self._connect() as connection:
            session_row = connection.execute(
                "select id from sessions where id = ?",
                (session_id,),
            ).fetchone()
            if session_row is None:
                raise ValueError(f"session not found: {session_id}")
            connection.execute(
                """
                insert into commands
                (id, session_id, tool_name, command, command_json, timeout_seconds,
                 status, started_at, finished_at, exit_code, stdout_truncated,
                 stderr_truncated, retry_of_id, tool_event_id, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, null, null, null, 0, 0, ?, null, ?, ?)
                """,
                (
                    command_id,
                    session_id,
                    tool_name,
                    command,
                    json.dumps(command_json, ensure_ascii=False),
                    timeout_seconds,
                    "pending",
                    retry_of_id,
                    now,
                    now,
                ),
            )
        self._append_command_event(
            session_id,
            {
                "created_at": now,
                "event": "pending",
                "command_id": command_id,
                "status": "pending",
                "tool_name": tool_name,
                "command": command,
                "command_json": command_json,
                "timeout_seconds": timeout_seconds,
                "retry_of_id": retry_of_id,
            },
        )
        return self.get_command(command_id)  # type: ignore[return-value]

    def start_command(self, command_id: str) -> dict[str, Any]:
        now = _now()
        with self._connect() as connection:
            row = self._fetch_command_row(connection, command_id)
            if row is None:
                raise ValueError(f"command not found: {command_id}")
            if str(row["status"]) != "pending":
                raise ValueError(
                    f"command is not pending and cannot be started: {command_id}"
                )
            connection.execute(
                "update commands set status = ?, started_at = ?, updated_at = ? where id = ?",
                ("running", now, now, command_id),
            )
        command = self.get_command(command_id)
        if command is None:
            raise ValueError(f"command not found after update: {command_id}")
        self._append_command_event(
            command["session_id"],
            {
                "created_at": now,
                "event": "running",
                "command_id": command_id,
                "status": "running",
                "started_at": now,
            },
        )
        return command

    def record_command_output(
        self,
        command_id: str,
        *,
        stream: str,
        chunk: str,
    ) -> None:
        now = _now()
        with self._connect() as connection:
            row = self._fetch_command_row(connection, command_id)
            if row is None:
                raise ValueError(f"command not found: {command_id}")
            if str(row["status"]) != "running":
                raise ValueError(
                    f"command is not running and cannot record output: {command_id}"
                )
            session_id = str(row["session_id"])
        self._append_command_event(
            session_id,
            {
                "created_at": now,
                "event": "output",
                "command_id": command_id,
                "status": "running",
                "stream": stream,
                "chunk": chunk,
            },
        )

    def record_command_output_truncated(
        self,
        command_id: str,
        *,
        stream: str,
        limit_bytes: int,
    ) -> None:
        now = _now()
        with self._connect() as connection:
            row = self._fetch_command_row(connection, command_id)
            if row is None:
                raise ValueError(f"command not found: {command_id}")
            if str(row["status"]) != "running":
                raise ValueError(
                    f"command is not running and cannot record truncation: {command_id}"
                )
            session_id = str(row["session_id"])
        self._append_command_event(
            session_id,
            {
                "created_at": now,
                "event": "output_truncated",
                "command_id": command_id,
                "status": "running",
                "stream": stream,
                "limit_bytes": limit_bytes,
                "truncated": True,
            },
        )

    def finish_command(
        self,
        command_id: str,
        *,
        status: str,
        exit_code: int | None,
        stdout_truncated: bool,
        stderr_truncated: bool,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        if status not in COMMAND_TERMINAL_STATUSES:
            raise ValueError(f"unsupported terminal command status: {status}")
        now = _now()
        with self._connect() as connection:
            row = self._fetch_command_row(connection, command_id)
            if row is None:
                raise ValueError(f"command not found: {command_id}")
            if str(row["status"]) in COMMAND_TERMINAL_STATUSES:
                raise ValueError(f"command already finished: {command_id}")
            if str(row["status"]) != "running":
                raise ValueError(f"command is not running: {command_id}")
            session_id = str(row["session_id"])
            connection.execute(
                """
                update commands
                set status = ?, finished_at = ?, exit_code = ?, stdout_truncated = ?,
                    stderr_truncated = ?, updated_at = ?
                where id = ?
                """,
                (
                    status,
                    now,
                    exit_code,
                    int(stdout_truncated),
                    int(stderr_truncated),
                    now,
                    command_id,
                ),
            )
        self._append_command_event(
            session_id,
            {
                "created_at": now,
                "event": status,
                "command_id": command_id,
                "status": status,
                "finished_at": now,
                "exit_code": exit_code,
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
                "error_message": error_message,
            },
        )
        command = self.get_command(command_id)
        if command is None:
            raise ValueError(f"command not found after finish: {command_id}")
        return command

    def link_command_tool_event(self, command_id: str, tool_event_id: str) -> dict[str, Any]:
        now = _now()
        with self._connect() as connection:
            row = self._fetch_command_row(connection, command_id)
            if row is None:
                raise ValueError(f"command not found: {command_id}")
            session_id = str(row["session_id"])
            connection.execute(
                "update commands set tool_event_id = ?, updated_at = ? where id = ?",
                (tool_event_id, now, command_id),
            )
        self._append_command_event(
            session_id,
            {
                "created_at": now,
                "event": "linked",
                "command_id": command_id,
                "status": "linked",
                "tool_event_id": tool_event_id,
            },
        )
        command = self.get_command(command_id)
        if command is None:
            raise ValueError(f"command not found after link: {command_id}")
        return command

    def retry_command(self, command_id: str) -> dict[str, Any]:
        command = self.get_command(command_id)
        if command is None:
            raise ValueError(f"command not found: {command_id}")
        if command["status"] not in COMMAND_TERMINAL_STATUSES:
            raise ValueError(f"command is not terminal and cannot be retried: {command_id}")
        return self.create_command(
            command["session_id"],
            tool_name=command["tool_name"],
            command=command["command"],
            command_json=command["command_json"],
            timeout_seconds=command["timeout_seconds"],
            retry_of_id=command["id"],
        )

    def _todo_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "session_id": row["session_id"],
            "branch_id": row["branch_id"],
            "leaf_id": row["leaf_id"],
            "title": row["title"],
            "status": row["status"],
            "source": row["source"],
            "message_id": row["message_id"],
            "command_id": row["command_id"],
            "tool_event_id": row["tool_event_id"],
            "verification_id": row["verification_id"],
            "metadata": json.loads(row["metadata_json"] or "{}"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _fetch_todo_row(
        self,
        connection: sqlite3.Connection,
        todo_id: str,
    ) -> sqlite3.Row | None:
        return connection.execute(
            "select * from todos where id = ?",
            (todo_id,),
        ).fetchone()

    def get_todo(self, todo_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = self._fetch_todo_row(connection, todo_id)
        if row is None:
            return None
        return self._todo_from_row(row)

    def list_todos(
        self,
        session_id: str,
        *,
        branch_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "select * from todos where session_id = ?"
        params: list[Any] = [session_id]
        if branch_id is not None:
            query += " and branch_id = ?"
            params.append(branch_id)
        query += " order by created_at asc, id asc"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._todo_from_row(row) for row in rows]

    def create_todo(
        self,
        session_id: str,
        *,
        title: str,
        source: str,
        branch_id: str | None = None,
        leaf_id: str | None = None,
        status: str = "pending",
        message_id: str | None = None,
        command_id: str | None = None,
        tool_event_id: str | None = None,
        verification_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if status not in TODO_STATUSES:
            raise ValueError(f"unsupported todo status: {status}")
        title = title.strip()
        if not title:
            raise ValueError("todo title is required")
        now = _now()
        todo_id = f"todo-{uuid4()}"
        with self._connect() as connection:
            active_branch_id, active_leaf_id = self._active_leaf_context(
                connection,
                session_id,
            )
            resolved_branch_id = branch_id or active_branch_id
            resolved_leaf_id = leaf_id or active_leaf_id
            connection.execute(
                """
                insert into todos
                (id, session_id, branch_id, leaf_id, title, status, source, message_id,
                 command_id, tool_event_id, verification_id, metadata_json, created_at,
                 updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    todo_id,
                    session_id,
                    resolved_branch_id,
                    resolved_leaf_id,
                    title,
                    status,
                    source,
                    message_id,
                    command_id,
                    tool_event_id,
                    verification_id,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            connection.execute(
                "update sessions set updated_at = ? where id = ?",
                (now, session_id),
            )
        todo = self.get_todo(todo_id)
        if todo is None:
            raise ValueError(f"todo not found after create: {todo_id}")
        return todo

    def update_todo(
        self,
        todo_id: str,
        *,
        status: str | None = None,
        title: str | None = None,
        command_id: str | None = None,
        tool_event_id: str | None = None,
        verification_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if status is not None and status not in TODO_STATUSES:
            raise ValueError(f"unsupported todo status: {status}")
        now = _now()
        with self._connect() as connection:
            row = self._fetch_todo_row(connection, todo_id)
            if row is None:
                raise ValueError(f"todo not found: {todo_id}")
            next_title = row["title"] if title is None else title.strip()
            if not next_title:
                raise ValueError("todo title is required")
            next_metadata = (
                json.loads(row["metadata_json"] or "{}")
                if metadata is None
                else metadata
            )
            connection.execute(
                """
                update todos
                set title = ?, status = ?, command_id = coalesce(?, command_id),
                    tool_event_id = coalesce(?, tool_event_id),
                    verification_id = coalesce(?, verification_id),
                    metadata_json = ?, updated_at = ?
                where id = ?
                """,
                (
                    next_title,
                    row["status"] if status is None else status,
                    command_id,
                    tool_event_id,
                    verification_id,
                    json.dumps(next_metadata, ensure_ascii=False),
                    now,
                    todo_id,
                ),
            )
            connection.execute(
                "update sessions set updated_at = ? where id = ?",
                (now, row["session_id"]),
            )
        todo = self.get_todo(todo_id)
        if todo is None:
            raise ValueError(f"todo not found after update: {todo_id}")
        return todo

    def _verification_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "session_id": row["session_id"],
            "branch_id": row["branch_id"],
            "leaf_id": row["leaf_id"],
            "label": row["label"],
            "status": row["status"],
            "command_id": row["command_id"],
            "tool_event_id": row["tool_event_id"],
            "evidence_summary": row["evidence_summary"],
            "metadata": json.loads(row["metadata_json"] or "{}"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _fetch_verification_row(
        self,
        connection: sqlite3.Connection,
        verification_id: str,
    ) -> sqlite3.Row | None:
        return connection.execute(
            "select * from verifications where id = ?",
            (verification_id,),
        ).fetchone()

    def get_verification(self, verification_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = self._fetch_verification_row(connection, verification_id)
        if row is None:
            return None
        return self._verification_from_row(row)

    def list_verifications(
        self,
        session_id: str,
        *,
        branch_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "select * from verifications where session_id = ?"
        params: list[Any] = [session_id]
        if branch_id is not None:
            query += " and branch_id = ?"
            params.append(branch_id)
        query += " order by created_at asc, id asc"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._verification_from_row(row) for row in rows]

    def create_verification(
        self,
        session_id: str,
        *,
        label: str,
        status: str,
        branch_id: str | None = None,
        leaf_id: str | None = None,
        command_id: str | None = None,
        tool_event_id: str | None = None,
        evidence_summary: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if status not in VERIFICATION_STATUSES:
            raise ValueError(f"unsupported verification status: {status}")
        label = label.strip()
        if not label:
            raise ValueError("verification label is required")
        now = _now()
        verification_id = f"verify-{uuid4()}"
        with self._connect() as connection:
            active_branch_id, active_leaf_id = self._active_leaf_context(
                connection,
                session_id,
            )
            resolved_branch_id = branch_id or active_branch_id
            resolved_leaf_id = leaf_id or active_leaf_id
            connection.execute(
                """
                insert into verifications
                (id, session_id, branch_id, leaf_id, label, status, command_id,
                 tool_event_id, evidence_summary, metadata_json, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    verification_id,
                    session_id,
                    resolved_branch_id,
                    resolved_leaf_id,
                    label,
                    status,
                    command_id,
                    tool_event_id,
                    evidence_summary,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            connection.execute(
                "update sessions set updated_at = ? where id = ?",
                (now, session_id),
            )
        verification = self.get_verification(verification_id)
        if verification is None:
            raise ValueError(f"verification not found after create: {verification_id}")
        return verification

    def update_verification(
        self,
        verification_id: str,
        *,
        status: str | None = None,
        evidence_summary: str | None = None,
        command_id: str | None = None,
        tool_event_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if status is not None and status not in VERIFICATION_STATUSES:
            raise ValueError(f"unsupported verification status: {status}")
        now = _now()
        with self._connect() as connection:
            row = self._fetch_verification_row(connection, verification_id)
            if row is None:
                raise ValueError(f"verification not found: {verification_id}")
            next_metadata = (
                json.loads(row["metadata_json"] or "{}")
                if metadata is None
                else metadata
            )
            connection.execute(
                """
                update verifications
                set status = ?, evidence_summary = ?, command_id = coalesce(?, command_id),
                    tool_event_id = coalesce(?, tool_event_id), metadata_json = ?,
                    updated_at = ?
                where id = ?
                """,
                (
                    row["status"] if status is None else status,
                    (
                        row["evidence_summary"]
                        if evidence_summary is None
                        else evidence_summary
                    ),
                    command_id,
                    tool_event_id,
                    json.dumps(next_metadata, ensure_ascii=False),
                    now,
                    verification_id,
                ),
            )
            connection.execute(
                "update sessions set updated_at = ? where id = ?",
                (now, row["session_id"]),
            )
        verification = self.get_verification(verification_id)
        if verification is None:
            raise ValueError(f"verification not found after update: {verification_id}")
        return verification

    def record_stream_event(
        self,
        session_id: str,
        *,
        event: str,
        data: dict[str, Any],
        raw: str = "",
    ) -> None:
        self._append_jsonl(
            self.session_dir(session_id) / "stream.jsonl",
            {
                "created_at": _now(),
                "event": event,
                "data": data,
                "raw": raw,
            },
        )

    def create_session(
        self,
        *,
        cwd: str,
        agent_id: str,
        mode: str,
        target: str,
        cli_mode: str = "chat",
        title: str = "hao session",
    ) -> StoredSession:
        session_id = str(uuid4())
        now = _now()
        with self._connect() as connection:
            connection.execute(
                """
                insert into sessions
                (id, cwd, agent_id, mode, cli_mode, target, run_id, active_leaf_id, title,
                 created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, null, null, ?, ?, ?)
                """,
                (session_id, cwd, agent_id, mode, cli_mode, target, title, now, now),
            )
        self.session_dir(session_id)
        return self.get_session(session_id)  # type: ignore[return-value]

    def get_session(self, session_id: str) -> StoredSession | None:
        with self._connect() as connection:
            row = connection.execute(
                "select * from sessions where id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return StoredSession(**dict(row))

    def list_sessions(self, limit: int = 20) -> list[StoredSession]:
        with self._connect() as connection:
            rows = connection.execute(
                "select * from sessions order by updated_at desc limit ?",
                (limit,),
            ).fetchall()
        return [StoredSession(**dict(row)) for row in rows]

    def update_run_id(self, session_id: str, run_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "update sessions set run_id = ?, updated_at = ? where id = ?",
                (run_id, _now(), session_id),
            )

    def update_mode_target(self, session_id: str, *, mode: str, target: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "update sessions set mode = ?, target = ?, updated_at = ? where id = ?",
                (mode, target, _now(), session_id),
            )

    def update_cli_mode(self, session_id: str, cli_mode: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "update sessions set cli_mode = ?, updated_at = ? where id = ?",
                (cli_mode, _now(), session_id),
            )

    def append_message(
        self,
        session_id: str,
        *,
        role: str,
        content: str,
        state: str = "done",
        run_id: str | None = None,
        parent_id: str | None = None,
        branch_id: str | None = None,
        source_message_id: str | None = None,
        tool_event_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = _now()
        message_id = str(uuid4())
        with self._connect() as connection:
            session_row = connection.execute(
                "select active_leaf_id from sessions where id = ?",
                (session_id,),
            ).fetchone()
            if session_row is None:
                raise ValueError(f"session not found: {session_id}")
            explicit_parent = parent_id is not None
            resolved_parent_id = parent_id if explicit_parent else session_row["active_leaf_id"]
            parent_branch_id: str | None = None
            if resolved_parent_id is not None:
                parent_row = connection.execute(
                    """
                    select branch_id
                    from messages
                    where session_id = ? and id = ?
                    """,
                    (session_id, resolved_parent_id),
                ).fetchone()
                if parent_row is None:
                    raise ValueError(
                        f"parent message not found in session {session_id}: "
                        f"{resolved_parent_id}"
                    )
                parent_branch_id = str(parent_row["branch_id"] or "")
            resolved_branch_id = branch_id
            if not resolved_branch_id:
                if resolved_parent_id is None:
                    resolved_branch_id = message_id
                elif explicit_parent:
                    resolved_branch_id = message_id
                else:
                    resolved_branch_id = parent_branch_id or message_id
            row = connection.execute(
                "select coalesce(max(seq), 0) + 1 from messages where session_id = ?",
                (session_id,),
            ).fetchone()
            seq = int(row[0])
            connection.execute(
                """
                insert into messages
                (id, session_id, seq, parent_id, branch_id, role, content, state,
                 run_id, source_message_id, tool_event_id, metadata_json, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    session_id,
                    seq,
                    resolved_parent_id,
                    resolved_branch_id,
                    role,
                    content,
                    state,
                    run_id,
                    source_message_id,
                    tool_event_id,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    now,
                ),
            )
            connection.execute(
                "update sessions set active_leaf_id = ?, updated_at = ? where id = ?",
                (message_id, now, session_id),
            )
        return {
            "id": message_id,
            "seq": seq,
            "parent_id": resolved_parent_id,
            "children_ids": [],
            "branch_id": resolved_branch_id,
            "role": role,
            "content": content,
            "state": state,
            "run_id": run_id,
            "source_message_id": source_message_id,
            "tool_event_id": tool_event_id,
            "metadata": metadata or {},
            "created_at": now,
        }

    def _message_rows(
        self,
        connection: sqlite3.Connection,
        session_id: str,
    ) -> list[sqlite3.Row]:
        return connection.execute(
            """
            select *
            from messages
            where session_id = ?
            order by seq asc, created_at asc, id asc
            """,
            (session_id,),
        ).fetchall()

    def _children_by_parent(self, rows: list[sqlite3.Row]) -> dict[str, list[str]]:
        children: dict[str, list[str]] = {}
        for row in rows:
            parent_id = row["parent_id"]
            if parent_id is not None:
                children.setdefault(str(parent_id), []).append(str(row["id"]))
        return children

    def _message_from_row(
        self,
        row: sqlite3.Row,
        children_by_parent: dict[str, list[str]],
    ) -> dict[str, Any]:
        metadata = json.loads(row["metadata_json"] or "{}")
        return {
            "id": row["id"],
            "seq": row["seq"],
            "parent_id": row["parent_id"],
            "children_ids": children_by_parent.get(str(row["id"]), []),
            "branch_id": row["branch_id"],
            "role": row["role"],
            "content": row["content"],
            "state": row["state"],
            "run_id": row["run_id"],
            "source_message_id": row["source_message_id"],
            "tool_event_id": row["tool_event_id"],
            "metadata": metadata,
            "created_at": row["created_at"],
        }

    def list_messages(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = self._message_rows(connection, session_id)
        children_by_parent = self._children_by_parent(rows)
        return [self._message_from_row(row, children_by_parent) for row in rows]

    def list_active_path(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            session_row = connection.execute(
                "select active_leaf_id from sessions where id = ?",
                (session_id,),
            ).fetchone()
            if session_row is None:
                return []
            rows = self._message_rows(connection, session_id)
        if not rows:
            return []
        row_by_id = {str(row["id"]): row for row in rows}
        active_leaf_id = session_row["active_leaf_id"] or rows[-1]["id"]
        path: list[sqlite3.Row] = []
        seen: set[str] = set()
        current_id = str(active_leaf_id)
        while current_id and current_id not in seen:
            row = row_by_id.get(current_id)
            if row is None:
                break
            path.append(row)
            seen.add(current_id)
            parent_id = row["parent_id"]
            current_id = str(parent_id) if parent_id is not None else ""
        path.reverse()
        children_by_parent = self._children_by_parent(rows)
        return [self._message_from_row(row, children_by_parent) for row in path]

    def set_active_leaf(self, session_id: str, message_id: str) -> None:
        now = _now()
        with self._connect() as connection:
            row = connection.execute(
                "select id from messages where session_id = ? and id = ?",
                (session_id, message_id),
            ).fetchone()
            if row is None:
                raise ValueError(
                    f"active leaf message not found in session {session_id}: {message_id}"
                )
            connection.execute(
                "update sessions set active_leaf_id = ?, updated_at = ? where id = ?",
                (message_id, now, session_id),
            )

    def list_tool_events(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "select * from tool_events where session_id = ? order by created_at asc, id asc",
                (session_id,),
            ).fetchall()
        events: list[dict[str, Any]] = []
        for row in rows:
            events.append(
                {
                    "id": row["id"],
                    "session_id": row["session_id"],
                    "run_id": row["run_id"],
                    "tool_call_id": row["tool_call_id"],
                    "tool_name": row["tool_name"],
                    "status": row["status"],
                    "input_json": json.loads(row["input_json"] or "{}"),
                    "output_json": json.loads(row["output_json"] or "{}"),
                    "duration_ms": row["duration_ms"],
                    "created_at": row["created_at"],
                }
            )
        return events

    def record_tool_event(
        self,
        session_id: str,
        *,
        run_id: str | None,
        tool_call_id: str | None,
        tool_name: str,
        status: str,
        input_json: dict,
        output_json: dict,
        duration_ms: int,
    ) -> str:
        now = _now()
        event_id = str(uuid4())
        with self._connect() as connection:
            connection.execute(
                """
                insert into tool_events
                (id, session_id, run_id, tool_call_id, tool_name, status,
                 input_json, output_json, duration_ms, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    session_id,
                    run_id,
                    tool_call_id,
                    tool_name,
                    status,
                    json.dumps(input_json, ensure_ascii=False),
                    json.dumps(output_json, ensure_ascii=False),
                    duration_ms,
                    now,
                ),
            )
            connection.execute(
                "update sessions set updated_at = ? where id = ?",
                (now, session_id),
            )
        self._record_tool_artifacts(
            session_id,
            event_id=event_id,
            created_at=now,
            run_id=run_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            status=status,
            input_json=input_json,
            output_json=output_json,
            duration_ms=duration_ms,
        )
        return event_id

    def _record_tool_artifacts(
        self,
        session_id: str,
        *,
        event_id: str,
        created_at: str,
        run_id: str | None,
        tool_call_id: str | None,
        tool_name: str,
        status: str,
        input_json: dict,
        output_json: dict,
        duration_ms: int,
    ) -> None:
        session_dir = self.session_dir(session_id)
        payload = {
            "id": event_id,
            "created_at": created_at,
            "run_id": run_id,
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "status": status,
            "input_json": input_json,
            "output_json": output_json,
            "duration_ms": duration_ms,
        }
        self._append_jsonl(session_dir / "tool-events.jsonl", payload)

        diff = output_json.get("diff")
        if isinstance(diff, str) and diff.strip():
            diff_path = (
                session_dir
                / "diffs"
                / self._artifact_name(event_id, tool_name, ".diff")
            )
            diff_path.parent.mkdir(parents=True, exist_ok=True)
            diff_path.write_text(diff, encoding="utf-8")

        output_keys = {
            "command",
            "exit_code",
            "stdout",
            "stderr",
            "truncated",
            "error",
            "timeout_seconds",
        }
        if any(key in output_json for key in output_keys):
            output_path = (
                session_dir
                / "outputs"
                / self._artifact_name(event_id, tool_name, ".json")
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(
                    {
                        "id": event_id,
                        "created_at": created_at,
                        "tool_name": tool_name,
                        "status": status,
                        "input_json": input_json,
                        "output_json": {
                            key: output_json[key]
                            for key in output_keys
                            if key in output_json
                        },
                        "duration_ms": duration_ms,
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
                + "\n",
                encoding="utf-8",
            )
