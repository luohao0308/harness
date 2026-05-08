from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.schemas import ToolMetadataResponse, ToolRegistryResponse
from app.db.session import get_db_session
from app.security.auth import Principal
from app.tools.registry import ToolRegistry

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
