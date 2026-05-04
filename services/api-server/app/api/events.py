import json
import time
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.schemas import EventPage
from app.api.tasks import get_owned_task
from app.db.session import get_db_session
from app.events.event_store import EventStore
from app.security.auth import Principal

router = APIRouter(prefix="/tasks/{task_id}/events", tags=["events"])
DbSession = Annotated[Session, Depends(get_db_session)]


@router.get("", response_model=EventPage)
def list_task_events(
    task_id: str,
    session: DbSession,
    principal: Principal,
    after_sequence: Annotated[int | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> EventPage:
    get_owned_task(task_id, session, principal.organization_id)
    events = EventStore(session).list_by_task(
        task_id=task_id,
        after_sequence=after_sequence,
        limit=limit,
    )
    return EventPage(items=events)


@router.get("/stream")
def stream_task_events(
    request: Request,
    task_id: str,
    session: DbSession,
    principal: Principal,
    after_sequence: Annotated[int | None, Query()] = None,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    get_owned_task(task_id, session, principal.organization_id)

    def starting_after_sequence() -> int | None:
        if after_sequence is not None:
            return after_sequence
        if last_event_id is None:
            return None
        try:
            return int(last_event_id)
        except ValueError:
            return None

    def event_payload(event) -> dict:
        return {
            "id": event.id,
            "task_id": event.task_id,
            "agent_run_id": event.agent_run_id,
            "sequence": event.sequence,
            "event_type": event.event_type,
            "payload_json": event.payload_json,
            "actor_type": event.actor_type,
            "actor_id": event.actor_id,
            "trace_id": event.trace_id,
            "created_at": event.created_at.isoformat(),
        }

    def event_iterator() -> Iterator[str]:
        current_sequence = starting_after_sequence()
        idle_polls = 0
        while True:
            events = EventStore(session).list_by_task(
                task_id=task_id,
                after_sequence=current_sequence,
                limit=100,
            )
            if events:
                idle_polls = 0
                for event in events:
                    current_sequence = event.sequence
                    yield (
                        f"id: {event.sequence}\n"
                        f"data: {json.dumps(event_payload(event))}\n\n"
                    )
                continue

            yield ": heartbeat\n\n"
            idle_polls += 1
            if request.query_params.get("once") == "true" and idle_polls >= 1:
                break
            time.sleep(1)

    return StreamingResponse(event_iterator(), media_type="text/event-stream")
