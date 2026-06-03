from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from shlex import quote

from sqlalchemy.orm import Session

from app.db.models import CapabilityVersion, SandboxInstance, Task, ToolApproval, ToolCall, utc_now
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.knowledge_dify import resolve_connector_secret_ref
from app.observability.tracing import traced_operation
from app.sandbox.docker_manager import SandboxCommandTimeoutError
from app.sandbox.policies import PolicyEngine, SandboxPolicyDecision
from app.security.secrets import SECRET_PURPOSE_MCP_RUNTIME
from app.tools.adapter_registry import REGISTRY, adapter_snapshot
from app.tools.adapters import ensure_builtin_adapters_registered
from app.tools.capabilities import (
    CapabilityRegistry,
    CapabilityResolutionError,
    ResolvedCapabilityTool,
    redact_secrets,
)
from app.tools.filesystem import WorkspaceFileTool
from app.tools.idempotency import get_idempotent_result, remember_idempotent_result
from app.tools.mcp_adapter import MCPAdapter
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
        agent_id: str | None = None,
        capability_registry: CapabilityRegistry | None = None,
        shell_tool: ShellTool | None = None,
        mcp_adapter: MCPAdapter | None = None,
    ) -> None:
        self.session = session
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.registry = registry or ToolRegistry.default()
        self.agent_id = agent_id
        self.capability_registry = capability_registry
        self.shell_tool = shell_tool or ShellTool()
        self.mcp_adapter = mcp_adapter or MCPAdapter()
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
        task = self.session.get(Task, task_id)
        try:
            resolved = self._resolve_tool(
                tool_name=tool_name,
                task_id=task_id,
                organization_id=task.organization_id if task is not None else None,
                source="tool_execute",
            )
        except PermissionError as exc:
            organization_id = task.organization_id if task is not None else None
            capability_registry = self.capability_registry or CapabilityRegistry(
                self.session,
                organization_id=organization_id,
            )
            metadata = capability_registry.metadata_for_tool_name(tool_name) or self._metadata(
                tool_name
            )
            return self._deny(
                task_id=task_id,
                agent_run_id=agent_run_id,
                metadata=metadata,
                input_json=redact_secrets(input_json),
                decision=SandboxPolicyDecision(
                    allowed=False,
                    reason=str(exc),
                    policy_id="capability-attachment-required",
                    audit_level=metadata.audit_level,
                    requires_sandbox=metadata.requires_sandbox,
                ),
                requires_sandbox=metadata.requires_sandbox,
            )
        metadata = resolved.metadata if resolved is not None else self._metadata(tool_name)
        capability_snapshot_json = self._capability_snapshot_json(
            resolved=resolved,
            metadata=metadata,
        )
        stored_input_json = redact_secrets(input_json)
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
            if decision.policy_id == "tool-approval-required":
                idempotency_decision = self._check_required_idempotency_key(metadata, input_json)
                if not idempotency_decision.allowed:
                    return self._deny(
                        task_id=task_id,
                        agent_run_id=agent_run_id,
                        metadata=metadata,
                        input_json=stored_input_json,
                        decision=idempotency_decision,
                        requires_sandbox=requires_sandbox,
                        resolved=resolved,
                    )
                return self._request_approval(
                    task_id=task_id,
                    agent_run_id=agent_run_id,
                    metadata=metadata,
                    input_json=stored_input_json,
                    decision=decision,
                    requires_sandbox=requires_sandbox,
                    resolved=resolved,
                )
            return self._deny(
                task_id=task_id,
                agent_run_id=agent_run_id,
                metadata=metadata,
                input_json=stored_input_json,
                decision=decision,
                requires_sandbox=requires_sandbox,
                resolved=resolved,
            )
        idempotency_decision = self._check_required_idempotency_key(metadata, input_json)
        if not idempotency_decision.allowed:
            return self._deny(
                task_id=task_id,
                agent_run_id=agent_run_id,
                metadata=metadata,
                input_json=stored_input_json,
                decision=idempotency_decision,
                requires_sandbox=requires_sandbox,
                resolved=resolved,
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
                    input_json=stored_input_json,
                    decision=network_decision,
                    requires_sandbox=requires_sandbox,
                    resolved=resolved,
                )

        started_at = time.monotonic()
        tool_call = ToolCall(
            task_id=task_id,
            agent_run_id=agent_run_id,
            tool_name=metadata.name,
            status="RUNNING",
            risk_level=metadata.risk_level,
            capability_id=resolved.capability.id if resolved is not None else None,
            capability_version_id=resolved.version.id if resolved is not None else None,
            capability_type=resolved.version.type if resolved is not None else None,
            capability_content_sha256=resolved.version.content_sha256
            if resolved is not None
            else None,
            capability_config_sha256=resolved.version.config_sha256
            if resolved is not None
            else None,
            capability_schema_version=resolved.version.schema_version
            if resolved is not None
            else None,
            capability_snapshot_json=capability_snapshot_json,
            requires_sandbox=requires_sandbox,
            sandbox_id=sandbox.id if sandbox is not None else None,
            duration_ms=0,
            input_json=stored_input_json,
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

        cached_output = self._cached_idempotent_output(
            organization_id=task.organization_id if task is not None else None,
            metadata=metadata,
            input_json=input_json,
        )
        if cached_output is not None:
            tool_call.status = "SUCCESS"
            tool_call.duration_ms = int((time.monotonic() - started_at) * 1000)
            stored_output = redact_secrets(cached_output)
            tool_call.output_json = stored_output
            self.event_store.append(
                task_id=task_id,
                agent_run_id=agent_run_id,
                event_type=EventType.TOOL_RESULT_RECEIVED,
                payload_json={
                    "tool_call_id": tool_call.id,
                    "tool_name": metadata.name,
                    "status": tool_call.status,
                    "idempotent_replay": True,
                },
            )
            self.session.flush()
            return ToolExecution(tool_call=tool_call, allowed=True, output=stored_output)

        try:
            with traced_operation(
                self.session,
                "tool_call",
                task_id=task_id,
                agent_run_id=agent_run_id,
                kind="client" if metadata.name == "network_request" else "internal",
                attributes={
                    "tool_call_id": tool_call.id,
                    "tool_name": metadata.name,
                    "risk_level": metadata.risk_level,
                    "capability_version_id": tool_call.capability_version_id,
                },
            ):
                output = self._execute_allowed(
                    metadata,
                    input_json,
                    sandbox,
                    capability_config=resolved.version.config_json if resolved is not None else {},
                    organization_id=task.organization_id if task is not None else None,
                    user_id=task.created_by if task is not None else None,
                )
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
            self._remember_idempotent_output(
                organization_id=task.organization_id if task is not None else None,
                metadata=metadata,
                input_json=input_json,
                tool_call_id=tool_call.id,
                output=output,
            )

        tool_call.duration_ms = int((time.monotonic() - started_at) * 1000)
        stored_output = redact_secrets(output)
        tool_call.output_json = stored_output
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
            output=stored_output,
        )

    def request_approval(
        self,
        *,
        task_id: str,
        tool_name: str,
        input_json: dict,
        agent_run_id: str | None = None,
        reason: str | None = None,
    ) -> ToolExecution:
        task = self.session.get(Task, task_id)
        try:
            resolved = self._resolve_tool(
                tool_name=tool_name,
                task_id=task_id,
                organization_id=task.organization_id if task is not None else None,
                source="tool_approval",
            )
        except PermissionError as exc:
            metadata = self._metadata(tool_name)
            return self._deny(
                task_id=task_id,
                agent_run_id=agent_run_id,
                metadata=metadata,
                input_json=redact_secrets(input_json),
                decision=SandboxPolicyDecision(
                    allowed=False,
                    reason=str(exc),
                    policy_id="capability-attachment-required",
                    audit_level=metadata.audit_level,
                    requires_sandbox=metadata.requires_sandbox,
                ),
                requires_sandbox=metadata.requires_sandbox,
            )
        metadata = resolved.metadata if resolved is not None else self._metadata(tool_name)
        capability_snapshot_json = self._capability_snapshot_json(
            resolved=resolved,
            metadata=metadata,
        )
        idempotency_decision = self._check_required_idempotency_key(metadata, input_json)
        if not idempotency_decision.allowed:
            return self._deny(
                task_id=task_id,
                agent_run_id=agent_run_id,
                metadata=metadata,
                input_json=redact_secrets(input_json),
                decision=idempotency_decision,
                requires_sandbox=metadata.requires_sandbox,
                resolved=resolved,
                capability_snapshot_json=capability_snapshot_json,
            )
        decision = SandboxPolicyDecision(
            allowed=False,
            reason=reason or "workspace side-effect tool requires approval",
            policy_id="workspace-tool-approval-required",
            audit_level=metadata.audit_level,
            requires_sandbox=metadata.requires_sandbox,
        )
        return self._request_approval(
            task_id=task_id,
            agent_run_id=agent_run_id,
            metadata=metadata,
            input_json=redact_secrets(input_json),
            decision=decision,
            requires_sandbox=metadata.requires_sandbox,
            resolved=resolved,
            capability_snapshot_json=capability_snapshot_json,
        )

    def execute_approved_call(
        self,
        *,
        tool_call: ToolCall,
        sandbox: SandboxInstance | None = None,
    ) -> ToolExecution:
        metadata = self._metadata_for_existing_call(tool_call)
        input_json = tool_call.input_json if isinstance(tool_call.input_json, dict) else {}
        requires_sandbox = bool(tool_call.requires_sandbox or metadata.requires_sandbox)
        if metadata.name == "network_request":
            network_decision = self.policy_engine.evaluate_network_request(
                task_id=tool_call.task_id,
                url=str(input_json.get("url", "")),
            )
            if not network_decision.allowed:
                tool_call.status = "DENIED"
                tool_call.error_message = network_decision.reason
                tool_call.output_json = {}
                payload = {
                    "tool_call_id": tool_call.id,
                    "tool_name": metadata.name,
                    "allowed": False,
                    "policy_id": network_decision.policy_id,
                    "reason": network_decision.reason,
                    "audit_level": network_decision.audit_level,
                    "requires_sandbox": requires_sandbox,
                }
                self.event_store.append(
                    task_id=tool_call.task_id,
                    agent_run_id=tool_call.agent_run_id,
                    event_type=EventType.POLICY_DENIED,
                    payload_json=payload,
                )
                self.event_store.append(
                    task_id=tool_call.task_id,
                    agent_run_id=tool_call.agent_run_id,
                    event_type=EventType.TOOL_DENIED_BY_POLICY,
                    payload_json=payload,
                )
                self.session.flush()
                return ToolExecution(tool_call=tool_call, allowed=False, output={})

        started_at = time.monotonic()
        tool_call.status = "RUNNING"
        tool_call.error_message = None
        tool_call.sandbox_id = sandbox.id if sandbox is not None else tool_call.sandbox_id
        task = self.session.get(Task, tool_call.task_id)
        capability_config = self._capability_config_for_existing_call(tool_call)
        capability_snapshot_json = self._snapshot_for_existing_call(tool_call, metadata)
        tool_call.capability_snapshot_json = capability_snapshot_json
        idempotency_decision = self._check_required_idempotency_key(metadata, input_json)
        if not idempotency_decision.allowed:
            tool_call.status = "DENIED"
            tool_call.error_message = idempotency_decision.reason
            tool_call.output_json = {}
            payload = {
                "tool_call_id": tool_call.id,
                "tool_name": metadata.name,
                "allowed": False,
                "policy_id": idempotency_decision.policy_id,
                "reason": idempotency_decision.reason,
                "audit_level": idempotency_decision.audit_level,
                "requires_sandbox": requires_sandbox,
            }
            self.event_store.append(
                task_id=tool_call.task_id,
                agent_run_id=tool_call.agent_run_id,
                event_type=EventType.POLICY_CHECKED,
                payload_json=payload,
            )
            self.event_store.append(
                task_id=tool_call.task_id,
                agent_run_id=tool_call.agent_run_id,
                event_type=EventType.POLICY_DENIED,
                payload_json=payload,
            )
            self.event_store.append(
                task_id=tool_call.task_id,
                agent_run_id=tool_call.agent_run_id,
                event_type=EventType.TOOL_DENIED_BY_POLICY,
                payload_json=payload,
            )
            self.session.flush()
            return ToolExecution(tool_call=tool_call, allowed=False, output={})
        self.event_store.append(
            task_id=tool_call.task_id,
            agent_run_id=tool_call.agent_run_id,
            event_type=EventType.POLICY_CHECKED,
            payload_json={
                "tool_call_id": tool_call.id,
                "tool_name": metadata.name,
                "allowed": True,
                "policy_id": "tool-approval-approved",
                "reason": "approved tool call is allowed to proceed",
                "audit_level": metadata.audit_level,
                "requires_sandbox": requires_sandbox,
            },
        )
        self.event_store.append(
            task_id=tool_call.task_id,
            agent_run_id=tool_call.agent_run_id,
            event_type=EventType.TOOL_CALLED,
            payload_json={"tool_call_id": tool_call.id, "tool_name": metadata.name},
        )

        cached_output = self._cached_idempotent_output(
            organization_id=task.organization_id if task is not None else None,
            metadata=metadata,
            input_json=input_json,
        )
        if cached_output is not None:
            tool_call.status = "SUCCESS"
            tool_call.duration_ms = int((time.monotonic() - started_at) * 1000)
            stored_output = redact_secrets(cached_output)
            tool_call.output_json = stored_output
            self.event_store.append(
                task_id=tool_call.task_id,
                agent_run_id=tool_call.agent_run_id,
                event_type=EventType.TOOL_RESULT_RECEIVED,
                payload_json={
                    "tool_call_id": tool_call.id,
                    "tool_name": metadata.name,
                    "status": tool_call.status,
                    "idempotent_replay": True,
                },
            )
            self.session.flush()
            return ToolExecution(tool_call=tool_call, allowed=True, output=stored_output)
        try:
            output = self._execute_allowed(
                metadata,
                input_json,
                sandbox,
                capability_config=capability_config,
                organization_id=task.organization_id if task is not None else None,
                user_id=task.created_by if task is not None else None,
            )
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
            self._remember_idempotent_output(
                organization_id=task.organization_id if task is not None else None,
                metadata=metadata,
                input_json=input_json,
                tool_call_id=tool_call.id,
                output=output,
            )

        tool_call.duration_ms = int((time.monotonic() - started_at) * 1000)
        stored_output = redact_secrets(output)
        tool_call.output_json = stored_output
        self.event_store.append(
            task_id=tool_call.task_id,
            agent_run_id=tool_call.agent_run_id,
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
            allowed=tool_call.status == "SUCCESS",
            output=stored_output,
        )

    def _resolve_tool(
        self,
        *,
        tool_name: str,
        task_id: str,
        organization_id: str | None,
        source: str,
    ) -> ResolvedCapabilityTool | None:
        if self.agent_id is None:
            if tool_name not in self.registry.tools:
                raise ValueError(f"unknown tool: {tool_name}")
            raise PermissionError("agent capability attachment is required for tool execution")
        registry = self.capability_registry or CapabilityRegistry(
            self.session,
            organization_id=organization_id,
        )
        try:
            return registry.resolve_tool(
                agent_id=self.agent_id,
                tool_name=tool_name,
                task_id=task_id,
                source=source,
            )
        except CapabilityResolutionError as exc:
            metadata = registry.metadata_for_tool_name(tool_name) or self.registry.tools.get(
                tool_name
            )
            if metadata is None:
                raise ValueError(f"unknown tool: {tool_name}") from exc
            raise PermissionError(str(exc)) from exc

    def _metadata(self, tool_name: str) -> ToolMetadata:
        metadata = self.registry.tools.get(tool_name)
        if metadata is None:
            raise ValueError(f"unknown tool: {tool_name}")
        return metadata

    def _metadata_for_existing_call(self, tool_call: ToolCall) -> ToolMetadata:
        if tool_call.capability_version_id:
            version = self.session.get(CapabilityVersion, tool_call.capability_version_id)
            if version is not None:
                raw = version.content_json.get("tool_metadata")
                if isinstance(raw, dict):
                    return ToolMetadata.model_validate(raw)
        return self._metadata(tool_call.tool_name)

    def _capability_config_for_existing_call(self, tool_call: ToolCall) -> dict:
        if tool_call.capability_version_id:
            version = self.session.get(CapabilityVersion, tool_call.capability_version_id)
            if version is not None and isinstance(version.config_json, dict):
                return version.config_json
        return {}

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

    def _check_required_idempotency_key(
        self,
        metadata: ToolMetadata,
        input_json: dict,
    ) -> SandboxPolicyDecision:
        if metadata.idempotent or metadata.source != "mcp":
            return SandboxPolicyDecision(
                allowed=True,
                reason="idempotency key is not required",
                policy_id="tool-idempotency-key-not-required",
                audit_level=metadata.audit_level,
                requires_sandbox=metadata.requires_sandbox,
            )
        if str(input_json.get("idempotency_key") or "").strip():
            return SandboxPolicyDecision(
                allowed=True,
                reason="idempotency key accepted",
                policy_id="tool-idempotency-key-required",
                audit_level=metadata.audit_level,
                requires_sandbox=metadata.requires_sandbox,
            )
        return SandboxPolicyDecision(
            allowed=False,
            reason="non-idempotent MCP tool requires idempotency_key",
            policy_id="tool-idempotency-key-required",
            audit_level=metadata.audit_level,
            requires_sandbox=metadata.requires_sandbox,
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
        resolved: ResolvedCapabilityTool | None = None,
        capability_snapshot_json: dict | None = None,
    ) -> ToolExecution:
        snapshot_json = (
            capability_snapshot_json
            if isinstance(capability_snapshot_json, dict)
            else self._capability_snapshot_json(resolved=resolved, metadata=metadata)
        )
        tool_call = ToolCall(
            task_id=task_id,
            agent_run_id=agent_run_id,
            tool_name=metadata.name,
            status="DENIED",
            risk_level=metadata.risk_level,
            capability_id=resolved.capability.id if resolved is not None else None,
            capability_version_id=resolved.version.id if resolved is not None else None,
            capability_type=resolved.version.type if resolved is not None else None,
            capability_content_sha256=resolved.version.content_sha256
            if resolved is not None
            else None,
            capability_config_sha256=resolved.version.config_sha256
            if resolved is not None
            else None,
            capability_schema_version=resolved.version.schema_version
            if resolved is not None
            else None,
            capability_snapshot_json=snapshot_json,
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

    def _request_approval(
        self,
        *,
        task_id: str,
        agent_run_id: str | None,
        metadata: ToolMetadata,
        input_json: dict,
        decision: SandboxPolicyDecision,
        requires_sandbox: bool,
        resolved: ResolvedCapabilityTool | None = None,
        capability_snapshot_json: dict | None = None,
    ) -> ToolExecution:
        snapshot_json = (
            capability_snapshot_json
            if isinstance(capability_snapshot_json, dict)
            else self._capability_snapshot_json(resolved=resolved, metadata=metadata)
        )
        task = self.session.get(Task, task_id)
        tool_call = ToolCall(
            task_id=task_id,
            agent_run_id=agent_run_id,
            tool_name=metadata.name,
            status="PENDING_APPROVAL",
            risk_level=metadata.risk_level,
            capability_id=resolved.capability.id if resolved is not None else None,
            capability_version_id=resolved.version.id if resolved is not None else None,
            capability_type=resolved.version.type if resolved is not None else None,
            capability_content_sha256=resolved.version.content_sha256
            if resolved is not None
            else None,
            capability_config_sha256=resolved.version.config_sha256
            if resolved is not None
            else None,
            capability_schema_version=resolved.version.schema_version
            if resolved is not None
            else None,
            capability_snapshot_json=snapshot_json,
            requires_sandbox=requires_sandbox,
            duration_ms=0,
            input_json=input_json,
            output_json={},
            error_message=decision.reason,
            created_at=utc_now(),
        )
        self.session.add(tool_call)
        self.session.flush()
        approval = ToolApproval(
            task_id=task_id,
            tool_call_id=tool_call.id,
            organization_id=task.organization_id if task is not None else None,
            requested_by=None,
            status="PENDING",
            risk_level=metadata.risk_level,
            reason=decision.reason,
            request_json={
                "tool_name": metadata.name,
                "input_json": input_json,
                "requires_sandbox": requires_sandbox,
                "policy_id": decision.policy_id,
                "audit_level": decision.audit_level,
            },
            decision_json={},
            created_at=utc_now(),
        )
        self.session.add(approval)
        self.session.flush()
        payload = {
            "tool_call_id": tool_call.id,
            "tool_approval_id": approval.id,
            "tool_name": metadata.name,
            "allowed": False,
            "requires_approval": True,
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
            event_type=EventType.TOOL_APPROVAL_REQUESTED,
            payload_json=payload,
        )
        self.session.flush()
        return ToolExecution(
            tool_call=tool_call,
            allowed=False,
            output={"approval_id": approval.id, "status": approval.status},
        )

    def _execute_allowed(
        self,
        metadata: ToolMetadata,
        input_json: dict,
        sandbox: SandboxInstance | None,
        *,
        capability_config: dict | None = None,
        organization_id: str | None = None,
        user_id: str | None = None,
    ) -> dict:
        filesystem = WorkspaceFileTool(self.workspace_root)
        if metadata.source == "mcp":
            config = capability_config if isinstance(capability_config, dict) else {}
            secret_ref = str(config.get("secret_ref") or "").strip()
            secret_value = (
                resolve_connector_secret_ref(
                    secret_ref,
                    provider=metadata.name,
                    session=self.session,
                    organization_id=organization_id,
                    user_id=user_id,
                    purpose=SECRET_PURPOSE_MCP_RUNTIME,
                )
                if secret_ref
                else ""
            )
            result = self.mcp_adapter.execute(
                metadata=metadata,
                input_json=input_json,
                config_json=config,
                secret_value=secret_value,
                sandbox_workspace_root=self.workspace_root if sandbox is not None else None,
                sandbox_command_executor=(
                    (
                        lambda command, cwd, timeout_seconds: self.shell_tool.run(
                            session=self.session,
                            sandbox=sandbox,
                            request=ShellToolRequest(
                                command=command,
                                cwd=cwd,
                                timeout_seconds=timeout_seconds,
                            ),
                        )
                    )
                    if sandbox is not None
                    else None
                ),
            )
            return {
                "mcp_server": result.server,
                "mcp_method": result.method,
                "result": result.output_json,
            }
        if metadata.name not in self.registry.tools:
            return {
                "package_tool": metadata.name,
                "status": "validated_noop",
                "input_echo": redact_secrets(input_json),
            }
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

    def _capability_snapshot_json(
        self,
        *,
        resolved: ResolvedCapabilityTool | None,
        metadata: ToolMetadata,
    ) -> dict:
        snapshot = dict(resolved.snapshot_json) if resolved is not None else {}
        ensure_builtin_adapters_registered(REGISTRY)
        adapter = REGISTRY.get(metadata.name)
        if adapter is not None:
            snapshot = {
                **snapshot,
                "adapter": adapter_snapshot(adapter),
            }
        return snapshot

    def _snapshot_for_existing_call(self, tool_call: ToolCall, metadata: ToolMetadata) -> dict:
        snapshot = tool_call.capability_snapshot_json
        if not isinstance(snapshot, dict):
            snapshot = {}
        ensure_builtin_adapters_registered(REGISTRY)
        adapter = REGISTRY.get(metadata.name)
        if adapter is not None:
            snapshot = {**snapshot, "adapter": adapter_snapshot(adapter)}
        return snapshot

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

    def _cached_idempotent_output(
        self,
        *,
        organization_id: str | None,
        metadata: ToolMetadata,
        input_json: dict,
    ) -> dict | None:
        if metadata.idempotent:
            return None
        key = str(input_json.get("idempotency_key") or "").strip()
        if not key:
            return None
        return get_idempotent_result(
            self.session,
            organization_id=organization_id,
            tool_name=metadata.name,
            idempotency_key=key,
        )

    def _remember_idempotent_output(
        self,
        *,
        organization_id: str | None,
        metadata: ToolMetadata,
        input_json: dict,
        tool_call_id: str,
        output: dict,
    ) -> None:
        if metadata.idempotent or output.get("error"):
            return
        key = str(input_json.get("idempotency_key") or "").strip()
        if not key:
            return
        remember_idempotent_result(
            self.session,
            organization_id=organization_id,
            tool_name=metadata.name,
            idempotency_key=key,
            tool_call_id=tool_call_id,
            output_json=redact_secrets(output),
        )
