from __future__ import annotations

import json
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, status
from fastapi.responses import StreamingResponse
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session, sessionmaker

from app.api.schemas import normalize_workspace_mode
from app.db.models import AgentMessage, Team, TeamAgent, TeamEvent, TeamMailboxMessage, TeamTask
from app.db.session import get_db_session
from app.security.auth import Principal, require_role
from app.teams.service import TEAM_TOOL_NAMES, TeamSessionService

router = APIRouter(prefix="/teams", tags=["teams"])
DbSession = Annotated[Session, Depends(get_db_session)]

_SSE_HEADERS: dict[str, str] = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


class TeamAgentSessionMessageResponse(BaseModel):
    id: str
    session_id: str
    agent_id: str
    role: str
    content: str
    metadata_json: dict = Field(default_factory=dict)
    created_at: str | None = None


class TeamAgentResponse(BaseModel):
    id: str
    team_id: str
    slot_id: str
    agent_id: str
    role: Literal["leader", "teammate"]
    agent_name: str
    status: Literal["pending", "idle", "active", "completed", "failed"]
    model_provider: str
    model_name: str
    conversation_id: str | None = None
    session_id: str | None = None
    session_messages: list[TeamAgentSessionMessageResponse] = Field(default_factory=list)
    metadata_json: dict = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class TeamMailboxMessageResponse(BaseModel):
    id: str
    team_id: str
    to_agent_slot_id: str
    from_agent_slot_id: str
    type: str
    content: str
    summary: str | None = None
    read: bool
    files_json: list = Field(default_factory=list)
    metadata_json: dict = Field(default_factory=dict)
    created_at: str | None = None


class TeamTaskResponse(BaseModel):
    id: str
    team_id: str
    subject: str
    description: str
    owner_slot_id: str | None = None
    status: Literal["pending", "in_progress", "completed", "deleted"]
    blocked_by_json: list[str] = Field(default_factory=list)
    blocks_json: list[str] = Field(default_factory=list)
    metadata_json: dict = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class TeamEventResponse(BaseModel):
    id: str
    team_id: str
    sequence: int
    event_type: str
    payload_json: dict
    actor_type: str
    actor_id: str | None = None
    created_at: str | None = None


class TeamResponse(BaseModel):
    id: str
    organization_id: str | None = None
    name: str
    status: str
    workspace: str
    workspace_mode: Literal["shared", "isolated"]
    leader_slot_id: str
    created_by: str | None = None
    agents: list[TeamAgentResponse] = Field(default_factory=list)
    messages: list[TeamMailboxMessageResponse] = Field(default_factory=list)
    tasks: list[TeamTaskResponse] = Field(default_factory=list)
    unread_counts: dict[str, int] = Field(default_factory=dict)
    team_tools: list[str] = Field(default_factory=lambda: sorted(TEAM_TOOL_NAMES))
    created_at: str | None = None
    updated_at: str | None = None

    model_config = ConfigDict(from_attributes=True)


class TeamPage(BaseModel):
    items: list[TeamResponse]
    next_cursor: str | None = None


class TeamSeedMessageRequest(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1)
    created_at: str | None = None
    metadata_json: dict = Field(default_factory=dict)


class TeamCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    workspace: str = Field(default="")
    workspace_mode: Literal["shared", "isolated"] = "shared"
    leader_agent_id: str = Field(default="default")
    leader_name: str = Field(default="Leader")
    seed_messages: list[TeamSeedMessageRequest] = Field(default_factory=list)


class TeamRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class TeamAgentCreateRequest(BaseModel):
    agent_id: str = Field(default="default")
    agent_name: str = Field(min_length=1, max_length=120)
    role: Literal["teammate"] = "teammate"
    model_provider: str | None = None
    model_name: str | None = None


class TeamAgentUpdateRequest(BaseModel):
    agent_name: str | None = Field(default=None, min_length=1, max_length=120)
    model_provider: str | None = None
    model_name: str | None = None


class TeamMessageCreateRequest(BaseModel):
    target: str = Field(default="leader", description="leader, team, or a concrete slot id")
    content: str = Field(min_length=1)
    from_agent_slot_id: str = Field(default="user")
    type: str = Field(default="message")
    summary: str | None = None
    files: list[str] = Field(default_factory=list)
    mode: Literal["chat", "markdown_plan", "plan", "goal"] = "chat"

    @field_validator("mode", mode="before")
    @classmethod
    def normalize_mode(cls, value: str) -> str:
        return normalize_workspace_mode(value)


class TeamTaskCreateRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=240)
    description: str = ""
    owner_slot_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("owner_slot_id", "ownerSlotId", "owner"),
    )
    blocked_by: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("blocked_by", "blockedBy", "blocked_by_json"),
    )

    model_config = ConfigDict(populate_by_name=True)


class TeamTaskUpdateRequest(BaseModel):
    status: Literal["pending", "in_progress", "completed", "deleted"] | None = None
    owner_slot_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("owner_slot_id", "ownerSlotId", "owner"),
    )
    description: str | None = None
    blocked_by: list[str] | None = Field(
        default=None,
        validation_alias=AliasChoices("blocked_by", "blockedBy", "blocked_by_json"),
    )

    model_config = ConfigDict(populate_by_name=True)


class TeamToolCallRequest(BaseModel):
    from_agent_slot_id: str | None = None
    args: dict = Field(default_factory=dict)


class TeamToolCallResponse(BaseModel):
    tool_name: str
    from_agent_slot_id: str | None = None
    result: str


def _service(session: Session, principal) -> TeamSessionService:
    return TeamSessionService(
        session=session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
    )


def _team_response(team: Team, service: TeamSessionService) -> TeamResponse:
    agents = sorted(
        team.agents,
        key=lambda agent: (0 if agent.role == "leader" else 1, agent.created_at, agent.id),
    )
    messages = sorted(team.messages, key=lambda message: (message.created_at, message.id))
    tasks = sorted(team.tasks, key=lambda task: (task.created_at, task.id))
    return TeamResponse(
        id=team.id,
        organization_id=team.organization_id,
        name=team.name,
        status=team.status,
        workspace=team.workspace,
        workspace_mode=team.workspace_mode,
        leader_slot_id=team.leader_slot_id,
        created_by=team.created_by,
        agents=[_agent_response(agent, service.session_messages(agent)) for agent in agents],
        messages=[_message_response(message) for message in messages],
        tasks=[_task_response(task) for task in tasks if task.status != "deleted"],
        unread_counts=service.unread_counts(messages),
        team_tools=sorted(TEAM_TOOL_NAMES),
        created_at=team.created_at.isoformat() if team.created_at else None,
        updated_at=team.updated_at.isoformat() if team.updated_at else None,
    )


def _agent_response(
    agent: TeamAgent,
    session_messages: list[AgentMessage] | None = None,
) -> TeamAgentResponse:
    metadata_json = dict(agent.metadata_json or {})
    wake_state = metadata_json.get("wake")
    status_value = agent.status
    if status_value == "active" and (
        not isinstance(wake_state, dict)
        or wake_state.get("in_progress") is not True
        or _has_completed_wake_turn(wake_state, session_messages or [])
    ):
        status_value = "idle"
        if isinstance(wake_state, dict) and wake_state.get("in_progress") is True:
            metadata_json["wake"] = {**wake_state, "in_progress": False}
    return TeamAgentResponse(
        id=agent.id,
        team_id=agent.team_id,
        slot_id=agent.slot_id,
        agent_id=agent.agent_id,
        role=agent.role,
        agent_name=agent.agent_name,
        status=status_value,
        model_provider=agent.model_provider,
        model_name=agent.model_name,
        conversation_id=agent.conversation_id,
        session_id=agent.session_id,
        session_messages=[
            _session_message_response(message) for message in (session_messages or [])
        ],
        metadata_json=metadata_json,
        created_at=agent.created_at.isoformat() if agent.created_at else None,
        updated_at=agent.updated_at.isoformat() if agent.updated_at else None,
    )


def _parse_iso_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _has_completed_wake_turn(wake_state: dict, session_messages: list[AgentMessage]) -> bool:
    if not session_messages:
        return False
    latest_message = session_messages[-1]
    if latest_message.role != "assistant":
        return False
    started_at = _parse_iso_datetime(wake_state.get("started_at"))
    if started_at is None:
        return True
    if latest_message.created_at is None:
        return False
    message_created_at = latest_message.created_at
    if message_created_at.tzinfo is None:
        message_created_at = message_created_at.replace(tzinfo=UTC)
    return message_created_at >= started_at


