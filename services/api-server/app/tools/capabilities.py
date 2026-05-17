from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import event, or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    Agent,
    AgentCapabilityAttachment,
    Capability,
    CapabilitySnapshot,
    CapabilityVersion,
    utc_now,
)
from app.tools.registry import ToolMetadata, ToolRegistry

CAPABILITY_SCHEMA_VERSION = 1
CAPABILITY_TYPE_BUILTIN_TOOL = "builtin_tool"
CAPABILITY_TYPE_MCP_TOOL = "mcp_tool"
CAPABILITY_TYPE_SKILL = "skill"

SECRET_KEY_PARTS = ("token", "password", "credential", "authorization", "api_key", "apikey")
SECRET_KEY_ALLOWLIST = {"secret_ref", "secret_scope"}


class CapabilityResolutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResolvedCapabilityTool:
    metadata: ToolMetadata
    capability: Capability
    version: CapabilityVersion
    snapshot_json: dict


def stable_json_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            normalized = key_text.lower().replace("-", "_")
            if normalized not in SECRET_KEY_ALLOWLIST and any(
                part in normalized for part in SECRET_KEY_PARTS
            ):
                redacted[key_text] = "[REDACTED]"
            else:
                redacted[key_text] = redact_secrets(item)
        return redacted
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return value


def tool_capability_key(tool_name: str) -> str:
    return f"tool:{tool_name}"


def _capability_type_for_tool(metadata: ToolMetadata) -> str:
    return CAPABILITY_TYPE_MCP_TOOL if metadata.source == "mcp" else CAPABILITY_TYPE_BUILTIN_TOOL


