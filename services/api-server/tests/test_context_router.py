from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AgentEvent,
    ExecutionPlan,
    ModelCall,
    SystemSetting,
    Task,
    ToolCall,
    utc_now,
)
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.main import app
from tests.conftest import AUTH_HEADERS


def create_task(db_session: Session, *, goal: str, model_name: str = "default") -> Task:
    task = Task(
        organization_id="dev-org",
        created_by="dev-engineer",
        title="Context Router",
        goal=goal,
        status="RUNNING",
        model_provider="default",
        model_name=model_name,
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(task)
    db_session.flush()
    return task


def add_model_router_settings(db_session: Session) -> None:
    db_session.add(
        SystemSetting(
            organization_id="dev-org",
            key="settings.models",
            value_json={
                "default_provider": "openai-compatible",
                "default_model": "general-model",
                "providers": [{"name": "openai-compatible", "status": "healthy"}],
                "rate_limits": {"rpm": 600, "tpm": 120000},
                "circuit_breaker": {"failure_threshold": 3, "cooldown_seconds": 60},
                "model_router": {
                    "coding": {
                        "provider": "openai-compatible",
                        "model": "code-strong",
                        "model_class": "strong-coding",
                    },
                    "grading": {
                        "provider": "openai-compatible",
                        "model": "grade-stable",
                        "model_class": "stable-grading",
                    },
                },
            },
            updated_by="test",
            updated_at=utc_now(),
        )
    )
    db_session.flush()


def test_get_task_context_builds_memory_and_routes_coding_model(db_session: Session) -> None:
    add_model_router_settings(db_session)
    task = create_task(db_session, goal="Fix a React API bug and add pytest coverage")
    db_session.add(
        ExecutionPlan(
            task_id=task.id,
            version=1,
            status="GENERATED",
            plan_json={
                "summary": "Coding fix",
                "steps": [
                    {
                        "key": "inspect",
                        "description": "Inspect failing API",
                        "execution_mode": "sync",
                        "risk_level": "low",
                    }
                ],
            },
            created_at=utc_now(),
        )
    )
    db_session.add(
        ModelCall(
            task_id=task.id,
            model_provider="openai-compatible",
            model_name="general-model",
            status="SUCCESS",
            prompt_tokens=10,
            completion_tokens=4,
            duration_ms=25,
            request_json={},
            response_json={},
            created_at=utc_now(),
        )
    )
    db_session.add(
        ToolCall(
            task_id=task.id,
            tool_name="mcp_context_search",
            status="SUCCESS",
            risk_level="low",
            requires_sandbox=False,
            duration_ms=12,
            input_json={"query": "React API bug"},
            output_json={"results": [{"title": "known issue"}]},
            created_at=utc_now(),
        )
    )
    EventStore(db_session).append(
        task_id=task.id,
        event_type=EventType.TASK_STARTED,
        payload_json={"task_id": task.id},
    )
    EventStore(db_session).append(
        task_id=task.id,
        event_type=EventType.AGENT_SELECTED,
        payload_json={"agent_id": "coder", "reasoning": "coding task"},
    )
    db_session.commit()
    event_count = db_session.execute(select(AgentEvent)).scalars().all()

    response = TestClient(app).get(f"/api/tasks/{task.id}/context", headers=AUTH_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["working_memory"]["step_count"] == 1
    assert payload["rag_context"]["retrieval_count"] == 1
    assert payload["context_compression"]["model_call_count"] == 1
    assert payload["model_routing"]["task_type"] == "coding"
    assert payload["model_routing"]["selected_model"] == "code-strong"
    assert payload["latest_agent_router"]["payload_json"]["agent_id"] == "coder"
    assert len(db_session.execute(select(AgentEvent)).scalars().all()) == len(event_count)


def test_route_task_context_appends_traceable_events(db_session: Session) -> None:
    add_model_router_settings(db_session)
    task = create_task(db_session, goal="Run eval regression and grade the agent trace")
    db_session.commit()

    response = TestClient(app).post(
        f"/api/tasks/{task.id}/context/route",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["model_routing"]["task_type"] == "grading"
    assert payload["model_routing"]["selected_model"] == "grade-stable"
    events = EventStore(db_session).list_by_task(task_id=task.id)
    assert [event.event_type for event in events] == [
        "CONTEXT_COMPRESSED",
        "MODEL_ROUTED",
    ]
    assert events[1].payload_json["model_name"] == "grade-stable"
