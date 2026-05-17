from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.schemas import (
    CapabilityAdminValidationRequest,
    CapabilityAdminValidationResponse,
    CapabilityTestInvocationRequest,
    ToolExecuteResponse,
    ToolMetadataResponse,
    ToolRegistryResponse,
)
from app.api.tasks import _to_tool_call_response
from app.db.models import Task, utc_now
from app.db.session import get_db_session
from app.security.auth import Principal, require_role
from app.tools.capabilities import CapabilityRegistry
from app.tools.registry import ToolRegistry
from app.tools.runner import ToolRunner

router = APIRouter(prefix="/tools", tags=["tools"])
DbSession = Annotated[Session, Depends(get_db_session)]


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
        enable_sandbox=False,
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
