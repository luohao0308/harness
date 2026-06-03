"""Agent lookup, session lookup, and compatibility reply helpers."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *

def _get_agent(*, agent_id: str, session: Session, principal: Principal) -> Agent:
    ensure_default_agents(session, principal.organization_id)
    session.commit()
    agent = session.execute(select(Agent).where(Agent.id == agent_id)).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent 未找到")
    return agent


def _owned_session(
    *,
    session_id: str,
    session: Session,
    principal: Principal,
) -> AgentSession:
    agent_session = session.execute(
        select(AgentSession).where(
            AgentSession.id == session_id,
            AgentSession.organization_id == principal.organization_id,
        )
    ).scalar_one_or_none()
    if agent_session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent Session 未找到")
    return agent_session


def _chat_reply(*, agent_id: str, content: str) -> str:
    return (
        f"{agent_id} 已收到你的消息。"
        "当前会话端点仅作为内部兼容层；主工作台固定使用 Plan 模式。"
        f"消息摘要：{content[:80]}"
    )

__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