def _session_message_response(message: AgentMessage) -> TeamAgentSessionMessageResponse:
    return TeamAgentSessionMessageResponse(
        id=message.id,
        session_id=message.session_id,
        agent_id=message.agent_id,
        role=message.role,
        content=message.content,
        metadata_json=message.metadata_json,
        created_at=message.created_at.isoformat() if message.created_at else None,
    )


def _message_response(message: TeamMailboxMessage) -> TeamMailboxMessageResponse:
    return TeamMailboxMessageResponse(
        id=message.id,
        team_id=message.team_id,
        to_agent_slot_id=message.to_agent_slot_id,
        from_agent_slot_id=message.from_agent_slot_id,
        type=message.type,
        content=message.content,
        summary=message.summary,
        read=message.read,
        files_json=message.files_json,
        metadata_json=message.metadata_json,
        created_at=message.created_at.isoformat() if message.created_at else None,
    )


def _task_response(task: TeamTask) -> TeamTaskResponse:
    return TeamTaskResponse(
        id=task.id,
        team_id=task.team_id,
        subject=task.subject,
        description=task.description,
        owner_slot_id=task.owner_slot_id,
        status=task.status,
        blocked_by_json=task.blocked_by_json,
        blocks_json=task.blocks_json,
        metadata_json=task.metadata_json,
        created_at=task.created_at.isoformat() if task.created_at else None,
        updated_at=task.updated_at.isoformat() if task.updated_at else None,
    )


def _event_response(event: TeamEvent) -> TeamEventResponse:
    return TeamEventResponse(
        id=event.id,
        team_id=event.team_id,
        sequence=event.sequence,
        event_type=event.event_type,
        payload_json=event.payload_json,
        actor_type=event.actor_type,
        actor_id=event.actor_id,
        created_at=event.created_at.isoformat() if event.created_at else None,
    )


def _sse_event(event: TeamEventResponse) -> str:
    return (
        f"id: {event.sequence}\n"
        f"data: {json.dumps(event.model_dump(mode='json'), ensure_ascii=False)}\n\n"
    )


