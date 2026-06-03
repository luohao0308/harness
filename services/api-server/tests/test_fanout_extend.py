from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agents.specialists import ensure_system_specialists
from app.agents.subagent_manager import SubagentManager
from app.db.models import SubagentSpecialist
from app.events.event_store import EventStore
from app.main import app
from tests.conftest import AUTH_HEADERS
from tests.test_subagents import create_task


def test_fanout_extend_adds_dynamic_specialist_and_event(db_session: Session) -> None:
    ensure_system_specialists(db_session)
    task = create_task(db_session)
    specialists = list(
        db_session.query(SubagentSpecialist)
        .filter(SubagentSpecialist.slug.in_(["code-reviewer", "researcher", "safety-checker"]))
        .all()
    )
    by_slug = {specialist.slug: specialist for specialist in specialists}
    batch_id, runs = SubagentManager(db_session).spawn_fanout(
        task=task,
        assignment={"step_key": "review", "description": "review release"},
        specialists=[by_slug["code-reviewer"], by_slug["researcher"]],
        enqueue=False,
    )
    runs[0].status = "RUNNING"
    runs[1].status = "RUNNING"
    db_session.commit()

    response = TestClient(app).post(
        f"/api/subagents/{runs[0].id}/fanout/extend",
        headers=AUTH_HEADERS,
        json={
            "additional_specialist_slugs": ["safety-checker"],
            "reason": "researcher_found_security_topic",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["fanout_batch_id"] == batch_id
    assert body["added_count"] == 1
    added = body["agent_runs"][0]
    assert added["dynamic_fanout_origin"] == batch_id
    assert added["dynamic_fanout_requested_by"] == runs[0].id
    assert added["dynamic_fanout_reason"] == "researcher_found_security_topic"
    assert added["fanout_total"] == 3
    events = EventStore(db_session).list_by_task(task_id=task.id)
    assert any(event.event_type == "FANOUT_EXTENDED" for event in events)


def test_fanout_extend_rejects_completed_batch(db_session: Session) -> None:
    ensure_system_specialists(db_session)
    task = create_task(db_session)
    specialists = list(
        db_session.query(SubagentSpecialist)
        .filter(SubagentSpecialist.slug.in_(["code-reviewer", "researcher"]))
        .all()
    )
    _batch_id, runs = SubagentManager(db_session).spawn_fanout(
        task=task,
        assignment={"step_key": "review"},
        specialists=specialists,
        enqueue=False,
    )
    for run in runs:
        run.status = "SUCCESS"
    db_session.commit()

    response = TestClient(app).post(
        f"/api/subagents/{runs[0].id}/fanout/extend",
        headers=AUTH_HEADERS,
        json={"additional_specialist_slugs": ["safety-checker"], "reason": "late"},
    )

    assert response.status_code == 409
