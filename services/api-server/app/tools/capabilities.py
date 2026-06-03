from __future__ import annotations

import hashlib
import ipaddress
import json
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from jsonschema import Draft202012Validator
from sqlalchemy import event, or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    Agent,
    AgentCapabilityAttachment,
    Capability,
    CapabilityPackage,
    CapabilitySnapshot,
    CapabilityVersion,
    utc_now,
)
from app.tools.registry import ToolMetadata, ToolRegistry

CAPABILITY_SCHEMA_VERSION = 1
CAPABILITY_TYPE_BUILTIN_TOOL = "builtin_tool"
CAPABILITY_TYPE_MCP_TOOL = "mcp_tool"
CAPABILITY_TYPE_SKILL = "skill"
CAPABILITY_TYPE_KNOWLEDGE_CONNECTOR = "knowledge_connector"
CAPABILITY_TYPE_CONTEXT_OPTIMIZER = "context_optimizer"
EXECUTABLE_CAPABILITY_TYPES = {CAPABILITY_TYPE_BUILTIN_TOOL, CAPABILITY_TYPE_MCP_TOOL}

SECRET_KEY_PARTS = ("token", "password", "credential", "authorization", "api_key", "apikey")
SECRET_KEY_ALLOWLIST = {"secret_ref", "secret_scope", "max_candidate_tokens_ratio"}

PUBLIC_SOURCE_TYPES = {"public_url", "public_git", "git", "url"}
PUBLIC_SOURCE_KINDS = {"public_url", "public_git"}
TRUSTED_SOURCE_KINDS = {"trusted_url", "trusted_git"}
ALLOWED_PACKAGE_TYPES = {
    "agent_template",
    "skill_pack",
    "tool_definition",
    "mcp_server",
    "prompt_template",
    "knowledge_connector",
    "context_optimizer",
}
PACKAGE_TYPES = ALLOWED_PACKAGE_TYPES
PACKAGE_MANIFEST_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["name", "version", "description", "package_type", "permissions"],
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "version": {"type": "string", "minLength": 1},
        "description": {"type": "string", "minLength": 1},
        "package_type": {"enum": sorted(ALLOWED_PACKAGE_TYPES)},
        "permissions": {
            "type": "array",
            "items": {"type": "string"},
        },
        "secret_refs": {
            "type": "array",
            "items": {
                "anyOf": [
                    {"type": "string", "minLength": 1},
                    {
                        "type": "object",
                        "properties": {
                            "secret_ref": {"type": "string", "minLength": 1},
                            "ref": {"type": "string", "minLength": 1},
                        },
                    },
                ]
            },
        },
        "tool_metadata": {"type": "object"},
        "transport": {"enum": ["stdio", "http", "sse"]},
        "auth_required": {"type": "boolean"},
        "optimizer": {"type": "object"},
    },
    "additionalProperties": True,
}
PACKAGE_MANIFEST_VALIDATOR = Draft202012Validator(PACKAGE_MANIFEST_SCHEMA)
ALLOWED_PUBLIC_SCHEMES = {"git+https", "https"}
BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain", "metadata.google.internal"}
BLOCKED_HOSTS = BLOCKED_HOSTNAMES
MAX_PACKAGE_KEY_LENGTH = 128
MAX_CAPABILITY_KEY_LENGTH = 128
MAX_CAPABILITY_VERSION_ID_LENGTH = 64
MAX_REMOTE_PACKAGE_BYTES = 1_000_000
MAX_REMOTE_PACKAGE_REDIRECTS = 5


def _source_config(payload: dict) -> dict:
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    content = payload.get("content") if isinstance(payload.get("content"), dict) else {}
    source = config.get("source") if isinstance(config.get("source"), dict) else {}
    if isinstance(content.get("package_manifest"), dict):
        manifest = content["package_manifest"]
    elif isinstance(content.get("manifest"), dict):
        manifest = content["manifest"]
    else:
        manifest = content
    return {
        "source_type": (
            config.get("source_type")
            or source.get("type")
            or manifest.get("source_type")
        ),
        "source_url": config.get("source_url") or source.get("url") or manifest.get("source_url"),
        "package_type": (
            config.get("package_type")
            or manifest.get("package_type")
            or manifest.get("type")
        ),
        "permissions": config.get("permissions") or manifest.get("permissions"),
        "secret_refs": config.get("secret_refs") or manifest.get("secret_refs") or [],
        "provenance": config.get("provenance") or manifest.get("provenance") or {},
        "digest": config.get("digest") or source.get("digest") or manifest.get("digest"),
        "commit": config.get("commit") or source.get("commit") or manifest.get("commit"),
        "manifest": manifest,
    }


def _is_public_source(source_type: Any) -> bool:
    return str(source_type or "").strip().lower() in PUBLIC_SOURCE_TYPES


def _is_private_or_reserved_host(hostname: str) -> bool:
    normalized = hostname.strip().strip("[]").lower().rstrip(".")
    if normalized in BLOCKED_HOSTNAMES or normalized.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    )