class CapabilityRegistry:
    def __init__(self, session: Session, organization_id: str | None) -> None:
        self.session = session
        self.organization_id = organization_id

    def ensure_builtin_capabilities(self) -> dict[str, CapabilityVersion]:
        versions: dict[str, CapabilityVersion] = {}
        for metadata in ToolRegistry.default().list_tools():
            capability = self._get_or_create_tool_capability(metadata)
            version = self._get_or_create_tool_version(capability, metadata)
            if capability.current_version_id != version.id:
                capability.current_version_id = version.id
                capability.updated_at = utc_now()
            versions[metadata.name] = version
        self.session.flush()
        return versions

    def backfill_agent_attachments(self, agent_id: str, *, attached_by: str | None = None) -> None:
        """One-way legacy migration helper.

        Runtime resolution must not call this method. It is reserved for migration, seed,
        and test setup surfaces that deliberately convert legacy Agent.tools_json into
        persisted AgentCapabilityAttachment rows.
        """
        agent = self._agent(agent_id)
        existing_count = self.session.execute(
            select(AgentCapabilityAttachment.id).where(
                AgentCapabilityAttachment.agent_id == agent.id,
            )
        ).first()
        if existing_count is not None:
            return
        versions = self.ensure_builtin_capabilities()
        now = utc_now()
        for index, tool_name in enumerate(agent.tools_json):
            version = versions.get(str(tool_name))
            if version is None:
                continue
            self.session.add(
                AgentCapabilityAttachment(
                    organization_id=agent.organization_id,
                    agent_id=agent.id,
                    capability_id=version.capability_id,
                    capability_version_id=version.id,
                    enabled=True,
                    priority=index,
                    attached_by=attached_by,
                    attached_at=now,
                )
            )
        self.session.flush()

    def resolve_tool(
        self,
        *,
        agent_id: str,
        tool_name: str,
        task_id: str | None = None,
        source: str = "runtime",
    ) -> ResolvedCapabilityTool:
        self._agent(agent_id)
        rows = list(
            self.session.execute(
                select(AgentCapabilityAttachment, Capability, CapabilityVersion)
                .join(Capability, AgentCapabilityAttachment.capability_id == Capability.id)
                .join(
                    CapabilityVersion,
                    AgentCapabilityAttachment.capability_version_id == CapabilityVersion.id,
                )
                .where(
                    AgentCapabilityAttachment.agent_id == agent_id,
                    AgentCapabilityAttachment.enabled.is_(True),
                    Capability.status == "active",
                    CapabilityVersion.status == "active",
                )
                .order_by(
                    AgentCapabilityAttachment.priority.asc(),
                    AgentCapabilityAttachment.attached_at.asc(),
                )
            ).all()
        )
        for _attachment, capability, version in rows:
            metadata = self._metadata_from_version(version)
            if metadata.name == tool_name:
                snapshot = self.create_snapshot(
                    agent_id=agent_id,
                    task_id=task_id,
                    source=source,
                    versions=[version],
                )
                return ResolvedCapabilityTool(
                    metadata=metadata,
                    capability=capability,
                    version=version,
                    snapshot_json=snapshot,
                )
        raise CapabilityResolutionError(
            f"agent {agent_id} is not attached to capability {tool_name}"
        )

    def tool_registry_for_agent(self, agent_id: str) -> tuple[ToolRegistry, dict]:
        self._agent(agent_id)
        versions = self._attached_versions(agent_id)
        tools: dict[str, ToolMetadata] = {}
        for version in versions:
            metadata = self._metadata_from_version(version)
            tools[metadata.name] = metadata
        snapshot = self.create_snapshot(
            agent_id=agent_id,
            task_id=None,
            source="registry_listing",
            versions=versions,
            persist=False,
        )
        return ToolRegistry(tools=tools), snapshot

    def create_snapshot(
        self,
        *,
        agent_id: str | None,
        task_id: str | None,
        source: str,
        versions: list[CapabilityVersion],
        persist: bool = True,
    ) -> dict:
        ordered_versions = sorted(versions, key=lambda item: item.id)
        entries = [
            {
                "capability_version_id": version.id,
                "capability_id": version.capability_id,
                "capability_type": version.type,
                "content_sha256": version.content_sha256,
                "config_sha256": version.config_sha256,
                "schema_version": version.schema_version,
            }
            for version in ordered_versions
        ]
        snapshot = {
            "capability_snapshot_id": None,
            "agent_id": agent_id,
            "schema_version": CAPABILITY_SCHEMA_VERSION,
            "capability_version_ids": [entry["capability_version_id"] for entry in entries],
            "content_sha256_values": [entry["content_sha256"] for entry in entries],
            "config_sha256_values": [entry["config_sha256"] for entry in entries],
            "capabilities": entries,
        }
        if not persist:
            return snapshot
        row = CapabilitySnapshot(
            organization_id=self.organization_id,
            agent_id=agent_id,
            task_id=task_id,
            source=source,
            schema_version=CAPABILITY_SCHEMA_VERSION,
            snapshot_json=snapshot,
            snapshot_sha256=stable_json_sha256(snapshot),
            created_at=utc_now(),
        )
        self.session.add(row)
        self.session.flush()
        snapshot = {**snapshot, "capability_snapshot_id": row.id}
        row.snapshot_json = snapshot
        row.snapshot_sha256 = stable_json_sha256(snapshot)
        self.session.flush()
        return snapshot

    def admin_validate_capability(self, payload: dict) -> dict:
        redacted = redact_secrets(payload)
        return {
            "status": "valid",
            "schema_version": CAPABILITY_SCHEMA_VERSION,
            "content_sha256": stable_json_sha256(redacted.get("content", {})),
            "config_sha256": stable_json_sha256(redacted.get("config", {})),
            "redacted_payload": redacted,
        }

    def _attached_versions(self, agent_id: str) -> list[CapabilityVersion]:
        return list(
            self.session.execute(
                select(CapabilityVersion)
                .join(
                    AgentCapabilityAttachment,
                    AgentCapabilityAttachment.capability_version_id == CapabilityVersion.id,
                )
                .join(Capability, AgentCapabilityAttachment.capability_id == Capability.id)
                .where(
                    AgentCapabilityAttachment.agent_id == agent_id,
                    AgentCapabilityAttachment.enabled.is_(True),
                    Capability.status == "active",
                    CapabilityVersion.status == "active",
                )
                .order_by(
                    AgentCapabilityAttachment.priority.asc(),
                    AgentCapabilityAttachment.attached_at.asc(),
                )
            ).scalars()
        )

    def _agent(self, agent_id: str) -> Agent:
        agent = self.session.execute(
            select(Agent).where(
                Agent.id == agent_id,
                or_(
                    Agent.organization_id == self.organization_id,
                    Agent.organization_id.is_(None),
                ),
            )
        ).scalar_one_or_none()
        if agent is None:
            raise CapabilityResolutionError(f"agent not found: {agent_id}")
        return agent

    def _get_or_create_tool_capability(self, metadata: ToolMetadata) -> Capability:
        key = tool_capability_key(metadata.name)
        capability = self.session.execute(
            select(Capability).where(
                Capability.organization_id.is_(None),
                Capability.capability_key == key,
            )
        ).scalar_one_or_none()
        if capability is not None:
            return capability
        capability = Capability(
            organization_id=None,
            capability_key=key,
            type=_capability_type_for_tool(metadata),
            status="active",
            schema_version=CAPABILITY_SCHEMA_VERSION,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self.session.add(capability)
        self.session.flush()
        return capability

    def _get_or_create_tool_version(
        self,
        capability: Capability,
        metadata: ToolMetadata,
    ) -> CapabilityVersion:
        content = {"tool_metadata": metadata.model_dump()}
        config = {
            "secret_ref": None,
            "secret_scope": None,
            "source": metadata.source,
        }
        content_sha = stable_json_sha256(content)
        config_sha = stable_json_sha256(config)
        version_id = f"{metadata.name}:{content_sha[:16]}:{config_sha[:8]}"
        version = self.session.get(CapabilityVersion, version_id)
        if version is not None:
            return version
        version = CapabilityVersion(
            id=version_id,
            capability_id=capability.id,
            version=1,
            type=capability.type,
            status="active",
            content_json=content,
            config_json=config,
            content_sha256=content_sha,
            config_sha256=config_sha,
            schema_version=CAPABILITY_SCHEMA_VERSION,
            created_at=utc_now(),
        )
        self.session.add(version)
        self.session.flush()
        return version

    def _metadata_from_version(self, version: CapabilityVersion) -> ToolMetadata:
        raw = version.content_json.get("tool_metadata")
        if not isinstance(raw, dict):
            raise CapabilityResolutionError(f"capability version is not executable: {version.id}")
        return ToolMetadata.model_validate(raw)


@event.listens_for(CapabilityVersion, "before_update")
def _reject_capability_version_update(*_args: object) -> None:
    raise ValueError("capability_versions are immutable")


@event.listens_for(CapabilityVersion, "before_delete")
def _reject_capability_version_delete(*_args: object) -> None:
    raise ValueError("capability_versions are immutable")
