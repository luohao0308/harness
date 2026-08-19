import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import (
    AdminAuditEvent,
    AgentEvent,
    Base,
    Task,
    ToolApproval,
    ToolCall,
)
from app.db.session import get_db_session
from app.events.event_types import EventType
from app.main import app
from app.security.auth import AuthenticatedPrincipal, get_current_principal


@pytest.fixture
def audit_context():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine)
    session = testing_session()
    principal_state = {
        "value": AuthenticatedPrincipal(
            user_id="user-a",
            organization_id="org-a",
            roles={"admin"},
            role="admin",
            permissions=set(),
            auth_type="jwt",
            api_key_id=None,
        )
    }

    def override_get_db():
        yield session

    def override_principal():
        return principal_state["value"]

    app.dependency_overrides[get_db_session] = override_get_db
    app.dependency_overrides[get_current_principal] = override_principal
    yield session, principal_state
    session.close()
    app.dependency_overrides.clear()


def _add_task(session: Session, task_id: str, organization_id: str = "org-a") -> Task:
    task = Task(
        id=task_id,
        organization_id=organization_id,
        created_by="user-a",
        title=f"Task {task_id}",
        goal="Review local changes",
        status="RUNNING",
        model_provider="default",
        model_name="default",
    )
    session.add(task)
    return task


def _add_approval(
    session: Session,
    approval_id: str,
    task_id: str,
    organization_id: str = "org-a",
) -> ToolApproval:
    tool_call = ToolCall(
        id=f"tool-{approval_id}",
        task_id=task_id,
        tool_name="desktop_change_review",
        status="WAITING_APPROVAL",
        risk_level="high",
        input_json={},
    )
    approval = ToolApproval(
        id=approval_id,
        task_id=task_id,
        tool_call_id=tool_call.id,
        organization_id=organization_id,
        requested_by="desktop",
        status="PENDING",
        risk_level="high",
        reason="Confirm destructive hunk operation",
        request_json={},
    )
    session.add_all([tool_call, approval])
    return approval


def _payload(**overrides):
    payload = {
        "operation_id": "operation-1",
        "phase": "completed",
        "action": "stage",
        "path": "src/main.ts",
        "hunk_ids": ["worktree:0", "worktree:1"],
        "preview_sha256": "a" * 64,
    }
    payload.update(overrides)
    return payload


def _set_role(principal_state: dict, role: str) -> None:
    principal_state["value"] = AuthenticatedPrincipal(
        user_id="user-a",
        organization_id="org-a",
        roles={role},
        role=role,
        permissions=set(),
        auth_type="jwt",
        api_key_id=None,
    )


