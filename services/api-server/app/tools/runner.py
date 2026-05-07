from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from shlex import quote

from sqlalchemy.orm import Session

from app.db.models import SandboxInstance, ToolCall, utc_now
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.sandbox.docker_manager import SandboxCommandTimeoutError
from app.sandbox.policies import PolicyEngine, SandboxPolicyDecision
from app.tools.filesystem import WorkspaceFileTool
from app.tools.registry import ToolMetadata, ToolRegistry
from app.tools.shell import ShellTool, ShellToolRequest


@dataclass(frozen=True)
class ToolExecution:
    tool_call: ToolCall
    allowed: bool
    output: dict


class ToolRunner:
    def __init__(
        self,
        *,
        session: Session,
        workspace_root: Path | None = None,
        registry: ToolRegistry | None = None,
        shell_tool: ShellTool | None = None,
    ) -> None:
        self.session = session
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.registry = registry or ToolRegistry.default()
        self.shell_tool = shell_tool or ShellTool()
        self.event_store = EventStore(session)
        self.policy_engine = PolicyEngine(session)

    def execute(
        self,
        *,
        task_id: str,
        tool_name: str,
        input_json: dict,
        roles: list[str] | None = None,
        agent_run_id: str | None = None,
        sandbox: SandboxInstance | None = None,
    ) -> ToolExecution:
        metadata = self._metadata(tool_name)
        role_names = roles or ["engineer"]
        decision = self._check_policy(
            task_id=task_id,
            metadata=metadata,
            roles=role_names,
            sandbox=sandbox,
        )
        requires_sandbox = (
            decision.requires_sandbox
            if decision.requires_sandbox is not None
            else metadata.requires_sandbox
        )
        if not decision.allowed:
            return self._deny(
                task_id=task_id,
                agent_run_id=agent_run_id,
                metadata=metadata,
                input_json=input_json,
                decision=decision,
                requires_sandbox=requires_sandbox,
            )
        if metadata.name == "network_request":
            network_decision = self.policy_engine.evaluate_network_request(
                task_id=task_id,
                url=str(input_json.get("url", "")),
            )
            if not network_decision.allowed:
                return self._deny(
                    task_id=task_id,
                    agent_run_id=agent_run_id,
                    metadata=metadata,
                    input_json=input_json,
                    decision=network_decision,
                    requires_sandbox=requires_sandbox,
                )

        started_at = time.monotonic()
        tool_call = ToolCall(
            task_id=task_id,
            agent_run_id=agent_run_id,
            tool_name=metadata.name,
            status="RUNNING",
            risk_level=metadata.risk_level,
            requires_sandbox=requires_sandbox,
            sandbox_id=sandbox.id if sandbox is not None else None,
            duration_ms=0,
            input_json=input_json,
            output_json={},
            created_at=utc_now(),
        )
        self.session.add(tool_call)
        self.session.flush()
        self.event_store.append(
            task_id=task_id,
            agent_run_id=agent_run_id,
            event_type=EventType.POLICY_CHECKED,
            payload_json={
                "tool_call_id": tool_call.id,
                "tool_name": metadata.name,
                "allowed": True,
                "policy_id": decision.policy_id,
                "reason": decision.reason,
                "audit_level": decision.audit_level,
                "requires_sandbox": requires_sandbox,
            },
        )
        self.event_store.append(
            task_id=task_id,
            agent_run_id=agent_run_id,
            event_type=EventType.TOOL_CALLED,
            payload_json={"tool_call_id": tool_call.id, "tool_name": metadata.name},
        )

        try:
            output = self._execute_allowed(metadata, input_json, sandbox)
        except SandboxCommandTimeoutError as exc:
            tool_call.status = "TIMEOUT"
            tool_call.error_message = str(exc)
            output = {"error": str(exc)}
            event_type = EventType.TOOL_TIMEOUT
        except Exception as exc:
            tool_call.status = "FAILED"
            tool_call.error_message = str(exc)
            output = {"error": str(exc)}
            event_type = EventType.TOOL_FAILED
        else:
            tool_call.status = "SUCCESS"
            event_type = EventType.TOOL_RESULT_RECEIVED

        tool_call.duration_ms = int((time.monotonic() - started_at) * 1000)
        tool_call.output_json = output
        self.event_store.append(
            task_id=task_id,
            agent_run_id=agent_run_id,
            event_type=event_type,
            payload_json={
                "tool_call_id": tool_call.id,
                "tool_name": metadata.name,
                "status": tool_call.status,
            },
        )
        self.session.flush()
        return ToolExecution(
            tool_call=tool_call,
            allowed=True,
            output=output,
        )

    def _metadata(self, tool_name: str) -> ToolMetadata:
        metadata = self.registry.tools.get(tool_name)
        if metadata is None:
            raise ValueError(f"unknown tool: {tool_name}")
        return metadata

    def _check_policy(
        self,
        *,
        task_id: str,
        metadata: ToolMetadata,
        roles: list[str],
        sandbox: SandboxInstance | None,
    ) -> SandboxPolicyDecision:
        return self.policy_engine.evaluate_tool(
            task_id=task_id,
            metadata=metadata,
            roles=roles,
            sandbox_present=sandbox is not None,
        )

    def _deny(
        self,
        *,
        task_id: str,
        agent_run_id: str | None,
        metadata: ToolMetadata,
        input_json: dict,
        decision: SandboxPolicyDecision,
        requires_sandbox: bool,
    ) -> ToolExecution:
        tool_call = ToolCall(
            task_id=task_id,
            agent_run_id=agent_run_id,
            tool_name=metadata.name,
            status="DENIED",
            risk_level=metadata.risk_level,
            requires_sandbox=requires_sandbox,
            duration_ms=0,
            input_json=input_json,
            output_json={},
            error_message=decision.reason,
            created_at=utc_now(),
        )
        self.session.add(tool_call)
        self.session.flush()
        payload = {
            "tool_call_id": tool_call.id,
            "tool_name": metadata.name,
            "allowed": False,
            "policy_id": decision.policy_id,
            "reason": decision.reason,
            "audit_level": decision.audit_level,
            "requires_sandbox": requires_sandbox,
        }
        self.event_store.append(
            task_id=task_id,
            agent_run_id=agent_run_id,
            event_type=EventType.POLICY_CHECKED,
            payload_json=payload,
        )
        self.event_store.append(
            task_id=task_id,
            agent_run_id=agent_run_id,
            event_type=EventType.POLICY_DENIED,
            payload_json=payload,
        )
        self.event_store.append(
            task_id=task_id,
            agent_run_id=agent_run_id,
            event_type=EventType.TOOL_DENIED_BY_POLICY,
            payload_json=payload,
        )
        self.session.flush()
        return ToolExecution(tool_call=tool_call, allowed=False, output={})

    def _execute_allowed(
        self,
        metadata: ToolMetadata,
        input_json: dict,
        sandbox: SandboxInstance | None,
    ) -> dict:
        filesystem = WorkspaceFileTool(self.workspace_root)
        if metadata.name == "read_file":
            result = filesystem.read_file(str(input_json["path"]))
            return {"content": result.content, "size_bytes": result.size_bytes}
        if metadata.name == "list_files":
            result = filesystem.list_files(
                root=str(input_json.get("root", ".")),
                glob=str(input_json.get("glob", "**/*")),
            )
            return {"files": result.files}
        if sandbox is None:
            raise ValueError("sandbox is required")

        if metadata.name == "run_tests":
            return self._run_shell_like(
                sandbox=sandbox,
                command=str(input_json.get("command", "pytest")),
                cwd=str(input_json.get("cwd", "/workspace")),
                timeout_seconds=int(input_json.get("timeout_seconds", metadata.timeout_seconds)),
            )
        if metadata.name == "run_shell":
            return self._run_shell_like(
                sandbox=sandbox,
                command=str(input_json["command"]),
                cwd=str(input_json.get("cwd", "/workspace")),
                timeout_seconds=int(input_json.get("timeout_seconds", metadata.timeout_seconds)),
            )
        if metadata.name == "git_command":
            args = input_json.get("args", [])
            command = "git " + " ".join(str(arg) for arg in args)
            return self._run_shell_like(
                sandbox=sandbox,
                command=command,
                cwd=str(input_json.get("cwd", "/workspace")),
                timeout_seconds=int(input_json.get("timeout_seconds", metadata.timeout_seconds)),
            )
        if metadata.name == "write_file":
            relative_path = str(input_json["path"])
            content = str(input_json.get("content", ""))
            script = (
                "from pathlib import Path\n"
                f"root = Path('/workspace/output').resolve()\n"
                f"target = (root / {relative_path!r}).resolve()\n"
                "target.parent.mkdir(parents=True, exist_ok=True)\n"
                "if root != target and root not in target.parents:\n"
                "    raise SystemExit('path escapes output scope')\n"
                f"content = {content!r}\n"
                "target.write_text(content, encoding='utf-8')\n"
                "print(len(content.encode('utf-8')))\n"
            )
            result = self._run_shell_like(
                sandbox=sandbox,
                command=f"python -c {quote(script)}",
                cwd="/workspace",
                timeout_seconds=int(input_json.get("timeout_seconds", metadata.timeout_seconds)),
            )
            return {
                "path": relative_path,
                "bytes_written": int(result["stdout_preview"].strip() or "0"),
                **result,
            }
        if metadata.name == "network_request":
            script = (
                "import json, urllib.request\n"
                f"method = {str(input_json.get('method', 'GET')).upper()!r}\n"
                f"url = {str(input_json['url'])!r}\n"
                f"headers = {dict(input_json.get('headers', {}))!r}\n"
                f"body = {input_json.get('body')!r}\n"
                "data = None if body is None else json.dumps(body).encode('utf-8')\n"
                "request = urllib.request.Request(url, data=data, headers=headers, method=method)\n"
                "with urllib.request.urlopen(request, timeout=20) as response:\n"
                "    preview = response.read(2000).decode('utf-8', errors='replace')\n"
                "    print(json.dumps({'status_code': response.status, 'body_preview': preview}))\n"
            )
            result = self._run_shell_like(
                sandbox=sandbox,
                command=f"python -c {quote(script)}",
                cwd="/workspace",
                timeout_seconds=int(input_json.get("timeout_seconds", metadata.timeout_seconds)),
            )
            try:
                parsed = json.loads(result["stdout_preview"])
            except json.JSONDecodeError:
                return result
            return {**parsed, "duration_ms": result["duration_ms"]}
        raise ValueError(f"tool implementation is not wired: {metadata.name}")

    def _run_shell_like(
        self,
        *,
        sandbox: SandboxInstance,
        command: str,
        cwd: str,
        timeout_seconds: int,
    ) -> dict:
        result = self.shell_tool.run(
            session=self.session,
            sandbox=sandbox,
            request=ShellToolRequest(
                command=command,
                cwd=cwd,
                timeout_seconds=timeout_seconds,
            ),
        )
        return {
            "exit_code": result.exit_code,
            "stdout_preview": result.stdout[:2000],
            "stderr_preview": result.stderr[:2000],
            "duration_ms": result.duration_ms,
        }
