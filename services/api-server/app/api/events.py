import json
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.schemas import EventPage
from app.db.session import get_db_session
from app.events.event_store import EventStore

router = APIRouter(prefix="/tasks/{task_id}/events", tags=["events"])
DbSession = Annotated[Session, Depends(get_db_session)]


@router.get("", response_model=EventPage)
def list_task_events(
    task_id: str,
    session: DbSession,
    after_sequence: Annotated[int | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> EventPage:
    events = EventStore(session).list_by_task(
        task_id=task_id,
        after_sequence=after_sequence,
        limit=limit,
    )
    return EventPage(items=events)


@router.get("/stream")
def stream_task_events(
    task_id: str,
    session: DbSession,
    after_sequence: Annotated[int | None, Query()] = None,
) -> StreamingResponse:
    def event_iterator() -> Iterator[str]:
        events = EventStore(session).list_by_task(
            task_id=task_id,
            after_sequence=after_sequence,
            limit=100,
        )
        for event in events:
            payload = {
                "id": event.id,
                "task_id": event.task_id,
                "sequence": event.sequence,
                "event_type": event.event_type,
                "payload_json": event.payload_json,
                "created_at": event.created_at.isoformat(),
            }
            yield (
                f"id: {event.sequence}\n"
                f"event: {event.event_type}\n"
                f"data: {json.dumps(payload)}\n\n"
            )

    return StreamingResponse(event_iterator(), media_type="text/event-stream")