@pytest.mark.parametrize("role", ["admin", "engineer"])
def test_change_review_audit_accepts_admin_and_engineer(audit_context, role: str):
    session, principal_state = audit_context
    _set_role(principal_state, role)

    response = TestClient(app).post(
        "/api/desktop/change-review/audit",
        json=_payload(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "accepted": True,
        "audit_id": data["audit_id"],
        "event_id": None,
        "operation_id": "operation-1",
        "phase": "completed",
    }
    audit = session.get(AdminAuditEvent, data["audit_id"])
    assert audit is not None
    assert audit.organization_id == "org-a"
    assert audit.actor_id == "user-a"
    assert audit.event_type == EventType.DESKTOP_CHANGE_REVIEW_AUDITED.value
    assert audit.action == "desktop.change_review.completed"
    assert audit.resource_type == "desktop_change_review"
    assert audit.resource_id == "operation-1"
    assert audit.payload_json["action"] == "stage"


def test_change_review_audit_rejects_non_engineer(audit_context):
    _session, principal_state = audit_context
    _set_role(principal_state, "member")

    response = TestClient(app).post(
        "/api/desktop/change-review/audit",
        json=_payload(),
    )

    assert response.status_code == 403


@pytest.mark.parametrize("reference", ["task_id", "run_id", "approval_id"])
def test_change_review_audit_hides_cross_organization_references(audit_context, reference: str):
    session, _principal = audit_context
    _add_task(session, "foreign-task", "org-b")
    _add_approval(session, "foreign-approval", "foreign-task", "org-b")
    session.commit()

    response = TestClient(app).post(
        "/api/desktop/change-review/audit",
        json=_payload(
            **{
                reference: (
                    "foreign-task"
                    if reference == "run_id"
                    else f"foreign-{reference.removesuffix('_id')}"
                )
            }
        ),
    )

    assert response.status_code == 404
    assert session.scalar(select(AdminAuditEvent)) is None


def test_change_review_audit_rejects_task_run_mismatch(audit_context):
    session, _principal = audit_context
    _add_task(session, "task-a")
    _add_task(session, "task-b")
    session.commit()

    response = TestClient(app).post(
        "/api/desktop/change-review/audit",
        json=_payload(task_id="task-a", run_id="task-b"),
    )

    assert response.status_code == 422
    assert session.scalar(select(AdminAuditEvent)) is None


def test_change_review_audit_rejects_approval_bound_to_another_task(audit_context):
    session, _principal = audit_context
    _add_task(session, "task-a")
    _add_task(session, "task-b")
    _add_approval(session, "approval-b", "task-b")
    session.commit()

    response = TestClient(app).post(
        "/api/desktop/change-review/audit",
        json=_payload(task_id="task-a", approval_id="approval-b"),
    )

    assert response.status_code == 422
    assert session.scalar(select(AdminAuditEvent)) is None


def test_change_review_audit_is_idempotent_per_operation_and_phase(audit_context):
    session, _principal = audit_context
    _add_task(session, "task-a")
    session.commit()
    client = TestClient(app)
    payload = _payload(run_id="task-a")

    first = client.post("/api/desktop/change-review/audit", json=payload)
    duplicate = client.post("/api/desktop/change-review/audit", json=payload)
    next_phase = client.post(
        "/api/desktop/change-review/audit",
        json={**payload, "phase": "failed", "error_code": "git_apply_failed"},
    )

    assert first.status_code == duplicate.status_code == next_phase.status_code == 200
    assert duplicate.json() == first.json()
    assert next_phase.json()["audit_id"] != first.json()["audit_id"]
    audits = list(session.scalars(select(AdminAuditEvent)))
    assert len(audits) == 2
    events = list(session.scalars(select(AgentEvent)))
    assert len(events) == 2


def test_change_review_audit_database_key_rejects_duplicate_phase(audit_context):
    session, _principal = audit_context
    first = AdminAuditEvent(
        organization_id="dev-org",
        actor_id="dev-engineer",
        event_type=EventType.DESKTOP_CHANGE_REVIEW_AUDITED.value,
        resource_type="desktop_change_review",
        resource_id="operation-db-key",
        action="desktop.change_review.completed",
        payload_json={"operation_id": "operation-db-key"},
    )
    session.add(first)
    session.flush()
    session.add(AdminAuditEvent(
        organization_id="dev-org",
        actor_id="dev-engineer",
        event_type=EventType.DESKTOP_CHANGE_REVIEW_AUDITED.value,
        resource_type="desktop_change_review",
        resource_id="operation-db-key",
        action="desktop.change_review.completed",
        payload_json={"operation_id": "operation-db-key"},
    ))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_change_review_audit_rejects_operation_identity_changes(audit_context):
    session, _principal = audit_context
    client = TestClient(app)

    first = client.post("/api/desktop/change-review/audit", json=_payload())
    conflicting_phase = client.post(
        "/api/desktop/change-review/audit",
        json=_payload(phase="failed", path="src/other.ts", error_code="git_apply_failed"),
    )

    assert first.status_code == 200
    assert conflicting_phase.status_code == 409
    assert len(list(session.scalars(select(AdminAuditEvent)))) == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"path": "../outside.txt"},
        {"path": "/absolute.txt"},
        {"path": "src\\windows-path.txt"},
        {"hunk_ids": ["invalid-hunk"]},
        {"hunk_ids": ["worktree:0", "worktree:0"]},
    ],
)
def test_change_review_audit_rejects_invalid_local_change_identity(
    audit_context,
    overrides: dict,
):
    session, _principal = audit_context

    response = TestClient(app).post(
        "/api/desktop/change-review/audit",
        json=_payload(**overrides),
    )

    assert response.status_code == 422
    assert session.scalar(select(AdminAuditEvent)) is None


def test_change_review_audit_binds_agent_event_to_run_and_approval(audit_context):
    session, _principal = audit_context
    _add_task(session, "task-a")
    _add_approval(session, "approval-a", "task-a")
    session.commit()

    response = TestClient(app).post(
        "/api/desktop/change-review/audit",
        json=_payload(
            phase="requested",
            action="revert",
            task_id="task-a",
            run_id="task-a",
            approval_id="approval-a",
        ),
    )

    assert response.status_code == 200
    data = response.json()
    event = session.get(AgentEvent, data["event_id"])
    assert event is not None
    assert event.task_id == "task-a"
    assert event.agent_run_id is None
    assert event.event_type == EventType.DESKTOP_CHANGE_REVIEW_AUDITED.value
    assert event.actor_type == "user"
    assert event.actor_id == "user-a"
    assert event.payload_json["approval_id"] == "approval-a"
    assert event.payload_json["operation_id"] == "operation-1"


def test_change_review_audit_can_derive_task_from_run(audit_context):
    session, _principal = audit_context
    _add_task(session, "task-a")
    session.commit()

    response = TestClient(app).post(
        "/api/desktop/change-review/audit",
        json=_payload(run_id="task-a"),
    )

    assert response.status_code == 200
    event = session.get(AgentEvent, response.json()["event_id"])
    assert event is not None
    assert event.task_id == "task-a"
    assert event.agent_run_id is None
