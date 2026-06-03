import shutil
import time
from importlib.util import find_spec
from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from jsonschema import Draft202012Validator
from sqlalchemy.orm import Session

from app.agents.registry import ensure_default_agents
from app.api.schemas import (
    AdapterHealthResponse,
    AdapterMetadataPage,
    AdapterMetadataResponse,
    CapabilityAdminValidationRequest,
    CapabilityAdminValidationResponse,
    CapabilityAttachmentUpdateRequest,
    CapabilityMarketplacePreflightRequest,
    CapabilityMarketplaceResponse,
    CapabilityPackageApproveRequest,
    CapabilityPackageAttachRequest,
    CapabilityPackageAttachResponse,
    CapabilityPackagePage,
    CapabilityPackageResponse,
    CapabilityPackageRollbackRequest,
    CapabilityPackageStageRequest,
    CapabilityPublicPackageStageRequest,
    CapabilityRuntimeConfigPage,
    CapabilityRuntimeConfigResponse,
    CapabilityRuntimeConfigUpdateRequest,
    CapabilitySimpleInstallRequest,
    CapabilitySimpleInstallResponse,
    CapabilityTestInvocationRequest,
    MCPDiscoveredToolResponse,
    MCPServerDiscoverResponse,
    MCPServerPage,
    MCPServerResponse,
    ToolExecuteResponse,
    ToolMetadataResponse,
    ToolRegistryResponse,
)
from app.api.tasks import _to_tool_call_response
from app.core.config import get_settings
from app.db.models import Task, utc_now
from app.db.session import get_db_session
from app.knowledge_connectors import connector_provider_release_matrix
from app.knowledge_dify import (
    resolve_connector_secret_ref,
    secret_ref_looks_like_raw_secret,
    store_connector_secret_ref,
)
from app.security.auth import Principal, require_role
from app.tools.adapter_registry import REGISTRY, adapter_metadata
from app.tools.adapters import ensure_builtin_adapters_registered
from app.tools.capabilities import (
    CapabilityRegistry,
    CapabilityResolutionError,
    _discovered_tool_name,
    _risk_level_from_mcp_annotations,
)
from app.tools.marketplace import list_capability_marketplace
from app.tools.mcp_protocol.discovery import discover_tools
from app.tools.registry import ToolRegistry
from app.tools.runner import ToolRunner

router = APIRouter(prefix="/tools", tags=["tools"])
DbSession = Annotated[Session, Depends(get_db_session)]
_ADAPTER_HEALTH_LIMITS: dict[str, list[float]] = {}
ADAPTER_HEALTH_MAX_PER_MINUTE = 10
STDIO_COMMAND_ALLOWED_CHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._/-@+"
)
STDIO_ARG_BLOCKED_CHARS = {"\n", "\r", "\x00"}