def _resolved_public_host_errors(hostname: str) -> list[str]:
    errors: list[str] = []
    try:
        records = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        return [f"public package source host could not be resolved: {exc}"]
    checked_addresses: set[str] = set()
    for record in records:
        sockaddr = record[4]
        if not sockaddr:
            continue
        address_text = str(sockaddr[0])
        if address_text in checked_addresses:
            continue
        checked_addresses.add(address_text)
        if _is_private_or_reserved_host(address_text):
            errors.append(
                "public package source resolver returned private, loopback, link-local, "
                "or metadata address"
            )
            break
    return errors


def _validate_public_source_url(source_url: Any) -> list[str]:
    if not isinstance(source_url, str) or not source_url.strip():
        return ["public package source_url is required"]
    parsed = urlparse(source_url)
    errors: list[str] = []
    if parsed.scheme.lower() not in ALLOWED_PUBLIC_SCHEMES:
        errors.append("public package source_url must use https or git+https")
    if parsed.username or parsed.password:
        errors.append("public package source_url must not contain credentials")
    if not parsed.hostname:
        errors.append("public package source_url host is required")
    elif _is_private_or_reserved_host(parsed.hostname):
        errors.append(
            "public package source_url must not target private, loopback, link-local, "
            "or metadata hosts"
        )
    else:
        errors.extend(_resolved_public_host_errors(parsed.hostname))
    return errors


def validate_trusted_source(source_uri: str) -> dict:
    errors = _validate_public_source_url(source_uri)
    return {"status": "invalid" if errors else "valid", "errors": errors}


@dataclass(frozen=True)
class DownloadedPackageContent:
    content: dict
    pinned_ref: str
    metadata: dict


def download_remote_package_content(source_uri: str) -> DownloadedPackageContent:
    source_errors = _validate_public_source_url(source_uri)
    if source_errors:
        raise CapabilityResolutionError("; ".join(source_errors))
    parsed = urlparse(source_uri)
    if parsed.scheme.lower() != "https":
        raise CapabilityResolutionError(
            "URL package download currently supports https package files; git+https sources "
            "must provide pinned_ref and package content metadata"
        )

    current_url = source_uri
    original_host = (parsed.hostname or "").lower().rstrip(".")
    redirects: list[dict[str, str]] = []
    headers = {"Accept": "application/json,text/markdown,text/plain,*/*"}

    try:
        with httpx.Client(
            timeout=10.0,
            follow_redirects=False,
            max_redirects=MAX_REMOTE_PACKAGE_REDIRECTS,
        ) as client:
            for _attempt in range(MAX_REMOTE_PACKAGE_REDIRECTS + 1):
                current_errors = _validate_public_source_url(current_url)
                if current_errors:
                    raise CapabilityResolutionError("; ".join(current_errors))
                response = client.get(current_url, headers=headers)
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise CapabilityResolutionError(
                            "remote package redirect did not include a Location header"
                        )
                    next_url = urljoin(current_url, location)
                    next_host = (urlparse(next_url).hostname or "").lower().rstrip(".")
                    if next_host != original_host:
                        raise CapabilityResolutionError(
                            "remote package redirect across hosts is not allowed"
                        )
                    redirects.append({"from": current_url, "to": next_url})
                    current_url = next_url
                    continue
                response.raise_for_status()
                raw = response.content
                if len(raw) > MAX_REMOTE_PACKAGE_BYTES:
                    raise CapabilityResolutionError(
                        f"remote package is larger than {MAX_REMOTE_PACKAGE_BYTES} bytes"
                    )
                content_sha = hashlib.sha256(raw).hexdigest()
                body = raw.decode("utf-8", errors="replace")
                parsed_json = _try_parse_package_json(body)
                content = {
                    "download": {
                        "source_uri": source_uri,
                        "final_url": current_url,
                        "content_type": response.headers.get("content-type", ""),
                        "size_bytes": len(raw),
                        "sha256": content_sha,
                        "redirects": redirects,
                    },
                    "body": body,
                }
                if parsed_json is not None:
                    content["json"] = parsed_json
                metadata = {
                    "source_uri": source_uri,
                    "final_url": current_url,
                    "sha256": content_sha,
                    "size_bytes": len(raw),
                    "content_type": response.headers.get("content-type", ""),
                    "redirect_count": len(redirects),
                    "redirects": redirects,
                    "fetch_client": "httpx",
                    "no_code_execution": True,
                }
                return DownloadedPackageContent(
                    content=content,
                    pinned_ref=f"sha256:{content_sha}",
                    metadata=metadata,
                )
    except httpx.HTTPStatusError as exc:
        raise CapabilityResolutionError(
            f"remote package download failed with HTTP {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        raise CapabilityResolutionError(f"remote package download failed: {exc}") from exc

    raise CapabilityResolutionError("remote package exceeded redirect limit")


def _try_parse_package_json(body: str) -> dict | list | None:
    try:
        value = json.loads(body)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, (dict, list)) else None


