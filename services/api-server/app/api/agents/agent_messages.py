"""Agent compatibility session message endpoints."""

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
    "/sessions/{session_id}/messages",
    response_model=AgentMessagePage,
    summary="查询 Agent 会话消息",
)
def list_agent_messages(
    session_id: str,
    session: DbSession,
    principal: Principal,
) -> AgentMessagePage:
    require_role(principal, {"admin", "engineer", "operator"})
    agent_session = _owned_session(session_id=session_id, session=session, principal=principal)
    messages = list(
        session.execute(
            select(AgentMessage)
            .where(AgentMessage.session_id == agent_session.id)
            .order_by(AgentMessage.created_at.asc(), AgentMessage.id.asc())
        ).scalars()
    )
    return AgentMessagePage(items=messages)


@router.post(
    "/sessions/{session_id}/messages",
    response_model=AgentChatResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
    summary="内部兼容：发送 Agent 会话消息",
)
def send_agent_message(
    session_id: str,
    request: AgentChatRequest,
    session: DbSession,
    principal: Principal,
) -> AgentChatResponse:
    require_role(principal, {"admin", "engineer"})
    agent_session = _owned_session(session_id=session_id, session=session, principal=principal)
    now = utc_now()
    user_message = AgentMessage(
        session_id=agent_session.id,
        agent_id=agent_session.agent_id,
        role="user",
        content=request.content,
        metadata_json={},
        created_at=now,
    )
    session.add(user_message)
    session.flush()
    assistant_message = AgentMessage(
        session_id=agent_session.id,
        agent_id=agent_session.agent_id,
        role="assistant",
        content=_chat_reply(agent_id=agent_session.agent_id, content=request.content),
        metadata_json={"mode": "chat", "agent_id": agent_session.agent_id},
        created_at=utc_now(),
    )
    agent_session.updated_at = now
    session.add(assistant_message)
    session.commit()
    session.refresh(agent_session)
    session.refresh(user_message)
    session.refresh(assistant_message)
    return AgentChatResponse(
        session=agent_session,
        messages=[user_message, assistant_message],
    )