def _bad_request_from_capability_error(exc: CapabilityResolutionError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get(
    "/registry",
    response_model=ToolRegistryResponse,
    summary="查询 Tool Registry",
    description="返回内置工具和 MCP-shaped 工具的统一注册表、风险、权限和 schema。",
)
def get_tool_registry(
    session: DbSession,
    principal: Principal,
    agent_id: str | None = None,
) -> ToolRegistryResponse:
    if agent_id:
        ensure_default_agents(session, principal.organization_id)
        session.commit()
        try:
            registry, _snapshot = CapabilityRegistry(
                session,
                principal.organization_id,
            ).tool_registry_for_agent(agent_id)
        except CapabilityResolutionError as exc:
            raise _bad_request_from_capability_error(exc) from exc
    else:
        registry = ToolRegistry.default()
    tools = [
        tool
        for tool in registry.list_tools()
        if set(principal.roles).intersection(tool.allowed_roles)
    ]
    return ToolRegistryResponse(
        items=[ToolMetadataResponse.model_validate(tool) for tool in tools],
        categories=sorted({tool.category for tool in tools}),
        sources=sorted({tool.source for tool in tools}),
    )


@router.get(
    "/adapters",
    response_model=AdapterMetadataPage,
    summary="List registered real tool adapters",
)
def list_tool_adapters(principal: Principal) -> AdapterMetadataPage:
    require_role(principal, {"admin", "engineer"})
    ensure_builtin_adapters_registered(REGISTRY)
    return AdapterMetadataPage(
        items=[
            AdapterMetadataResponse(**adapter_metadata(adapter))
            for adapter in REGISTRY.list_all()
        ]
    )


@router.get(
    "/adapters/{slug}/health",
    response_model=AdapterHealthResponse,
    summary="Probe a registered tool adapter",
)
def get_tool_adapter_health(
    slug: str,
    session: DbSession,
    principal: Principal,
    agent_id: str = "default",
) -> AdapterHealthResponse:
    require_role(principal, {"admin", "engineer"})
    ensure_builtin_adapters_registered(REGISTRY)
    adapter = REGISTRY.get(slug)
    if adapter is None:
        raise HTTPException(status_code=404, detail="adapter not found")
    _enforce_adapter_health_rate_limit(principal.organization_id, slug)
    config: dict = {}
    secret_value = ""
    try:
        record = CapabilityRegistry(
            session,
            principal.organization_id,
        ).runtime_config_for_tool(agent_id=agent_id, tool_name=slug)
        config = record.get("config_json") if isinstance(record.get("config_json"), dict) else {}
        secret_ref = str(config.get("secret_ref") or "").strip()
        if secret_ref:
            secret_value = resolve_connector_secret_ref(
                secret_ref,
                provider=slug,
                session=session,
                organization_id=principal.organization_id,
            )
    except CapabilityResolutionError:
        config = {}
        secret_value = ""
    result = adapter.health_check(config_json=config, secret_value=secret_value)
    return AdapterHealthResponse(
        slug=slug,
        ok=bool(result.get("ok")),
        latency_ms=int(result.get("latency_ms") or 0),
        message=str(result.get("message") or ""),
        sample=result.get("sample") if isinstance(result.get("sample"), dict) else {},
        last_checked_at=utc_now(),
    )


@router.get(
    "/mcp-servers",
    response_model=MCPServerPage,
    summary="List configured MCP protocol servers",
)
def list_mcp_servers(
    session: DbSession,
    principal: Principal,
    agent_id: str = "default",
) -> MCPServerPage:
    require_role(principal, {"admin", "engineer"})
    ensure_default_agents(session, principal.organization_id)
    session.commit()
    try:
        records = CapabilityRegistry(session, principal.organization_id).list_runtime_configs(
            agent_id
        )
    except CapabilityResolutionError as exc:
        raise _bad_request_from_capability_error(exc) from exc
    items = [
        _mcp_server_response(
            record,
            discovered_tools=[],
            resources_count=0,
            discovery_status="idle",
            discovery_message="",
            child_tool_count=_child_tool_count(records, _server_slug(record)),
        )
        for record in records
        if not str(record.get("tool_name") or "").startswith("mcp.")
    ]
    return MCPServerPage(items=items)


@router.post(
    "/mcp-servers/{tool_name:path}/discover",
    response_model=MCPServerDiscoverResponse,
    summary="Discover MCP protocol tools and register child capabilities",
)
def discover_mcp_server_tools(
    tool_name: str,
    session: DbSession,
    principal: Principal,
    agent_id: str = "default",
) -> MCPServerDiscoverResponse:
    require_role(principal, {"admin", "engineer"})
    ensure_default_agents(session, principal.organization_id)
    session.commit()
    registry = CapabilityRegistry(session, principal.organization_id)
    try:
        record = registry.runtime_config_for_tool(agent_id=agent_id, tool_name=tool_name)
    except CapabilityResolutionError as exc:
        raise _bad_request_from_capability_error(exc) from exc
    config = record.get("config_json") if isinstance(record.get("config_json"), dict) else {}
    runtime = config.get("runtime") if isinstance(config.get("runtime"), dict) else {}
    secret_ref = str(config.get("secret_ref") or "").strip()
    secret_value = ""
    if secret_ref:
        secret_value = resolve_connector_secret_ref(
            secret_ref,
            provider=tool_name,
            session=session,
            organization_id=principal.organization_id,
        )
    server_slug = _server_slug(record)
    discovery = discover_tools(
        server_slug=server_slug,
        runtime=runtime,
        secret_value=secret_value,
    )
    discovered = [_discovered_tool_response(server_slug, tool) for tool in discovery.tools]
    registered: list[dict] = []
    if discovery.ok and discovery.tools:
        registered = registry.register_discovered_mcp_tools(
            agent_id=agent_id,
            server_tool_name=tool_name,
            server_slug=server_slug,
            discovered_tools=[
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                    "annotations": tool.annotations,
                }
                for tool in discovery.tools
            ],
            runtime=runtime,
            secret_ref=secret_ref or None,
            created_by=principal.user_id,
        )
        session.commit()
    return MCPServerDiscoverResponse(
        **_mcp_server_response(
            record,
            discovered_tools=discovered,
            resources_count=discovery.resources_count,
            discovery_status="ready" if discovery.ok else "failed",
            discovery_message=discovery.message,
            child_tool_count=len(registered),
        ).model_dump(),
        registered_runtime_configs=[
            _runtime_config_response(
                item,
                session=session,
                organization_id=principal.organization_id,
            ).model_dump()
            for item in registered
        ],
    )


