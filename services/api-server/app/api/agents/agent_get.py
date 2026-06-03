"""Agent detail endpoint registered after single-segment collection routes."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *
from ._capability_helpers import *
from ._grounding_helpers import *
from ._knowledge_helpers import *
from ._plan_helpers import *
from ._session_helpers import *
from ._tool_helpers import *
from ._workspace_chat_helpers import *
from ._workspace_response_helpers import *

@router.get(
    "/{agent_id}",
    response_model=AgentResponse,
    summary="查询 Agent 详情",
    description="返回指定具名 Agent 的模型、工具、角色和路由标签。",
)
def get_agent(agent_id: str, session: DbSession, principal: Principal) -> AgentResponse:
    require_role(principal, {"admin", "engineer", "operator"})
    agent = _get_agent(agent_id=agent_id, session=session, principal=principal)
    return _agent_response(agent, session=session)
