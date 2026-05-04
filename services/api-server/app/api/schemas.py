from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    model_provider: str
    model_name: str
    max_runtime_seconds: int = 1800
    max_subagents: int = 5
    enable_sandbox: bool = True
    enable_network: bool = False


class TaskResponse(BaseModel):
    id: str
    title: str
    goal: str
    status: str
    model_provider: str
    model_name: str
    max_runtime_seconds: int
    max_subagents: int
    enable_sandbox: bool
    enable_network: bool
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class TaskPage(BaseModel):
    items: list[TaskResponse]
    next_cursor: str | None = None


class EventResponse(BaseModel):
    id: str
    task_id: str
    agent_run_id: str | None
    sequence: int
    event_type: str
    payload_json: dict
    actor_type: str
    actor_id: str | None
    trace_id: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EventPage(BaseModel):
    items: list[EventResponse]
    next_cursor: str | None = None


class SubagentResponse(BaseModel):
    id: str
    task_id: str
    parent_agent_id: str | None
    agent_type: str
    status: str
    context_json: dict
    started_at: datetime | None
    completed_at: datetime | None
    timeout_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class SubagentPage(BaseModel):
    items: list[SubagentResponse]
    next_cursor: str | None = None