def _enforce_adapter_health_rate_limit(organization_id: str | None, slug: str) -> None:
    key = f"{organization_id or 'global'}:{slug}"
    now = time.monotonic()
    recent = [stamp for stamp in _ADAPTER_HEALTH_LIMITS.get(key, []) if now - stamp < 60]
    if len(recent) >= ADAPTER_HEALTH_MAX_PER_MINUTE:
        raise HTTPException(status_code=429, detail="adapter health rate limit exceeded")
    recent.append(now)
    _ADAPTER_HEALTH_LIMITS[key] = recent


def _server_slug(record: dict) -> str:
    raw = str(record.get("mcp_server") or record.get("tool_name") or "mcp-server")
    normalized = "".join(char.lower() if char.isalnum() else "-" for char in raw).strip("-")
    return normalized or "mcp-server"


def _child_tool_count(records: list[dict], server_slug: str) -> int:
    prefix = f"mcp.{server_slug}."
    return sum(1 for record in records if str(record.get("tool_name") or "").startswith(prefix))


def _discovered_tool_response(server_slug: str, tool) -> MCPDiscoveredToolResponse:
    slug = _discovered_tool_name(server_slug, tool.name) or f"mcp.{server_slug}.tool"
    return MCPDiscoveredToolResponse(
        name=tool.name,
        slug=slug,
        description=tool.description,
        input_schema=tool.input_schema,
        annotations=tool.annotations,
        risk_level=_risk_level_from_mcp_annotations(tool.annotations),
    )


def _mcp_server_response(
    record: dict,
    *,
    discovered_tools: list[MCPDiscoveredToolResponse],
    resources_count: int,
    discovery_status: str,
    discovery_message: str,
    child_tool_count: int,
) -> MCPServerResponse:
    return MCPServerResponse(
        agent_id=str(record.get("agent_id") or ""),
        tool_name=str(record.get("tool_name") or ""),
        server_slug=_server_slug(record),
        transport=str(record.get("transport") or "http"),
        configured=bool(record.get("configured")),
        discovery_status=discovery_status,
        discovery_message=discovery_message,
        discovered_tools=discovered_tools,
        resources_count=resources_count,
        child_tool_count=child_tool_count,
    )


@router.post(
    "/capabilities/admin-validate",
    response_model=CapabilityAdminValidationResponse,
    summary="Validate capability metadata without execution",
)
def admin_validate_capability(
    request: CapabilityAdminValidationRequest,
    session: DbSession,
    principal: Principal,
) -> CapabilityAdminValidationResponse:
    require_role(principal, {"admin", "engineer"})
    result = CapabilityRegistry(session, principal.organization_id).admin_validate_capability(
        request.model_dump()
    )
    return CapabilityAdminValidationResponse(**result)


@router.get(
    "/capabilities/packages",
    response_model=CapabilityPackagePage,
    summary="List staged and installed capability packages",
)
def list_capability_packages(
    session: DbSession,
    principal: Principal,
) -> CapabilityPackagePage:
    require_role(principal, {"admin", "engineer"})
    packages = CapabilityRegistry(session, principal.organization_id).list_packages()
    return CapabilityPackagePage(
        items=[CapabilityPackageResponse.model_validate(package) for package in packages]
    )


@router.get(
    "/capabilities/marketplace",
    response_model=CapabilityMarketplaceResponse,
    summary="Browse MCP and Skill marketplace entries",
    description=(
        "Aggregates curated Harness entries, the official MCP Registry, and Smithery MCP/Skill "
        "search results into safe Harness install/preflight payloads."
    ),
)
def list_capability_marketplace_entries(
    principal: Principal,
    kind: str = "all",
    query: str = "",
    limit: int = 12,
) -> CapabilityMarketplaceResponse:
    require_role(principal, {"admin", "engineer"})
    return CapabilityMarketplaceResponse(
        **list_capability_marketplace(kind=kind, query=query, limit=limit)
    )


def _trusted_hosts() -> set[str]:
    return {
        host.strip().lower().rstrip(".")
        for host in get_settings().capability_trusted_hosts.split(",")
        if host.strip()
    }


def _simple_manifest(request: CapabilitySimpleInstallRequest) -> dict:
    if request.manifest:
        return request.manifest
    name = request.display_name.strip().lower().replace(" ", "-").replace("/", "-")
    manifest = {
        "name": name or "operator-installed-capability",
        "version": "1.0.0",
        "description": request.description,
        "package_type": request.package_type,
        "permissions": request.permissions,
        "secret_refs": request.secret_refs,
    }
    if request.package_type == "mcp_server":
        manifest["transport"] = "http"
    elif request.package_type == "context_optimizer":
        manifest["schema_version"] = "context-optimizer-v1"
        manifest["optimizer"] = {
            "mode": "budget_overlay",
            "max_candidate_tokens_ratio": 0.8,
            "section_limits": {
                "recent_window": 12,
                "long_term_memory": 8,
                "rag_evidence": 6,
            },
            "drop_order": [
                "rag_evidence_low_relevance_first",
                "long_term_memory_low_score_first",
                "recent_window_oldest_first",
            ],
            "prefer_valid_compressed_summary": True,
            "low_cost_route_hint": "summarization under budget",
        }
    else:
        manifest["runtime"] = {"type": request.package_type}
    return manifest