def _named_sse_event(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.get("", response_model=TeamPage)
def list_teams(session: DbSession, principal: Principal) -> TeamPage:
    require_role(principal, {"admin", "engineer", "operator"})
    service = _service(session, principal)
    return TeamPage(items=[_team_response(team, service) for team in service.list_teams()])


@router.post("", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
def create_team(
    request: TeamCreateRequest, session: DbSession, principal: Principal
) -> TeamResponse:
    require_role(principal, {"admin", "engineer"})
    service = _service(session, principal)
    team = service.create_team(
        name=request.name,
        workspace=request.workspace,
        workspace_mode=request.workspace_mode,
        leader_agent_id=request.leader_agent_id,
        leader_name=request.leader_name,
        seed_messages=[
            message.model_dump(mode="json") for message in request.seed_messages
        ],
    )
    session.commit()
    session.refresh(team)
    return _team_response(team, service)


@router.get("/{team_id}", response_model=TeamResponse)
def get_team(team_id: str, session: DbSession, principal: Principal) -> TeamResponse:
    require_role(principal, {"admin", "engineer", "operator"})
    service = _service(session, principal)
    return _team_response(service.get_team(team_id), service)


@router.patch("/{team_id}", response_model=TeamResponse)
def rename_team(
    team_id: str,
    request: TeamRenameRequest,
    session: DbSession,
    principal: Principal,
) -> TeamResponse:
    require_role(principal, {"admin", "engineer"})
    service = _service(session, principal)
    team = service.rename_team(team_id, request.name)
    session.commit()
    session.refresh(team)
    return _team_response(team, service)


@router.delete("/{team_id}", response_model=TeamResponse)
def archive_team(team_id: str, session: DbSession, principal: Principal) -> TeamResponse:
    require_role(principal, {"admin", "engineer"})
    service = _service(session, principal)
    team = service.archive_team(team_id)
    session.commit()
    session.refresh(team)
    return _team_response(team, service)


@router.post(
    "/{team_id}/agents", response_model=TeamAgentResponse, status_code=status.HTTP_201_CREATED
)
def add_team_agent(
    team_id: str,
    request: TeamAgentCreateRequest,
    session: DbSession,
    principal: Principal,
) -> TeamAgentResponse:
    require_role(principal, {"admin", "engineer"})
    service = _service(session, principal)
    agent = service.add_agent(
        team_id=team_id,
        agent_id=request.agent_id,
        agent_name=request.agent_name,
        role=request.role,
        model_provider=request.model_provider,
        model_name=request.model_name,
    )
    session.commit()
    session.refresh(agent)
    return _agent_response(agent)


@router.patch("/{team_id}/agents/{slot_id}", response_model=TeamAgentResponse)
def update_team_agent(
    team_id: str,
    slot_id: str,
    request: TeamAgentUpdateRequest,
    session: DbSession,
    principal: Principal,
) -> TeamAgentResponse:
    require_role(principal, {"admin", "engineer"})
    service = _service(session, principal)
    agent = service.update_agent(
        team_id=team_id,
        slot_id=slot_id,
        agent_name=request.agent_name,
        model_provider=request.model_provider,
        model_name=request.model_name,
    )
    session.commit()
    session.refresh(agent)
    return _agent_response(agent)


@router.delete("/{team_id}/agents/{slot_id}", response_model=TeamAgentResponse)
def remove_team_agent(
    team_id: str,
    slot_id: str,
    session: DbSession,
    principal: Principal,
) -> TeamAgentResponse:
    require_role(principal, {"admin", "engineer"})
    service = _service(session, principal)
    agent = service.remove_agent(team_id=team_id, slot_id=slot_id)
    response = _agent_response(agent)
    session.commit()
    return response


@router.post("/{team_id}/agents/{slot_id}/wake", response_model=TeamAgentResponse)
def wake_team_agent(
    team_id: str,
    slot_id: str,
    session: DbSession,
    principal: Principal,
) -> TeamAgentResponse:
    require_role(principal, {"admin", "engineer"})
    service = _service(session, principal)
    agent = service.wake_agent(team_id=team_id, slot_id=slot_id)
    session.commit()
    session.refresh(agent)
    return _agent_response(agent)


@router.post("/{team_id}/agents/{slot_id}/wake/cancel", response_model=TeamAgentResponse)
def cancel_team_agent_wake(
    team_id: str,
    slot_id: str,
    session: DbSession,
    principal: Principal,
) -> TeamAgentResponse:
    require_role(principal, {"admin", "engineer"})
    service = _service(session, principal)
    agent = service.cancel_agent_wake(team_id=team_id, slot_id=slot_id, reason="user_cancelled")
    session.commit()
    session.refresh(agent)
    return _agent_response(agent)


@router.post("/{team_id}/agents/{slot_id}/wake/stream")
def stream_wake_team_agent(
    team_id: str,
    slot_id: str,
    session: DbSession,
    principal: Principal,
) -> StreamingResponse:
    require_role(principal, {"admin", "engineer"})

    def iterator() -> Iterator[str]:
        service = _service(session, principal)
        stream = service.wake_agent_stream(team_id=team_id, slot_id=slot_id)
        try:
            for event in stream:
                event_type = str(event.get("type") or "message")
                payload = {key: value for key, value in event.items() if key != "type"}
                if event_type == "delta":
                    session.flush()
                elif event_type == "error":
                    session.commit()
                else:
                    session.commit()
                yield _named_sse_event(event_type, payload)
        except GeneratorExit:
            stream.close()
            session.commit()
            raise
        except Exception as exc:
            session.rollback()
            yield _named_sse_event("error", {"message": str(exc), "slot_id": slot_id})

    return StreamingResponse(iterator(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post(
    "/{team_id}/messages",
    response_model=TeamMailboxMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def send_team_message(
    team_id: str,
    request: TeamMessageCreateRequest,
    session: DbSession,
    principal: Principal,
) -> TeamMailboxMessageResponse:
    require_role(principal, {"admin", "engineer"})
    service = _service(session, principal)
    message = service.write_message(
        team_id=team_id,
        target=request.target,
        content=request.content,
        from_agent_slot_id=request.from_agent_slot_id,
        message_type=request.type,
        summary=request.summary,
        files=request.files,
        mode=request.mode,
        wake_recipient=False,
    )
    session.commit()
    session.refresh(message)
    return _message_response(message)


@router.post(
    "/{team_id}/agents/{slot_id}/mailbox/read", response_model=list[TeamMailboxMessageResponse]
)
def read_team_mailbox(
    team_id: str,
    slot_id: str,
    session: DbSession,
    principal: Principal,
) -> list[TeamMailboxMessageResponse]:
    require_role(principal, {"admin", "engineer"})
    service = _service(session, principal)
    messages = service.read_unread(team_id=team_id, slot_id=slot_id)
    session.commit()
    return [_message_response(message) for message in messages]


@router.post("/{team_id}/tools/{tool_name}", response_model=TeamToolCallResponse)
def call_team_tool(
    team_id: str,
    tool_name: str,
    request: TeamToolCallRequest,
    session: DbSession,
    principal: Principal,
) -> TeamToolCallResponse:
    require_role(principal, {"admin", "engineer"})
    service = _service(session, principal)
    result = service.call_tool(
        team_id=team_id,
        tool_name=tool_name,
        args=request.args,
        from_agent_slot_id=request.from_agent_slot_id,
    )
    session.commit()
    return TeamToolCallResponse(
        tool_name=tool_name,
        from_agent_slot_id=request.from_agent_slot_id,
        result=result,
    )


@router.get("/{team_id}/tasks", response_model=list[TeamTaskResponse])
def list_team_tasks(
    team_id: str, session: DbSession, principal: Principal
) -> list[TeamTaskResponse]:
    require_role(principal, {"admin", "engineer", "operator"})
    service = _service(session, principal)
    return [_task_response(task) for task in service.list_tasks(team_id)]


@router.post(
    "/{team_id}/tasks", response_model=TeamTaskResponse, status_code=status.HTTP_201_CREATED
)
def create_team_task(
    team_id: str,
    request: TeamTaskCreateRequest,
    session: DbSession,
    principal: Principal,
) -> TeamTaskResponse:
    require_role(principal, {"admin", "engineer"})
    service = _service(session, principal)
    task = service.create_task(
        team_id=team_id,
        subject=request.subject,
        description=request.description,
        owner_slot_id=request.owner_slot_id,
        blocked_by=request.blocked_by,
    )
    session.commit()
    session.refresh(task)
    return _task_response(task)


@router.patch("/{team_id}/tasks/{task_id}", response_model=TeamTaskResponse)
def update_team_task(
    team_id: str,
    task_id: str,
    request: TeamTaskUpdateRequest,
    session: DbSession,
    principal: Principal,
) -> TeamTaskResponse:
    require_role(principal, {"admin", "engineer"})
    service = _service(session, principal)
    task = service.update_task(
        team_id=team_id,
        task_id=task_id,
        status_value=request.status,
        owner_slot_id=(
            request.owner_slot_id if "owner_slot_id" in request.model_fields_set else None
        ),
        update_owner="owner_slot_id" in request.model_fields_set,
        description=request.description,
        blocked_by=request.blocked_by,
    )
    session.commit()
    session.refresh(task)
    return _task_response(task)


@router.get("/{team_id}/events", response_model=list[TeamEventResponse])
def list_team_events(
    team_id: str,
    session: DbSession,
    principal: Principal,
    after_sequence: int | None = Query(default=None, ge=0),
) -> list[TeamEventResponse]:
    require_role(principal, {"admin", "engineer", "operator"})
    service = _service(session, principal)
    return [
        _event_response(event)
        for event in service.list_events(team_id=team_id, after_sequence=after_sequence)
    ]


@router.get("/{team_id}/stream")
def stream_team_events(
    team_id: str,
    session: DbSession,
    principal: Principal,
    after_sequence: int | None = Query(default=None, ge=0),
    once: bool = Query(default=False),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    require_role(principal, {"admin", "engineer", "operator"})
    service = _service(session, principal)
    bind = session.get_bind()
    try:
        service.get_team(team_id)
    finally:
        session.close()
    poll_session_factory = sessionmaker(bind=bind, autoflush=False, autocommit=False)
    try:
        header_sequence = int(last_event_id) if last_event_id else None
    except ValueError:
        header_sequence = None
    start_after = after_sequence if after_sequence is not None else header_sequence

    def iterator() -> Iterator[str]:
        last_seen = start_after
        while True:
            with poll_session_factory() as poll_session:
                poll_service = _service(poll_session, principal)
                events = [
                    _event_response(event)
                    for event in poll_service.list_events(team_id=team_id, after_sequence=last_seen)
                ]
            if events:
                for event in events:
                    last_seen = event.sequence
                    yield _sse_event(event)
            elif once:
                yield ": heartbeat\n\n"
            if once:
                break
            time.sleep(2)

    return StreamingResponse(iterator(), media_type="text/event-stream", headers=_SSE_HEADERS)
