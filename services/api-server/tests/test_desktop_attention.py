from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, Task, Team, TeamAgent, TeamGoal, TeamTask, ToolApproval, ToolCall
from app.db.session import get_db_session
from app.main import app
from app.security.auth import AuthenticatedPrincipal, get_current_principal


@pytest.fixture
def attention_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine)
    session = testing_session()

    def override_get_db():
        yield session

    def override_principal():
        return AuthenticatedPrincipal(
            user_id="user-a",
            organization_id="org-a",
            roles={"admin"},
            role="admin",
            permissions=set(),
            auth_type="jwt",
            api_key_id=None,
        )

    app.dependency_overrides[get_db_session] = override_get_db
    app.dependency_overrides[get_current_principal] = override_principal
    yield session
    session.close()
    app.dependency_overrides.clear()


def add_task(
    session: Session,
    *,
    task_id: str,
    organization_id: str,
    status: str,
    updated_at: datetime,
) -> Task:
    task = Task(
        id=task_id,
        organization_id=organization_id,
        created_by="user-a",
        title=f"Task {task_id}",
        goal=f"Goal {task_id}",
        status=status,
        model_provider="default",
        model_name="default",
        created_at=updated_at - timedelta(hours=1),
        updated_at=updated_at,
    )
    session.add(task)
    return task


def add_pending_approval(
    session: Session,
    *,
    task: Task,
    approval_id: str,
    created_at: datetime,
) -> None:
    tool_call = ToolCall(
        id=f"tool-{approval_id}",
        task_id=task.id,
        tool_name="run_shell",
        status="WAITING_APPROVAL",
        risk_level="high",
        input_json={"command": "pytest"},
        created_at=created_at,
    )
    session.add(tool_call)
    session.add(
        ToolApproval(
            id=approval_id,
            task_id=task.id,
            tool_call_id=tool_call.id,
            organization_id=task.organization_id,
            requested_by="agent",
            status="PENDING",
            risk_level="high",
            reason="Command requires review",
            request_json={"input_json": {"command": "pytest"}},
            created_at=created_at,
        )
    )


def test_attention_projects_server_owned_items_and_isolates_organization(attention_db: Session):
    now = datetime.now(UTC)
    approval_task = add_task(
        attention_db,
        task_id="approval-task",
        organization_id="org-a",
        status="WAITING_APPROVAL",
        updated_at=now,
    )
    add_pending_approval(
        attention_db,
        task=approval_task,
        approval_id="approval-a",
        created_at=now,
    )
    add_task(
        attention_db,
        task_id="failed-task",
        organization_id="org-a",
        status="FAILED",
        updated_at=now - timedelta(minutes=1),
    )
    foreign_task = add_task(
        attention_db,
        task_id="foreign-task",
        organization_id="org-b",
        status="WAITING_APPROVAL",
        updated_at=now + timedelta(minutes=1),
    )
    add_pending_approval(
        attention_db,
        task=foreign_task,
        approval_id="approval-foreign",
        created_at=now + timedelta(minutes=1),
    )

    team = Team(
        id="team-a",
        organization_id="org-a",
        name="Team A",
        status="ACTIVE",
        created_by="user-a",
        updated_at=now,
    )
    attention_db.add(team)
    attention_db.add(
        TeamGoal(
            id="goal-a",
            team_id=team.id,
            organization_id="org-a",
            status="blocked",
            objective="Ship safely",
            non_goals_json=[],
            acceptance_criteria_json=[],
            supervision_policy_json={},
            correction_budget_json={},
            progress_json={},
            supervisor_state_json={},
            created_at=now - timedelta(hours=2),
            updated_at=now - timedelta(minutes=2),
        )
    )
    attention_db.add(
        TeamAgent(
            id="team-agent-a",
            team_id=team.id,
            organization_id="org-a",
            slot_id="reviewer",
            agent_id="default",
            role="teammate",
            agent_name="Reviewer",
            status="failed",
            updated_at=now - timedelta(minutes=3),
        )
    )
    attention_db.add(
        TeamTask(
            id="team-task-a",
            team_id=team.id,
            organization_id="org-a",
            subject="Review release",
            status="pending",
            blocked_by_json=["missing-evidence"],
            created_at=now - timedelta(hours=3),
            updated_at=now - timedelta(minutes=4),
        )
    )
    attention_db.commit()

    response = TestClient(app).get("/api/desktop/attention")

    assert response.status_code == 200
    data = response.json()
    assert data["counts"] == {"total": 5, "approvals": 1, "runs": 1, "teams": 3}
    assert [item["kind"] for item in data["items"]] == [
        "tool_approval",
        "run_failed",
        "team_goal_blocked",
        "team_agent_failed",
        "team_task_blocked",
    ]
    assert data["items"][0] == {
        "id": "approval:approval-a",
        "category": "approvals",
        "kind": "tool_approval",
        "severity": "critical",
        "title": "Task approval-task",
        "description": "Command requires review",
        "status": "PENDING",
        "occurred_at": now.isoformat().replace("+00:00", "Z"),
        "target_path": "/runs/approval-task",
        "task_id": "approval-task",
        "team_id": None,
        "approval_id": "approval-a",
        "tool_name": "run_shell",
        "risk_level": "high",
        "actions": ["approve", "reject", "open"],
    }
    assert all("foreign" not in item["id"] for item in data["items"])