def _simple_install_response(
    *,
    package,
    attachment=None,
    staged_capability_id: str | None = None,
    next_step_label: str,
) -> CapabilitySimpleInstallResponse:
    ready_state = "invalid"
    if attachment is not None:
        ready_state = "attached"
    elif package.status == "approved":
        ready_state = "ready"
    elif package.status == "staged":
        ready_state = "staged"
    return CapabilitySimpleInstallResponse(
        package=CapabilityPackageResponse.model_validate(package),
        validation_summary={
            "status": package.validation_json.get("status", package.status),
            "risk_level": package.risk_level,
            "source_kind": package.source_kind,
            "no_code_execution": package.validation_json.get("no_code_execution", True),
            "errors": package.validation_json.get("errors", []),
        },
        ready_state=ready_state,
        next_step_label=next_step_label,
        staged_capability_id=staged_capability_id,
        capability_id=package.capability_id,
        capability_version_id=package.capability_version_id,
        attachment=(
            CapabilityPackageAttachResponse(
                attachment_id=attachment.id,
                agent_id=attachment.agent_id,
                capability_id=attachment.capability_id,
                capability_version_id=attachment.capability_version_id,
                enabled=attachment.enabled,
                priority=attachment.priority,
            )
            if attachment is not None
            else None
        ),
    )


def _default_mcp_secret_ref(agent_id: str, tool_name: str) -> str:
    normalized_agent = "".join(
        char.lower() if char.isalnum() else "-" for char in agent_id.strip()
    ).strip("-")
    normalized_tool = "".join(
        char.lower() if char.isalnum() else "-" for char in tool_name.strip()
    ).strip("-")
    return f"secret://mcp/{normalized_agent or 'agent'}/{normalized_tool or 'tool'}/api-key"


