import shutil
from importlib.util import find_spec
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from jsonschema import Draft202012Validator
from sqlalchemy.orm import Session

from app.api.schemas import (
    CapabilityAdminValidationRequest,
    CapabilityAdminValidationResponse,
    CapabilityAttachmentUpdateRequest,
    CapabilityPackageApproveRequest,
    CapabilityPackageAttachRequest,
    CapabilityPackageAttachResponse,
    CapabilityPackagePage,
    CapabilityPackageResponse,
    CapabilityPackageRollbackRequest,
    CapabilityPackageStageRequest,
    CapabilityPublicPackageStageRequest,
    CapabilitySimpleInstallRequest,
    CapabilitySimpleInstallResponse,
    CapabilityTestInvocationRequest,
    ToolExecuteResponse,
    ToolMetadataResponse,
    ToolRegistryResponse,
)
from app.api.tasks import _to_tool_call_response
from app.core.config import get_settings
from app.db.models import Task, utc_now
from app.db.session import get_db_session
from app.knowledge_connectors import connector_provider_release_matrix
from app.security.auth import Principal, require_role
from app.tools.capabilities import CapabilityRegistry, CapabilityResolutionError
from app.tools.registry import ToolRegistry
from app.tools.runner import ToolRunner

router = APIRouter(prefix="/tools", tags=["tools"])
DbSession = Annotated[Session, Depends(get_db_session)]


def _bad_request_from_capability_error(exc: CapabilityResolutionError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get(
    "/registry",
    response_model=ToolRegistryResponse,
    summary="查询 Tool Registry",
    description="返回内置工具和 MCP-shaped 工具的统一注册表、风险、权限和 schema。",
)
def get_tool_registry(_: DbSession, principal: Principal) -> ToolRegistryResponse:
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