def test_attention_avoids_duplicate_waiting_run_and_applies_global_limit(attention_db: Session):
    now = datetime.now(UTC)
    approval_task = add_task(
        attention_db,
        task_id="waiting-with-approval",
        organization_id="org-a",
        status="WAITING_APPROVAL",
        updated_at=now,
    )
    add_pending_approval(
        attention_db,
        task=approval_task,
        approval_id="approval-limit",
        created_at=now,
    )
    add_task(
        attention_db,
        task_id="failed-newest",
        organization_id="org-a",
        status="FAILED",
        updated_at=now - timedelta(minutes=1),
    )
    add_task(
        attention_db,
        task_id="waiting-without-approval",
        organization_id="org-a",
        status="WAITING_APPROVAL",
        updated_at=now - timedelta(minutes=2),
    )
    attention_db.commit()

    response = TestClient(app).get("/api/desktop/attention", params={"limit": 2})

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["truncated"] is True
    assert [item["kind"] for item in data["items"]] == ["tool_approval", "run_failed"]
    assert sum(item["task_id"] == "waiting-with-approval" for item in data["items"]) == 1


def test_attention_returns_an_empty_projection(attention_db: Session):
    response = TestClient(app).get("/api/desktop/attention")

    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["counts"] == {"total": 0, "approvals": 0, "runs": 0, "teams": 0}
    assert data["truncated"] is False


def test_attention_limits_approval_actions_for_non_admin(attention_db: Session):
    now = datetime.now(UTC)
    task = add_task(
        attention_db,
        task_id="member-approval-task",
        organization_id="org-a",
        status="WAITING_APPROVAL",
        updated_at=now,
    )
    add_pending_approval(
        attention_db,
        task=task,
        approval_id="member-approval",
        created_at=now,
    )
    attention_db.commit()

    def override_member_principal():
        return AuthenticatedPrincipal(
            user_id="user-a",
            organization_id="org-a",
            roles={"member"},
            role="member",
            permissions=set(),
            auth_type="jwt",
            api_key_id=None,
        )

    app.dependency_overrides[get_current_principal] = override_member_principal
    response = TestClient(app).get("/api/desktop/attention")

    assert response.status_code == 200
    assert response.json()["items"][0]["actions"] == ["open"]


def test_attention_requires_authentication():
    app.dependency_overrides.clear()
    response = TestClient(app).get("/api/desktop/attention")
    assert response.status_code == 401