def _secret_refs_shape_errors(secret_refs: Any) -> list[str]:
    if secret_refs in (None, []):
        return []
    if not isinstance(secret_refs, list):
        return ["secret_refs must be a list of secret reference names"]
    errors: list[str] = []
    for index, item in enumerate(secret_refs):
        if isinstance(item, str):
            if not item.strip():
                errors.append(f"secret_refs[{index}] must not be empty")
            continue
        if isinstance(item, dict):
            ref = item.get("secret_ref") or item.get("ref")
            if not isinstance(ref, str) or not ref.strip():
                errors.append(f"secret_refs[{index}] must declare secret_ref")
            raw_secret_keys = [
                key
                for key in item
                if str(key).lower().replace("-", "_") not in SECRET_KEY_ALLOWLIST
                and any(part in str(key).lower().replace("-", "_") for part in SECRET_KEY_PARTS)
            ]
            if raw_secret_keys:
                errors.append(f"secret_refs[{index}] must not include raw secret values")
            continue
        errors.append(f"secret_refs[{index}] must be a string or object")
    return errors


class CapabilityResolutionError(RuntimeError):
    pass


def _manifest_secret_value_errors(value: Any, path: str = "manifest") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            child_path = f"{path}.{key}"
            if normalized == "secret_ref":
                if not isinstance(item, str) or not item.startswith(("vault://", "secret://")):
                    errors.append(f"{child_path} must use a secret ref")
            elif normalized not in SECRET_KEY_ALLOWLIST and any(
                part in normalized for part in SECRET_KEY_PARTS
            ):
                if item not in (None, ""):
                    errors.append(f"{child_path} must be provided as secret_ref, not raw secret")
            errors.extend(_manifest_secret_value_errors(item, child_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            errors.extend(_manifest_secret_value_errors(item, f"{path}[{index}]"))
    return errors


def _identifier_text(value: Any, *, fallback: str) -> str:
    text = str(value or fallback).strip() or fallback
    normalized = []
    previous_dash = False
    for char in text:
        if char.isalnum() or char in {"-", "_", "."}:
            normalized.append(char)
            previous_dash = False
        elif not previous_dash:
            normalized.append("-")
            previous_dash = True
    return "".join(normalized).strip("-_.") or fallback


def _bounded_identifier(value: Any, *, fallback: str, max_length: int) -> str:
    text = _identifier_text(value, fallback=fallback)
    if len(text) <= max_length:
        return text
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    prefix_length = max_length - len(digest) - 1
    prefix = text[:prefix_length].rstrip("-_.") or fallback[:prefix_length]
    return f"{prefix}-{digest}"


def package_key_for_manifest(manifest: dict) -> str:
    return _bounded_identifier(
        manifest.get("name"),
        fallback="unnamed-package",
        max_length=MAX_PACKAGE_KEY_LENGTH,
    )


def capability_key_for_package(package_key: str) -> str:
    return _bounded_identifier(
        f"package:{package_key}",
        fallback="package:unnamed-package",
        max_length=MAX_CAPABILITY_KEY_LENGTH,
    )


def capability_version_id_for_package(package_key: str, content_sha: str, config_sha: str) -> str:
    return _bounded_identifier(
        f"{package_key}:{content_sha[:16]}:{config_sha[:8]}",
        fallback="package-version",
        max_length=MAX_CAPABILITY_VERSION_ID_LENGTH,
    )


def _risk_level_for_manifest(manifest: dict) -> str:
    permissions = {str(item).lower() for item in manifest.get("permissions", [])}
    network_policy = str(manifest.get("network_policy", "none")).lower()
    if "write" in permissions or "shell" in permissions or network_policy not in {"none", ""}:
        return "high"
    if "network" in permissions or "mcp" in permissions:
        return "medium"
    return "low"


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
                    CapabilityVersion.type.in_(EXECUTABLE_CAPABILITY_TYPES),
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
        source = _source_config(redacted)
        source_type = str(source.get("source_type") or "private_upload").strip().lower()
        package_type = str(source.get("package_type") or "tool_definition").strip().lower()
        permissions = source.get("permissions")
        provenance = source.get("provenance") if isinstance(source.get("provenance"), dict) else {}
        manifest = source["manifest"] if isinstance(source.get("manifest"), dict) else {}
        is_package_manifest = any(
            key in manifest
            for key in ("package_type", "tool_metadata", "permissions", "version", "runtime")
        )

        errors: list[str] = []
        warnings: list[str] = []
        validation = (
            validate_package_manifest(manifest)
            if is_package_manifest
            else {
                "status": "valid",
                "errors": [],
                "risk_level": "low",
                "no_code_execution": True,
            }
        )
        if is_package_manifest:
            if package_type not in ALLOWED_PACKAGE_TYPES:
                errors.append(f"unsupported package_type: {package_type}")
            if permissions is not None and not isinstance(permissions, list):
                errors.append("package manifest permissions must be a list")
            errors.extend(validation["errors"])

        public_source = _is_public_source(source_type)
        if public_source:
            errors.extend(_validate_public_source_url(source.get("source_url")))
            if not source.get("digest") and not source.get("commit"):
                errors.append("public package source must be pinned by digest or commit")
        errors.extend(_secret_refs_shape_errors(source.get("secret_refs")))
        errors.extend(_manifest_secret_value_errors(source.get("secret_refs")))

        has_provenance = any(provenance.get(key) for key in ("signature", "sbom", "attestation"))
        if not has_provenance:
            warnings.append("package provenance signature/SBOM/attestation was not supplied")

        risk_score = 10
        if public_source:
            risk_score += 40
        if permissions:
            risk_score += min(30, len(permissions) * 10)
        if source.get("secret_refs"):
            risk_score += 10
        risk_score = min(risk_score, 100)

        return {
            "status": "valid" if not errors else "invalid",
            "schema_version": CAPABILITY_SCHEMA_VERSION,
            "content_sha256": stable_json_sha256(redacted.get("content", {})),
            "config_sha256": stable_json_sha256(redacted.get("config", {})),
            "errors": errors,
            "warnings": warnings,
            "risk_score": risk_score,
            "approval_required": public_source or risk_score >= 50,
            "validation_mode": "manifest_only_no_execution",
            "source_policy": {
                "source_type": source_type,
                "source_url": source.get("source_url"),
                "public_source": public_source,
                "pinned": bool(source.get("digest") or source.get("commit")),
                "ssrf_private_network_checked": public_source,
                "allowed_schemes": sorted(ALLOWED_PUBLIC_SCHEMES),
            },
            "manifest_summary": {
                "package_type": package_type,
                "permissions": permissions or [],
                "secret_ref_count": len(source.get("secret_refs") or []),
                "has_provenance_evidence": has_provenance,
                "package_manifest": is_package_manifest,
            },
            "redacted_payload": redacted,
            "validation": validation,
        }

    def stage_private_package(
        self,
        *,
        manifest: dict,
        content: dict | None = None,
        created_by: str | None = None,
    ) -> CapabilityPackage:
        return self._stage_package(
            manifest=manifest,
            content=content or {},
            source_kind="private_upload",
            source_uri=None,
            pinned_ref=None,
            created_by=created_by,
        )

    def stage_public_package(
        self,
        *,
        manifest: dict,
        source_kind: str,
        source_uri: str,
        pinned_ref: str,
        content: dict | None = None,
        created_by: str | None = None,
    ) -> CapabilityPackage:
        if source_kind not in PUBLIC_SOURCE_KINDS:
            raise CapabilityResolutionError(
                "public package source_kind must be public_url or public_git"
            )
        source_policy = validate_public_source(source_uri, pinned_ref=pinned_ref)
        if source_policy["status"] != "valid":
            raise CapabilityResolutionError(source_policy["errors"][0])
        package = self._stage_package(
            manifest=manifest,
            content=content or {},
            source_kind=source_kind,
            source_uri=source_uri,
            pinned_ref=pinned_ref,
            created_by=created_by,
        )
        package.validation_json = {
            **package.validation_json,
            "public_source_policy": source_policy,
            "staging_execution": "manifest_only_no_code_execution",
        }
        self.session.flush()
        return package

    def install_trusted_url_package(
        self,
        *,
        manifest: dict,
        source_uri: str,
        trusted_hosts: set[str],
        pinned_ref: str | None = None,
        content: dict | None = None,
        agent_id: str | None = None,
        created_by: str | None = None,
    ) -> tuple[CapabilityPackage, AgentCapabilityAttachment | None]:
        host = _normalized_host(source_uri)
        if not host or host not in trusted_hosts:
            raise CapabilityResolutionError("trusted URL host is not allowlisted")
        source_policy = validate_trusted_source(source_uri)
        if source_policy["status"] != "valid":
            raise CapabilityResolutionError("; ".join(source_policy["errors"]))
        source_kind = "trusted_git" if source_uri.startswith("git+") else "trusted_url"
        downloaded = None
        effective_content = content or {}
        effective_pin = pinned_ref
        if not effective_content and source_kind == "trusted_url":
            downloaded = download_remote_package_content(source_uri)
            effective_content = downloaded.content
            effective_pin = effective_pin or downloaded.pinned_ref
        elif not effective_content and source_kind == "trusted_git":
            raise CapabilityResolutionError(
                "trusted git install requires supplied package content metadata in v1"
            )
        package = self._stage_package(
            manifest=manifest,
            content=effective_content,
            source_kind=source_kind,
            source_uri=source_uri,
            pinned_ref=effective_pin,
            created_by=created_by,
        )
        if package.status != "staged":
            return package, None
        if downloaded is not None:
            package.validation_json = {
                **package.validation_json,
                "download": downloaded.metadata,
            }
            package.provenance_json = {
                **package.provenance_json,
                "download": downloaded.metadata,
            }
        package.audit_json = {
            **package.audit_json,
            "trusted_install": {
                "host": host,
                "auto_enable_allowed": True,
                "source_policy": source_policy,
            },
        }
        package = self.approve_package(package_id=package.id, approved_by=created_by)
        attachment = None
        if agent_id:
            attachment = self.attach_package_capability(
                package_id=package.id,
                agent_id=agent_id,
                attached_by=created_by,
                enabled=True,
                priority=10,
            )
        return package, attachment

    def preflight_public_url_package(
        self,
        *,
        manifest: dict,
        source_uri: str,
        pinned_ref: str | None = None,
        content: dict | None = None,
        created_by: str | None = None,
    ) -> CapabilityPackage:
        source_kind = "public_git" if source_uri.startswith("git+") else "public_url"
        downloaded = None
        effective_content = content or {}
        effective_pin = pinned_ref
        if source_kind == "public_url" and not effective_content:
            downloaded = download_remote_package_content(source_uri)
            effective_content = downloaded.content
            effective_pin = effective_pin or downloaded.pinned_ref
        if not effective_pin and not effective_content:
            raise CapabilityResolutionError(
                "public preflight requires pinned_ref or downloaded package content hash"
            )
        effective_pin = effective_pin or f"sha256:{stable_json_sha256(effective_content)}"
        package = self.stage_public_package(
            manifest=manifest,
            source_kind=source_kind,
            source_uri=source_uri,
            pinned_ref=effective_pin,
            content=effective_content,
            created_by=created_by,
        )
        if downloaded is not None:
            package.validation_json = {
                **package.validation_json,
                "download": downloaded.metadata,
            }
            package.provenance_json = {
                **package.provenance_json,
                "download": downloaded.metadata,
            }
            self.session.flush()
        return package

    def install_uploaded_package(
        self,
        *,
        manifest: dict,
        content: dict | None = None,
        agent_id: str | None = None,
        created_by: str | None = None,
    ) -> tuple[CapabilityPackage, AgentCapabilityAttachment | None]:
        package = self.stage_private_package(
            manifest=manifest,
            content=content or {},
            created_by=created_by,
        )
        if package.status != "staged":
            return package, None
        package = self.approve_package(package_id=package.id, approved_by=created_by)
        attachment = None
        if agent_id:
            attachment = self.attach_package_capability(
                package_id=package.id,
                agent_id=agent_id,
                attached_by=created_by,
                enabled=True,
                priority=10,
            )
        return package, attachment

    def approve_package(
        self,
        *,
        package_id: str,
        approved_by: str | None = None,
    ) -> CapabilityPackage:
        package = self._package(package_id)
        if package.status not in {"staged", "rejected"}:
            return package
        validation = validate_package_manifest(package.manifest_json)
        if validation["status"] != "valid":
            raise CapabilityResolutionError("; ".join(validation["errors"]))
        if package.source_kind in PUBLIC_SOURCE_KINDS:
            source_policy = validate_public_source(
                str(package.source_uri or ""),
                pinned_ref=package.pinned_ref,
            )
            if source_policy["status"] != "valid":
                raise CapabilityResolutionError("; ".join(source_policy["errors"]))
        capability = self._get_or_create_package_capability(package)
        version = self._create_package_version(capability, package)
        capability.current_version_id = version.id
        capability.status = "active"
        capability.updated_at = utc_now()
        package.status = "approved"
        package.capability_id = capability.id
        package.capability_version_id = version.id
        package.approved_by = approved_by
        package.approved_at = utc_now()
        package.updated_at = utc_now()
        package.audit_json = {
            **package.audit_json,
            "approval": {
                "approved_by": approved_by,
                "capability_version_id": version.id,
                "immutable_version": True,
                "runtime_activation_requires_agent_attachment": True,
            },
        }
        self.session.flush()
        return package

    def attach_package_capability(
        self,
        *,
        package_id: str,
        agent_id: str,
        attached_by: str | None = None,
        enabled: bool = True,
        priority: int = 100,
    ) -> AgentCapabilityAttachment:
        self._agent(agent_id)
        package = self._package(package_id)
        if (
            package.status != "approved"
            or not package.capability_version_id
            or not package.capability_id
        ):
            raise CapabilityResolutionError("package must be approved before attachment")
        existing = self.session.execute(
            select(AgentCapabilityAttachment).where(
                AgentCapabilityAttachment.agent_id == agent_id,
                AgentCapabilityAttachment.capability_version_id == package.capability_version_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.enabled = enabled
            existing.priority = priority
            self.session.flush()
            return existing
        attachment = AgentCapabilityAttachment(
            organization_id=self.organization_id,
            agent_id=agent_id,
            capability_id=package.capability_id,
            capability_version_id=package.capability_version_id,
            enabled=enabled,
            priority=priority,
            attached_by=attached_by,
            attached_at=utc_now(),
        )
        self.session.add(attachment)
        self.session.flush()
        return attachment

    def list_packages(self) -> list[CapabilityPackage]:
        return list(
            self.session.execute(
                select(CapabilityPackage)
                .where(
                    or_(
                        CapabilityPackage.organization_id == self.organization_id,
                        CapabilityPackage.organization_id.is_(None),
                    )
                )
                .order_by(CapabilityPackage.created_at.desc())
            ).scalars()
        )

    def rollback_package(
        self,
        *,
        package_id: str,
        capability_version_id: str,
        updated_by: str | None = None,
    ) -> CapabilityPackage:
        package = self._package(package_id)
        if not package.capability_id:
            raise CapabilityResolutionError("package has no installed capability")
        version = self.session.get(CapabilityVersion, capability_version_id)
        if version is None or version.capability_id != package.capability_id:
            raise CapabilityResolutionError("rollback target is not a version of this package")
        capability = self.session.get(Capability, package.capability_id)
        if capability is None:
            raise CapabilityResolutionError("installed capability not found")
        capability.current_version_id = version.id
        capability.status = "active"
        capability.updated_at = utc_now()
        package.capability_version_id = version.id
        package.status = "approved"
        package.updated_at = utc_now()
        package.audit_json = {
            **package.audit_json,
            "rollback": {
                "target_capability_version_id": version.id,
                "updated_by": updated_by,
                "history_mutated": False,
            },
        }
        self.session.flush()
        return package

    def uninstall_package(
        self,
        *,
        package_id: str,
        updated_by: str | None = None,
    ) -> CapabilityPackage:
        package = self._package(package_id)
        if not package.capability_id:
            package.status = "uninstalled"
            self.session.flush()
            return package
        active_attachment = self.session.execute(
            select(AgentCapabilityAttachment.id).where(
                AgentCapabilityAttachment.capability_id == package.capability_id,
                AgentCapabilityAttachment.enabled.is_(True),
            )
        ).first()
        if active_attachment is not None:
            raise CapabilityResolutionError("cannot uninstall package with active attachments")
        capability = self.session.get(Capability, package.capability_id)
        if capability is not None:
            capability.status = "inactive"
            capability.updated_at = utc_now()
        package.status = "uninstalled"
        package.updated_at = utc_now()
        package.audit_json = {
            **package.audit_json,
            "uninstall": {"updated_by": updated_by, "active_attachments_blocked": True},
        }
        self.session.flush()
        return package

    def set_attachment_enabled(
        self,
        *,
        attachment_id: str,
        enabled: bool,
    ) -> AgentCapabilityAttachment:
        attachment = self.session.get(AgentCapabilityAttachment, attachment_id)
        if attachment is None or attachment.organization_id != self.organization_id:
            raise CapabilityResolutionError(f"attachment not found: {attachment_id}")
        attachment.enabled = enabled
        self.session.flush()
        return attachment

    def metadata_for_tool_name(self, tool_name: str) -> ToolMetadata | None:
        for version in self.session.execute(
            select(CapabilityVersion)
            .join(Capability, CapabilityVersion.capability_id == Capability.id)
            .where(
                or_(
                    Capability.organization_id == self.organization_id,
                    Capability.organization_id.is_(None),
                )
            )
        ).scalars():
            raw = version.content_json.get("tool_metadata")
            if isinstance(raw, dict) and raw.get("name") == tool_name:
                return ToolMetadata.model_validate(raw)
        return None

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
                    CapabilityVersion.type.in_(EXECUTABLE_CAPABILITY_TYPES),
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

    def _package(self, package_id: str) -> CapabilityPackage:
        package = self.session.execute(
            select(CapabilityPackage).where(
                CapabilityPackage.id == package_id,
                or_(
                    CapabilityPackage.organization_id == self.organization_id,
                    CapabilityPackage.organization_id.is_(None),
                ),
            )
        ).scalar_one_or_none()
        if package is None:
            raise CapabilityResolutionError(f"package not found: {package_id}")
        return package

    def _stage_package(
        self,
        *,
        manifest: dict,
        content: dict,
        source_kind: str,
        source_uri: str | None,
        pinned_ref: str | None,
        created_by: str | None,
    ) -> CapabilityPackage:
        redacted_manifest = redact_secrets(manifest)
        redacted_content = redact_secrets(content)
        validation = validate_package_manifest(redacted_manifest)
        source_sha = stable_json_sha256(
            {
                "manifest": redacted_manifest,
                "content": redacted_content,
                "source_uri": source_uri,
                "pinned_ref": pinned_ref,
            }
        )
        package = CapabilityPackage(
            organization_id=self.organization_id,
            package_key=package_key_for_manifest(redacted_manifest),
            package_type=str(redacted_manifest.get("package_type")),
            source_kind=source_kind,
            source_uri=source_uri,
            source_sha256=source_sha,
            pinned_ref=pinned_ref,
            status="staged" if validation["status"] == "valid" else "invalid",
            risk_level=str(
                redacted_manifest.get("risk_level", validation.get("risk_level", "medium"))
            ),
            manifest_json=redacted_manifest,
            validation_json={
                **validation,
                "staging_execution": "manifest_only_no_code_execution",
                "content_sha256": stable_json_sha256(redacted_content),
            },
            provenance_json={
                "source_kind": source_kind,
                "source_uri": source_uri,
                "pinned_ref": pinned_ref,
                "source_sha256": source_sha,
                "sbom": redacted_manifest.get("sbom"),
                "signature": redacted_manifest.get("signature"),
            },
            audit_json={
                "events": [
                    {
                        "event": "package_staged",
                        "no_code_execution": True,
                        "requires_approval": source_kind in PUBLIC_SOURCE_KINDS,
                    }
                ]
            },
            created_by=created_by,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self.session.add(package)
        self.session.flush()
        return package

    def _get_or_create_package_capability(self, package: CapabilityPackage) -> Capability:
        key = capability_key_for_package(package.package_key)
        capability = self.session.execute(
            select(Capability).where(
                Capability.organization_id == self.organization_id,
                Capability.capability_key == key,
            )
        ).scalar_one_or_none()
        if capability is not None:
            return capability
        capability = Capability(
            organization_id=self.organization_id,
            capability_key=key,
            type=_capability_type_for_package(package.package_type, package.manifest_json),
            status="active",
            schema_version=CAPABILITY_SCHEMA_VERSION,
            created_by=package.created_by,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self.session.add(capability)
        self.session.flush()
        return capability

    def _create_package_version(
        self,
        capability: Capability,
        package: CapabilityPackage,
    ) -> CapabilityVersion:
        content = package_content_for_version(package)
        config = {
            "secret_refs": package.manifest_json.get("secret_refs", []),
            "permissions": package.manifest_json.get("permissions", []),
            "source_kind": package.source_kind,
            "source_uri": package.source_uri,
            "pinned_ref": package.pinned_ref,
            "package_id": package.id,
        }
        content_sha = stable_json_sha256(content)
        config_sha = stable_json_sha256(config)
        existing_count = self.session.execute(
            select(CapabilityVersion).where(CapabilityVersion.capability_id == capability.id)
        ).scalars().all()
        version_number = len(existing_count) + 1
        version_id = capability_version_id_for_package(
            package.package_key,
            content_sha,
            config_sha,
        )
        existing = self.session.get(CapabilityVersion, version_id)
        if existing is not None:
            return existing
        version = CapabilityVersion(
            id=version_id,
            capability_id=capability.id,
            version=version_number,
            type=capability.type,
            status="active",
            content_json=content,
            config_json=config,
            content_sha256=content_sha,
            config_sha256=config_sha,
            schema_version=CAPABILITY_SCHEMA_VERSION,
            created_by=package.approved_by or package.created_by,
            created_at=utc_now(),
        )
        self.session.add(version)
        self.session.flush()
        return version

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


def validate_package_manifest(manifest: dict | None) -> dict:
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return {"status": "invalid", "errors": ["manifest must be an object"], "risk_level": "high"}
    for error in sorted(PACKAGE_MANIFEST_VALIDATOR.iter_errors(manifest), key=str):
        path = ".".join(str(part) for part in error.path)
        prefix = f"{path}: " if path else ""
        errors.append(f"{prefix}{error.message}")
    package_type = manifest.get("package_type")
    permissions = manifest.get("permissions")
    permission_count = len(permissions) if isinstance(permissions, list) else 0
    secret_refs = manifest.get("secret_refs", [])
    secret_ref_count = len(secret_refs) if isinstance(secret_refs, list) else 0
    if package_type != "context_optimizer" and _contains_raw_secret(manifest):
        errors.append("raw secret-like values are not allowed; use secret_refs")
    if package_type == "tool_definition":
        tool_metadata = manifest.get("tool_metadata")
        if not isinstance(tool_metadata, dict):
            errors.append("tool_definition requires tool_metadata")
        else:
            try:
                ToolMetadata.model_validate(tool_metadata)
            except Exception as exc:  # pragma: no cover - pydantic message is enough
                errors.append(f"tool_metadata is invalid: {exc}")
    if package_type == "mcp_server":
        transport = manifest.get("transport")
        if transport not in {"stdio", "http", "sse"}:
            errors.append("mcp_server transport must be stdio, http, or sse")
        if manifest.get("auth_required") and not secret_refs:
            errors.append("mcp_server auth requires secret_refs")
    if package_type == "context_optimizer":
        errors.extend(_context_optimizer_manifest_errors(manifest))
    risk_level = str(
        manifest.get("risk_level")
        or _risk_from_permissions(permissions if isinstance(permissions, list) else [])
    )
    return {
        "status": "invalid" if errors else "valid",
        "errors": errors,
        "risk_level": risk_level,
        "permission_count": permission_count,
        "secret_ref_count": secret_ref_count,
        "no_code_execution": True,
        "jsonschema_draft": "2020-12",
    }


def _context_optimizer_manifest_errors(manifest: dict) -> list[str]:
    errors: list[str] = []
    allowed_manifest_keys = {
        "name",
        "version",
        "description",
        "package_type",
        "schema_version",
        "display_name",
        "risk_level",
        "permissions",
        "provenance",
        "optimizer",
        "secret_refs",
    }
    unknown_manifest_keys = sorted(set(manifest) - allowed_manifest_keys)
    if unknown_manifest_keys:
        errors.append(
            "context_optimizer manifest has unsupported fields: "
            + ", ".join(unknown_manifest_keys)
        )
    if manifest.get("schema_version") != "context-optimizer-v1":
        errors.append("context_optimizer schema_version must be context-optimizer-v1")
    optimizer = manifest.get("optimizer")
    if not isinstance(optimizer, dict):
        errors.append("context_optimizer requires optimizer object")
        return errors
    allowed_optimizer_keys = {
        "mode",
        "max_candidate_tokens_ratio",
        "section_limits",
        "drop_order",
        "prefer_valid_compressed_summary",
        "low_cost_route_hint",
    }
    unknown_keys = sorted(set(optimizer) - allowed_optimizer_keys)
    if unknown_keys:
        errors.append(
            "context_optimizer optimizer has unsupported fields: " + ", ".join(unknown_keys)
        )
    if optimizer.get("mode") != "budget_overlay":
        errors.append("context_optimizer optimizer.mode must be budget_overlay")
    ratio = optimizer.get("max_candidate_tokens_ratio")
    if ratio is not None and (
        isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or ratio <= 0 or ratio > 1
    ):
        errors.append("context_optimizer max_candidate_tokens_ratio must be > 0 and <= 1")
    section_limits = optimizer.get("section_limits", {})
    allowed_section_types = {
        "recent_window",
        "attachments_summary",
        "long_term_memory",
        "compressed_summary",
        "rag_evidence",
    }
    if section_limits is not None:
        if not isinstance(section_limits, dict):
            errors.append("context_optimizer section_limits must be an object")
        else:
            for section_type, limit in section_limits.items():
                if section_type not in allowed_section_types:
                    errors.append(f"context_optimizer section limit unsupported: {section_type}")
                if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
                    errors.append(
                        "context_optimizer section limit for "
                        f"{section_type} must be a non-negative integer"
                    )
    allowed_drop_rules = {
        "rag_evidence_low_relevance_first",
        "long_term_memory_low_score_first",
        "compressed_summary",
        "compressed_summary_if_stale",
        "attachments_summary",
        "recent_window_oldest_first",
    }
    drop_order = optimizer.get("drop_order", [])
    if drop_order is not None:
        if not isinstance(drop_order, list) or not all(
            isinstance(item, str) for item in drop_order
        ):
            errors.append("context_optimizer drop_order must be a string array")
        else:
            unsupported = [item for item in drop_order if item not in allowed_drop_rules]
            if unsupported:
                errors.append(
                    "context_optimizer drop_order has unsupported rules: "
                    + ", ".join(unsupported)
                )
    prefer_summary = optimizer.get("prefer_valid_compressed_summary")
    if prefer_summary is not None and not isinstance(prefer_summary, bool):
        errors.append("context_optimizer prefer_valid_compressed_summary must be boolean")
    hint = optimizer.get("low_cost_route_hint")
    if hint is not None and (not isinstance(hint, str) or len(hint) > 200):
        errors.append("context_optimizer low_cost_route_hint must be a string up to 200 chars")
    if manifest.get("secret_refs"):
        errors.append("context_optimizer must not require secret_refs in v1")
    permissions = manifest.get("permissions")
    if permissions not in (None, [], ["context:optimize"]):
        errors.append("context_optimizer permissions must be empty or ['context:optimize']")
    return errors


def validate_public_source(source_uri: str, *, pinned_ref: str | None) -> dict:
    errors: list[str] = []
    parsed = urlparse(source_uri)
    if parsed.scheme not in {"https", "git+https"}:
        errors.append("public source scheme must be https or git+https")
    if parsed.username or parsed.password:
        errors.append("credentials in public source URLs are not allowed")
    host = (parsed.hostname or "").lower()
    if not host:
        errors.append("public source host is required")
    elif host in BLOCKED_HOSTS:
        errors.append("public source host is blocked")
    else:
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                errors.append("public source IP is not publicly routable")
        if not errors:
            for resolver_error in _resolved_public_host_errors(host):
                errors.append(resolver_error.replace("public package source", "public source"))
    if not pinned_ref:
        errors.append("public source must be pinned by digest, commit, or archive identity")
    return {"status": "invalid" if errors else "valid", "errors": errors, "pinned_ref": pinned_ref}


def _normalized_host(source_uri: str) -> str:
    parsed = urlparse(source_uri)
    return (parsed.hostname or "").strip().lower().rstrip(".")


def package_content_for_version(package: CapabilityPackage) -> dict:
    manifest = package.manifest_json
    if isinstance(manifest.get("tool_metadata"), dict):
        return {
            "tool_metadata": manifest["tool_metadata"],
            "package_manifest": manifest,
            "package_provenance": package.provenance_json,
        }
    return {
        "package_manifest": manifest,
        "package_provenance": package.provenance_json,
    }


def _capability_type_for_package(package_type: str, manifest: dict) -> str:
    if package_type == "mcp_server":
        return CAPABILITY_TYPE_MCP_TOOL
    if package_type == "skill_pack":
        return CAPABILITY_TYPE_SKILL
    if package_type == "knowledge_connector":
        return CAPABILITY_TYPE_KNOWLEDGE_CONNECTOR
    if package_type == "context_optimizer":
        return CAPABILITY_TYPE_CONTEXT_OPTIMIZER
    if package_type == "tool_definition":
        metadata = manifest.get("tool_metadata")
        if isinstance(metadata, dict) and metadata.get("source") == "mcp":
            return CAPABILITY_TYPE_MCP_TOOL
        return CAPABILITY_TYPE_BUILTIN_TOOL
    return package_type


def _risk_from_permissions(permissions: list) -> str:
    normalized = {str(item).lower() for item in permissions}
    if {"network", "shell", "filesystem:write"}.intersection(normalized):
        return "high"
    if normalized:
        return "medium"
    return "low"


def _contains_raw_secret(value: Any, *, key_path: str = "") -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in SECRET_KEY_ALLOWLIST:
                continue
            if any(part in normalized for part in SECRET_KEY_PARTS):
                if isinstance(item, str) and item and not item.startswith("secret://"):
                    return True
            if _contains_raw_secret(item, key_path=f"{key_path}.{key}"):
                return True
    if isinstance(value, list):
        return any(_contains_raw_secret(item, key_path=key_path) for item in value)
    return False