def _runtime_endpoint_errors(
    *,
    transport: str,
    endpoint_url: str | None,
    command: str | None,
) -> list[str]:
    errors: list[str] = []
    if transport in {"http", "sse"}:
        if not endpoint_url:
            errors.append("endpoint_url is required for http or sse MCP runtime")
        else:
            parsed = urlparse(endpoint_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                errors.append("endpoint_url must be an absolute http or https URL")
            if parsed.username or parsed.password:
                errors.append("endpoint_url must not contain credentials")
    if transport == "stdio" and not command:
        errors.append("command is required for stdio MCP runtime")
    if transport == "stdio" and command:
        stripped_command = command.strip()
        if not stripped_command or any(char.isspace() for char in stripped_command):
            errors.append("stdio command must be a single executable path or name")
        elif any(char not in STDIO_COMMAND_ALLOWED_CHARS for char in stripped_command):
            errors.append("stdio command contains unsupported characters")
    return errors


def _runtime_arg_errors(args: list[str]) -> list[str]:
    errors: list[str] = []
    for index, raw in enumerate(args[:20]):
        value = str(raw)
        if any(char in value for char in STDIO_ARG_BLOCKED_CHARS):
            errors.append(f"args[{index}] contains unsupported control characters")
    return errors


def _runtime_secret_configured(
    *,
    session: Session,
    organization_id: str | None,
    tool_name: str,
    secret_ref: str | None,
) -> bool:
    if not secret_ref:
        return False
    return bool(
        resolve_connector_secret_ref(
            secret_ref,
            provider=tool_name,
            session=session,
            organization_id=organization_id,
        )
    )


def _runtime_config_response(
    record: dict,
    *,
    session: Session,
    organization_id: str | None,
) -> CapabilityRuntimeConfigResponse:
    secret_ref = record.get("secret_ref")
    secret_configured = _runtime_secret_configured(
        session=session,
        organization_id=organization_id,
        tool_name=str(record.get("tool_name") or ""),
        secret_ref=str(secret_ref) if secret_ref else None,
    )
    missing_fields = list(record.get("missing_fields") or [])
    if secret_ref and not secret_configured and "secret_value" not in missing_fields:
        missing_fields.append("secret_value")
    return CapabilityRuntimeConfigResponse(
        **{
            **record,
            "secret_configured": secret_configured,
            "missing_fields": missing_fields,
            "configured": bool(record.get("configured")) and not missing_fields,
        }
    )


@router.post(
    "/capabilities/install/trusted-url",
    response_model=CapabilitySimpleInstallResponse,
    status_code=201,
    summary="Install and enable a trusted allowlisted URL capability",
)
def install_trusted_url_capability(
    request: CapabilitySimpleInstallRequest,
    session: DbSession,
    principal: Principal,
) -> CapabilitySimpleInstallResponse:
    require_role(principal, {"admin", "engineer"})
    if not request.source_uri:
        raise HTTPException(status_code=400, detail="source_uri is required")
    try:
        package, attachment = CapabilityRegistry(
            session,
            principal.organization_id,
        ).install_trusted_url_package(
            manifest=_simple_manifest(request),
            source_uri=request.source_uri,
            pinned_ref=request.pinned_ref,
            trusted_hosts=_trusted_hosts(),
            content=request.content,
            agent_id=request.agent_id,
            created_by=principal.user_id,
        )
    except CapabilityResolutionError as exc:
        raise _bad_request_from_capability_error(exc) from exc
    session.commit()
    session.refresh(package)
    return _simple_install_response(
        package=package,
        attachment=attachment,
        next_step_label="Open Agent attachment" if attachment else "Attach to Agent",
    )


@router.post(
    "/capabilities/preflight/public-url",
    response_model=CapabilitySimpleInstallResponse,
    status_code=201,
    summary="Download and preflight an arbitrary public URL capability without activation",
)
def preflight_public_url_capability(
    request: CapabilitySimpleInstallRequest,
    session: DbSession,
    principal: Principal,
) -> CapabilitySimpleInstallResponse:
    require_role(principal, {"admin", "engineer"})
    if not request.source_uri:
        raise HTTPException(status_code=400, detail="source_uri is required")
    try:
        package = CapabilityRegistry(
            session,
            principal.organization_id,
        ).preflight_public_url_package(
            manifest=_simple_manifest(request),
            source_uri=request.source_uri,
            pinned_ref=request.pinned_ref,
            content=request.content,
            created_by=principal.user_id,
        )
    except CapabilityResolutionError as exc:
        raise _bad_request_from_capability_error(exc) from exc
    session.commit()
    session.refresh(package)
    return _simple_install_response(
        package=package,
        staged_capability_id=package.id,
        next_step_label="Enable after validation",
    )


@router.post(
    "/capabilities/preflight/marketplace",
    response_model=CapabilitySimpleInstallResponse,
    status_code=201,
    summary="Register marketplace metadata for approval without fetching the listed URL",
)
def preflight_marketplace_capability(
    request: CapabilityMarketplacePreflightRequest,
    session: DbSession,
    principal: Principal,
) -> CapabilitySimpleInstallResponse:
    require_role(principal, {"admin", "engineer"})
    try:
        package = CapabilityRegistry(
            session,
            principal.organization_id,
        ).preflight_marketplace_package(
            manifest=_simple_manifest(request),
            source_uri=request.source_uri,
            pinned_ref=request.pinned_ref,
            content={
                **request.content,
                "marketplace_install": {
                    "source": request.marketplace_source,
                    "item_id": request.marketplace_item_id,
                    "registry_metadata_only": True,
                },
            },
            created_by=principal.user_id,
        )
    except CapabilityResolutionError as exc:
        raise _bad_request_from_capability_error(exc) from exc
    session.commit()
    session.refresh(package)
    return _simple_install_response(
        package=package,
        staged_capability_id=package.id,
        next_step_label="Approve marketplace version",
    )


@router.post(
    "/capabilities/install/upload",
    response_model=CapabilitySimpleInstallResponse,
    status_code=201,
    summary="Install an uploaded capability package without manifest editing",
)
def install_uploaded_capability(
    request: CapabilitySimpleInstallRequest,
    session: DbSession,
    principal: Principal,
) -> CapabilitySimpleInstallResponse:
    require_role(principal, {"admin", "engineer"})
    try:
        package, attachment = CapabilityRegistry(
            session,
            principal.organization_id,
        ).install_uploaded_package(
            manifest=_simple_manifest(request),
            content=request.content,
            agent_id=request.agent_id,
            created_by=principal.user_id,
        )
    except CapabilityResolutionError as exc:
        raise _bad_request_from_capability_error(exc) from exc
    session.commit()
    session.refresh(package)
    return _simple_install_response(
        package=package,
        attachment=attachment,
        next_step_label="Open Agent attachment" if attachment else "Attach to Agent",
    )


@router.get(
    "/capabilities/dependency-preflight",
    summary="Report v1 capability product dependency and runtime preflight",
)
def capability_dependency_preflight() -> dict:
    settings = get_settings()
    feature_flags = sorted(
        flag.strip() for flag in settings.feature_flags.split(",") if flag.strip()
    )
    trusted_hosts = sorted(_trusted_hosts())
    sandbox_paths = {
        "bubblewrap": bool(shutil.which("bwrap")),
        "sandbox_exec": bool(shutil.which("sandbox-exec")),
        "docker": bool(shutil.which("docker")),
    }
    token_estimator = "tiktoken" if find_spec("tiktoken") else "conservative-fallback"
    provider_matrix = connector_provider_release_matrix()
    return {
        "required_v1": {
            "httpx": "available" if find_spec("httpx") else "missing",
            "jsonschema": (
                "draft-2020-12-validator-active"
                if Draft202012Validator.META_SCHEMA.get("$schema")
                == "https://json-schema.org/draft/2020-12/schema"
                else "missing"
            ),
            "sandbox_or_policy": "policy-bound-fallback",
            "dify_connector": provider_matrix.get("dify", {}).get("release_state", "missing"),
            "token_estimator": token_estimator,
        },
        "optional_v2": {
            "sigstore_python": "hidden-until-sbom_required_gate",
            "ragas": "hidden-until-ragas_ci_gate",
            "openapi_python_client": "optional-wrapper-generation",
            "squid": "hidden-until-networked-local-execution",
            "tanstack_react_table": "hidden-until-large-ref-virtualization",
        },
        "feature_flags": feature_flags,
        "trusted_hosts": trusted_hosts,
        "sandbox_paths": sandbox_paths,
        "mcp_remote_allowed_hosts": [
            host.strip()
            for host in settings.mcp_remote_allowed_hosts.split(",")
            if host.strip()
        ],
        "local_release_path": "no-container",
        "docker_private_smoke": "optional",
    }


@router.post(
    "/capabilities/packages/private",
    response_model=CapabilityPackageResponse,
    status_code=201,
    summary="Stage a private capability package without executing code",
)
def stage_private_capability_package(
    request: CapabilityPackageStageRequest,
    session: DbSession,
    principal: Principal,
) -> CapabilityPackageResponse:
    require_role(principal, {"admin", "engineer"})
    package = CapabilityRegistry(session, principal.organization_id).stage_private_package(
        manifest=request.manifest,
        content=request.content,
        created_by=principal.user_id,
    )
    session.commit()
    session.refresh(package)
    return CapabilityPackageResponse.model_validate(package)


@router.post(
    "/capabilities/packages/public",
    response_model=CapabilityPackageResponse,
    status_code=201,
    summary="Stage a public URL/Git capability package with trust controls",
)
def stage_public_capability_package(
    request: CapabilityPublicPackageStageRequest,
    session: DbSession,
    principal: Principal,
) -> CapabilityPackageResponse:
    require_role(principal, {"admin", "engineer"})
    try:
        package = CapabilityRegistry(session, principal.organization_id).stage_public_package(
            manifest=request.manifest,
            source_kind=request.source_kind,
            source_uri=request.source_uri,
            pinned_ref=request.pinned_ref,
            content=request.content,
            created_by=principal.user_id,
        )
    except CapabilityResolutionError as exc:
        raise _bad_request_from_capability_error(exc) from exc
    session.commit()
    session.refresh(package)
    return CapabilityPackageResponse.model_validate(package)


@router.post(
    "/capabilities/packages/{package_id}/approve",
    response_model=CapabilityPackageResponse,
    summary="Approve a staged capability package and create an immutable version",
)
def approve_capability_package(
    package_id: str,
    request: CapabilityPackageApproveRequest,
    session: DbSession,
    principal: Principal,
) -> CapabilityPackageResponse:
    require_role(principal, {"admin", "engineer"})
    try:
        package = CapabilityRegistry(session, principal.organization_id).approve_package(
            package_id=package_id,
            approved_by=principal.user_id,
        )
    except CapabilityResolutionError as exc:
        raise _bad_request_from_capability_error(exc) from exc
    package.audit_json = {
        **package.audit_json,
        "approval_reason": request.reason,
    }
    session.commit()
    session.refresh(package)
    return CapabilityPackageResponse.model_validate(package)


@router.post(
    "/capabilities/staged/{package_id}/enable",
    response_model=CapabilitySimpleInstallResponse,
    summary="Enable a staged public capability after validation",
)
def enable_staged_capability(
    package_id: str,
    request: CapabilityPackageApproveRequest,
    session: DbSession,
    principal: Principal,
) -> CapabilitySimpleInstallResponse:
    require_role(principal, {"admin", "engineer"})
    try:
        package = CapabilityRegistry(session, principal.organization_id).approve_package(
            package_id=package_id,
            approved_by=principal.user_id,
        )
    except CapabilityResolutionError as exc:
        raise _bad_request_from_capability_error(exc) from exc
    package.audit_json = {
        **package.audit_json,
        "enable_reason": request.reason,
    }
    session.commit()
    session.refresh(package)
    return _simple_install_response(
        package=package,
        next_step_label="Attach to Agent",
    )


@router.post(
    "/capabilities/packages/{package_id}/attachments",
    response_model=CapabilityPackageAttachResponse,
    status_code=201,
    summary="Attach an approved package capability to an Agent",
)
def attach_capability_package(
    package_id: str,
    request: CapabilityPackageAttachRequest,
    session: DbSession,
    principal: Principal,
) -> CapabilityPackageAttachResponse:
    require_role(principal, {"admin", "engineer"})
    try:
        attachment = CapabilityRegistry(
            session,
            principal.organization_id,
        ).attach_package_capability(
            package_id=package_id,
            agent_id=request.agent_id,
            attached_by=principal.user_id,
            enabled=request.enabled,
            priority=request.priority,
        )
    except CapabilityResolutionError as exc:
        raise _bad_request_from_capability_error(exc) from exc
    session.commit()
    return CapabilityPackageAttachResponse(
        attachment_id=attachment.id,
        agent_id=attachment.agent_id,
        capability_id=attachment.capability_id,
        capability_version_id=attachment.capability_version_id,
        enabled=attachment.enabled,
        priority=attachment.priority,
    )
@router.post(
    "/capabilities/packages/{package_id}/rollback",
    response_model=CapabilityPackageResponse,
    summary="Rollback package current version without mutating historical versions",
)
def rollback_capability_package(
    package_id: str,
    request: CapabilityPackageRollbackRequest,
    session: DbSession,
    principal: Principal,
) -> CapabilityPackageResponse:
    require_role(principal, {"admin", "engineer"})
    try:
        package = CapabilityRegistry(session, principal.organization_id).rollback_package(
            package_id=package_id,
            capability_version_id=request.capability_version_id,
            updated_by=principal.user_id,
        )
    except CapabilityResolutionError as exc:
        raise _bad_request_from_capability_error(exc) from exc
    package.audit_json = {**package.audit_json, "rollback_reason": request.reason}
    session.commit()
    session.refresh(package)
    return CapabilityPackageResponse.model_validate(package)


@router.post(
    "/capabilities/packages/{package_id}/uninstall",
    response_model=CapabilityPackageResponse,
    summary="Uninstall a package when no enabled Agent attachments remain",
)
def uninstall_capability_package(
    package_id: str,
    session: DbSession,
    principal: Principal,
) -> CapabilityPackageResponse:
    require_role(principal, {"admin", "engineer"})
    try:
        package = CapabilityRegistry(session, principal.organization_id).uninstall_package(
            package_id=package_id,
            updated_by=principal.user_id,
        )
    except CapabilityResolutionError as exc:
        raise _bad_request_from_capability_error(exc) from exc
    session.commit()
    session.refresh(package)
    return CapabilityPackageResponse.model_validate(package)


@router.patch(
    "/capabilities/attachments/{attachment_id}",
    response_model=CapabilityPackageAttachResponse,
    summary="Enable or disable an Agent capability attachment",
)
def update_capability_attachment(
    attachment_id: str,
    request: CapabilityAttachmentUpdateRequest,
    session: DbSession,
    principal: Principal,
) -> CapabilityPackageAttachResponse:
    require_role(principal, {"admin", "engineer"})
    try:
        attachment = CapabilityRegistry(session, principal.organization_id).set_attachment_enabled(
            attachment_id=attachment_id,
            enabled=request.enabled,
        )
    except CapabilityResolutionError as exc:
        raise _bad_request_from_capability_error(exc) from exc
    session.commit()
    return CapabilityPackageAttachResponse(
        attachment_id=attachment.id,
        agent_id=attachment.agent_id,
        capability_id=attachment.capability_id,
        capability_version_id=attachment.capability_version_id,
        enabled=attachment.enabled,
        priority=attachment.priority,
    )


@router.get(
    "/capabilities/runtime-configs",
    response_model=CapabilityRuntimeConfigPage,
    summary="List installed MCP runtime configuration records",
)
def list_runtime_configs(
    session: DbSession,
    principal: Principal,
    agent_id: str = "default",
) -> CapabilityRuntimeConfigPage:
    require_role(principal, {"admin", "engineer"})
    ensure_default_agents(session, principal.organization_id)
    session.commit()
    try:
        records = CapabilityRegistry(
            session,
            principal.organization_id,
        ).list_runtime_configs(agent_id)
    except CapabilityResolutionError as exc:
        raise _bad_request_from_capability_error(exc) from exc
    return CapabilityRuntimeConfigPage(
        items=[
            _runtime_config_response(
                record,
                session=session,
                organization_id=principal.organization_id,
            )
            for record in records
        ]
    )


@router.get(
    "/capabilities/runtime-config",
    response_model=CapabilityRuntimeConfigResponse,
    summary="Get installed MCP runtime configuration",
)
def get_runtime_config(
    session: DbSession,
    principal: Principal,
    agent_id: str,
    tool_name: str,
) -> CapabilityRuntimeConfigResponse:
    require_role(principal, {"admin", "engineer"})
    ensure_default_agents(session, principal.organization_id)
    session.commit()
    try:
        record = CapabilityRegistry(
            session,
            principal.organization_id,
        ).runtime_config_for_tool(agent_id=agent_id, tool_name=tool_name)
    except CapabilityResolutionError as exc:
        raise _bad_request_from_capability_error(exc) from exc
    return _runtime_config_response(
        record,
        session=session,
        organization_id=principal.organization_id,
    )


@router.patch(
    "/capabilities/runtime-config",
    response_model=CapabilityRuntimeConfigResponse,
    summary="Save installed MCP runtime configuration",
)
def update_runtime_config(
    request: CapabilityRuntimeConfigUpdateRequest,
    session: DbSession,
    principal: Principal,
) -> CapabilityRuntimeConfigResponse:
    require_role(principal, {"admin", "engineer"})
    ensure_default_agents(session, principal.organization_id)
    session.commit()
    transport = request.transport
    endpoint_url = request.endpoint_url.strip() if isinstance(request.endpoint_url, str) else None
    command = request.command.strip() if isinstance(request.command, str) else None
    secret_ref = (
        request.secret_ref.strip()
        if isinstance(request.secret_ref, str) and request.secret_ref.strip()
        else None
    )
    secret_value = (
        request.secret_value.strip()
        if isinstance(request.secret_value, str) and request.secret_value.strip()
        else None
    )
    if secret_value and not secret_ref:
        secret_ref = _default_mcp_secret_ref(request.agent_id, request.tool_name)
    errors = _runtime_endpoint_errors(
        transport=transport,
        endpoint_url=endpoint_url,
        command=command,
    )
    if transport == "stdio":
        errors.extend(_runtime_arg_errors(request.args))
    if secret_ref and secret_ref_looks_like_raw_secret(secret_ref):
        errors.append("secret_ref must reference a server-side secret, not a raw API key")
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))
    if secret_value and secret_ref:
        try:
            store_connector_secret_ref(
                session,
                organization_id=principal.organization_id,
                actor_id=principal.user_id,
                secret_ref=secret_ref,
                provider=request.tool_name,
                secret_value=secret_value,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    runtime = {
        "transport": transport,
        "endpoint_url": endpoint_url,
        "command": command,
        "args": [str(item)[:200] for item in request.args[:20]],
        "timeout_seconds": request.timeout_seconds,
    }
    try:
        record = CapabilityRegistry(
            session,
            principal.organization_id,
        ).update_runtime_config(
            agent_id=request.agent_id,
            tool_name=request.tool_name,
            runtime=runtime,
            secret_ref=secret_ref,
            updated_by=principal.user_id,
        )
    except CapabilityResolutionError as exc:
        raise _bad_request_from_capability_error(exc) from exc
    session.commit()
    return _runtime_config_response(
        record,
        session=session,
        organization_id=principal.organization_id,
    )


@router.post(
    "/capabilities/test-invoke",
    response_model=ToolExecuteResponse,
    status_code=202,
    summary="Invoke an attached capability through an Agent-scoped test run",
)
def test_invoke_capability(
    request: CapabilityTestInvocationRequest,
    session: DbSession,
    principal: Principal,
) -> ToolExecuteResponse:
    require_role(principal, {"admin", "engineer"})
    task = Task(
        organization_id=principal.organization_id,
        agent_id=request.agent_id,
        created_by=principal.user_id,
        title=f"Capability test: {request.tool_name}",
        goal=f"Test invoke capability {request.tool_name}",
        status="RUNNING",
        model_provider="system",
        model_name="capability-registry",
        max_runtime_seconds=60,
        max_subagents=0,
        enable_sandbox=True,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    session.add(task)
    session.flush()
    capability_registry = CapabilityRegistry(session, principal.organization_id)
    execution = ToolRunner(
        session=session,
        agent_id=request.agent_id,
        capability_registry=capability_registry,
    ).execute(
        task_id=task.id,
        tool_name=request.tool_name,
        input_json=request.input_json,
        roles=principal.roles,
    )
    task.status = "COMPLETED" if execution.tool_call.status == "SUCCESS" else "FAILED"
    task.capability_snapshot_json = execution.tool_call.capability_snapshot_json
    task.completed_at = utc_now()
    task.updated_at = utc_now()
    session.commit()
    session.refresh(execution.tool_call)
    return ToolExecuteResponse(
        tool_call=_to_tool_call_response(execution.tool_call),
        allowed=execution.allowed,
        output=execution.output,
    )
