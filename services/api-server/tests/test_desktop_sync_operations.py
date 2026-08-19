from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import (
    AgentEvent,
    AgentRun,
    Base,
    ModelCall,
    Task,
    ToolApproval,
    ToolCall,
    User,
)
from app.db.session import get_db_session
from app.main import app
from app.security.auth import AuthenticatedPrincipal, get_current_principal


@pytest.fixture
def test_db():
    """Create in-memory SQLite database for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine)
    session = TestingSessionLocal()

    # Override database dependency
    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db_session] = override_get_db

    yield session

    # Cleanup
    session.close()
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(test_db: Session):
    """Create a test user."""
    user = User(
        id="test-user-id",
        email="test@example.com",
        name="Test User",
        password_hash="dummy_hash",
        email_verified=True,
    )
    test_db.add(user)
    test_db.commit()

    # Override authentication to return this user's principal
    def override_get_current_principal():
        return AuthenticatedPrincipal(
            user_id=user.id,
            organization_id="org-a",
            roles=set(),
            role=None,
            permissions=set(),
            auth_type="jwt",
            api_key_id=None,
        )

    app.dependency_overrides[get_current_principal] = override_get_current_principal

    return user


@pytest.fixture
def existing_task(test_db: Session, test_user: User):
    """Create an existing task in the database."""
    task = Task(
        id="existing-task-id",
        organization_id="org-a",
        created_by=test_user.id,
        title="Existing Task",
        goal="Original Goal",
        status="pending",
        model_provider="anthropic",
        model_name="claude-opus-4",
        created_at=datetime.now(UTC) - timedelta(days=1),
        updated_at=datetime.now(UTC) - timedelta(days=1),
    )
    test_db.add(task)
    test_db.commit()
    return task


class TestDesktopSyncOperationsEndpoint:
    """Test POST /api/desktop/sync/operations endpoint."""

    def test_create_new_task(self, test_user):
        """Should create a new task from desktop operation."""
        client = TestClient(app)
        operation = {
            "type": "create",
            "entity_type": "task",
            "entity_id": "new-task-id",
            "data": {
                "title": "New Task",
                "goal": "New Goal",
                "status": "pending",
                "model_provider": "anthropic",
                "model_name": "claude-opus-4",
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }

        response = client.post(
            "/api/desktop/sync/operations",
            json={"operations": [operation]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["applied"] == 1
        assert data["conflicts"] == []

    def test_update_existing_task(self, test_user, existing_task):
        """Should update an existing task."""
        client = TestClient(app)
        operation = {
            "type": "update",
            "entity_type": "task",
            "entity_id": existing_task.id,
            "data": {
                "title": "Updated Task",
                "status": "in_progress",
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }

        response = client.post(
            "/api/desktop/sync/operations",
            json={"operations": [operation]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["applied"] == 1
        assert data["conflicts"] == []

    def test_delete_task(self, test_user, existing_task):
        """Should delete a task."""
        client = TestClient(app)
        operation = {
            "type": "delete",
            "entity_type": "task",
            "entity_id": existing_task.id,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        response = client.post(
            "/api/desktop/sync/operations",
            json={"operations": [operation]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["applied"] == 1
        assert data["conflicts"] == []

    def test_detect_conflict_on_concurrent_update(self, test_user, existing_task, test_db):
        """Should detect conflicts when server version is newer."""
        # Update the task on the server
        existing_task.title = "Server Updated Title"
        existing_task.updated_at = datetime.now(UTC)
        test_db.commit()

        # Try to apply a client update with older timestamp
        client = TestClient(app)
        operation = {
            "type": "update",
            "entity_type": "task",
            "entity_id": existing_task.id,
            "data": {
                "title": "Client Updated Title",
            },
            "timestamp": (datetime.now(UTC) - timedelta(seconds=10)).isoformat(),
        }

        response = client.post(
            "/api/desktop/sync/operations",
            json={"operations": [operation]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["applied"] == 0
        assert len(data["conflicts"]) == 1
        conflict = data["conflicts"][0]
        assert conflict["entity_id"] == existing_task.id
        assert conflict["entity_type"] == "task"
        assert "server_version" in conflict
        assert "client_version" in conflict

    def test_apply_multiple_operations(self, test_user):
        """Should apply multiple operations in a batch."""
        client = TestClient(app)
        operations = [
            {
                "type": "create",
                "entity_type": "task",
                "entity_id": "task-1",
                "data": {
                    "title": "Task 1",
                    "goal": "Goal 1",
                    "status": "pending",
                    "model_provider": "anthropic",
                    "model_name": "claude-opus-4",
                },
                "timestamp": datetime.now(UTC).isoformat(),
            },
            {
                "type": "create",
                "entity_type": "task",
                "entity_id": "task-2",
                "data": {
                    "title": "Task 2",
                    "goal": "Goal 2",
                    "status": "pending",
                    "model_provider": "anthropic",
                    "model_name": "claude-opus-4",
                },
                "timestamp": datetime.now(UTC).isoformat(),
            },
        ]

        response = client.post(
            "/api/desktop/sync/operations",
            json={"operations": operations},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["applied"] == 2
        assert data["conflicts"] == []

    def test_requires_authentication(self):
        """Should return 401 when no authentication provided."""
        client = TestClient(app)
        app.dependency_overrides.clear()

        response = client.post(
            "/api/desktop/sync/operations",
            json={"operations": []},
        )

        assert response.status_code == 401

    def test_validates_operation_format(self, test_user):
        """Should return 400 when operation format is invalid."""
        client = TestClient(app)
        invalid_operation = {
            "type": "invalid_type",
            "entity_type": "task",
            "entity_id": "task-1",
        }

        response = client.post(
            "/api/desktop/sync/operations",
            json={"operations": [invalid_operation]},
        )

        assert response.status_code == 422  # FastAPI validation error

    def test_handles_empty_operations_list(self, test_user):
        """Should handle empty operations list gracefully."""
        client = TestClient(app)

        response = client.post(
            "/api/desktop/sync/operations",
            json={"operations": []},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["applied"] == 0
        assert data["conflicts"] == []

    def test_imports_offline_agent_snapshot_idempotently(self, test_user, test_db):
        """A retried terminal offline Run creates one canonical evidence graph."""
        run_id = "11111111-1111-4111-8111-111111111111"
        event_id = "22222222-2222-4222-8222-222222222222"
        model_call_id = "33333333-3333-4333-8333-333333333333"
        tool_call_id = "44444444-4444-4444-8444-444444444444"
        approval_id = "55555555-5555-4555-8555-555555555555"
        timestamp = datetime.now(UTC).isoformat()
        snapshot = {
            "schemaVersion": 1,
            "run": {
                "id": run_id,
                "prompt": "offline release check",
                "result": "done",
                "status": "COMPLETED",
                "modelProvider": "desktop-offline",
                "modelName": "deterministic-v1",
                "syncRevision": 2,
                "startedAt": timestamp,
                "completedAt": timestamp,
            },
            "events": [{
                "id": event_id,
                "runId": run_id,
                "sequence": 1,
                "eventType": "TASK_COMPLETED",
                "payload": {"offline": True},
                "actorType": "system",
                "createdAt": timestamp,
            }],
            "modelCalls": [{
                "id": model_call_id,
                "runId": run_id,
                "modelProvider": "desktop-offline",
                "modelName": "deterministic-v1",
                "status": "SUCCESS",
                "durationMs": 4,
                "requestSha256": "a" * 64,
                "responseText": "done",
                "createdAt": timestamp,
            }],
            "toolCalls": [{
                "id": tool_call_id,
                "runId": run_id,
                "toolName": "workspace.write_text",
                "riskLevel": "HIGH",
                "status": "SUCCESS",
                "input": {"path": "report.txt"},
                "output": {"path": "report.txt"},
                "durationMs": 2,
                "createdAt": timestamp,
            }],
            "approvals": [{
                "id": approval_id,
                "runId": run_id,
                "toolCallId": tool_call_id,
                "toolName": "workspace.write_text",
                "status": "APPROVED",
                "reason": "approved",
                "request": {"path": "report.txt"},
                "decision": {"approved": True},
                "createdAt": timestamp,
                "decidedAt": timestamp,
            }],
        }
        operation = {
            "type": "create",
            "entity_type": "offline_agent_run",
            "entity_id": run_id,
            "data": snapshot,
            "timestamp": timestamp,
        }
        client = TestClient(app)
        first = client.post("/api/desktop/sync/operations", json={"operations": [operation]})
        second = client.post("/api/desktop/sync/operations", json={"operations": [operation]})

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["applied"] == 1
        assert second.json()["applied"] == 1
        assert test_db.query(Task).filter(Task.id == run_id).count() == 1
        assert test_db.query(AgentRun).filter(AgentRun.id == run_id).count() == 1
        assert test_db.query(AgentEvent).filter(AgentEvent.id == event_id).count() == 1
        assert test_db.query(ModelCall).filter(ModelCall.id == model_call_id).count() == 1
        assert test_db.query(ToolCall).filter(ToolCall.id == tool_call_id).count() == 1
        assert test_db.query(ToolApproval).filter(ToolApproval.id == approval_id).count() == 1

    def test_rejects_invalid_offline_agent_snapshot_as_a_conflict(self, test_user):
        client = TestClient(app)
        response = client.post(
            "/api/desktop/sync/operations",
            json={"operations": [{
                "type": "create",
                "entity_type": "offline_agent_run",
                "entity_id": "not-a-uuid",
                "data": {
                    "run": {
                        "id": "not-a-uuid",
                        "prompt": "invalid snapshot",
                        "status": "COMPLETED",
                    },
                    "events": [],
                    "modelCalls": [],
                    "toolCalls": [],
                    "approvals": [],
                },
                "timestamp": datetime.now(UTC).isoformat(),
            }]},
        )

        assert response.status_code == 200
        assert response.json()["applied"] == 0
        assert response.json()["conflicts"][0]["entity_id"] == "not-a-uuid"

    @pytest.mark.parametrize("sync_revision", [None, "2", -1, True])
    def test_rejects_invalid_offline_sync_revision_for_new_run(self, test_user, sync_revision):
        operation = _offline_agent_operation(
            datetime.now(UTC).isoformat(),
            sync_revision=sync_revision,
        )

        response = TestClient(app).post(
            "/api/desktop/sync/operations",
            json={"operations": [operation]},
        )

        assert response.status_code == 200
        assert response.json()["applied"] == 0
        assert response.json()["conflicts"][0]["entity_id"] == operation["entity_id"]

    def test_rejects_missing_offline_sync_revision(self, test_user):
        operation = _offline_agent_operation(datetime.now(UTC).isoformat())
        del operation["data"]["run"]["syncRevision"]

        response = TestClient(app).post(
            "/api/desktop/sync/operations",
            json={"operations": [operation]},
        )

        assert response.status_code == 200
        assert response.json()["applied"] == 0
        assert response.json()["conflicts"][0]["entity_id"] == operation["entity_id"]

    def test_applies_offline_sync_revisions_monotonically(self, test_user, test_db):
        timestamp = datetime.now(UTC).isoformat()
        client = TestClient(app)

        first = client.post(
            "/api/desktop/sync/operations",
            json={"operations": [_offline_agent_operation(timestamp, sync_revision=5)]},
        )
        assert first.json()["applied"] == 1
        task = test_db.get(Task, "11111111-1111-4111-8111-111111111111")
        assert task is not None
        assert task.status == "COMPLETED"

        stale = _offline_agent_operation(timestamp, sync_revision=4)
        stale["data"]["run"]["status"] = "FAILED"
        stale_response = client.post(
            "/api/desktop/sync/operations",
            json={"operations": [stale]},
        )
        assert stale_response.json()["applied"] == 0
        assert stale_response.json()["conflicts"][0]["entity_id"] == task.id
        test_db.refresh(task)
        assert task.status == "COMPLETED"
        assert task.capability_snapshot_json["sync_revision"] == 5

        same = _offline_agent_operation(timestamp, sync_revision=5)
        same["data"]["run"]["status"] = "FAILED"
        same["data"]["events"][0]["id"] = "66666666-6666-4666-8666-666666666666"
        same["data"]["events"][0]["sequence"] = 2
        same_response = client.post(
            "/api/desktop/sync/operations",
            json={"operations": [same]},
        )
        assert same_response.json()["applied"] == 1
        test_db.refresh(task)
        assert task.status == "COMPLETED"
        assert task.capability_snapshot_json["sync_revision"] == 5
        assert test_db.get(AgentEvent, "66666666-6666-4666-8666-666666666666") is None

        newer = _offline_agent_operation(timestamp, sync_revision=6)
        newer["data"]["run"]["status"] = "FAILED"
        newer_response = client.post(
            "/api/desktop/sync/operations",
            json={"operations": [newer]},
        )
        assert newer_response.json()["applied"] == 1
        test_db.refresh(task)
        assert task.status == "FAILED"
        assert task.capability_snapshot_json["sync_revision"] == 6

    def test_rejects_offline_agent_task_owned_by_another_organization(
        self,
        test_user,
        test_db,
    ):
        run_id = "11111111-1111-4111-8111-111111111111"
        timestamp = datetime.now(UTC)
        foreign_task = Task(
            id=run_id,
            organization_id="org-b",
            created_by=test_user.id,
            title="Foreign organization task",
            goal="Must not change",
            status="COMPLETED",
            model_provider="desktop-offline",
            model_name="deterministic-v1",
            capability_snapshot_json={"source": "desktop-offline-agent"},
            created_at=timestamp,
            updated_at=timestamp,
        )
        test_db.add(foreign_task)
        test_db.commit()

        response = TestClient(app).post(
            "/api/desktop/sync/operations",
            json={"operations": [_offline_agent_operation(timestamp.isoformat())]},
        )

        assert response.status_code == 200
        assert response.json()["applied"] == 0
        assert response.json()["conflicts"][0]["entity_id"] == run_id
        test_db.refresh(foreign_task)
        assert foreign_task.title == "Foreign organization task"
        assert foreign_task.organization_id == "org-b"

    @pytest.mark.parametrize(
        "collision_kind",
        ["agent_run", "event", "model_call", "tool_call", "approval"],
    )
    def test_rejects_offline_agent_evidence_uuid_owned_by_another_run(
        self,
        collision_kind,
        test_user,
        test_db,
    ):
        timestamp = datetime.now(UTC)
        operation = _offline_agent_operation(timestamp.isoformat())
        run_id = operation["entity_id"]
        foreign_task_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        foreign_run_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        foreign_tool_call_id = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
        foreign_task = Task(
            id=foreign_task_id,
            organization_id="org-a",
            created_by=test_user.id,
            title="Foreign evidence owner",
            goal="Foreign evidence owner",
            status="COMPLETED",
            model_provider="desktop-offline",
            model_name="deterministic-v1",
            capability_snapshot_json={"source": "desktop-offline-agent"},
            created_at=timestamp,
            updated_at=timestamp,
        )
        foreign_run = AgentRun(
            id=run_id if collision_kind == "agent_run" else foreign_run_id,
            task_id=foreign_task_id,
            agent_type="root",
            status="COMPLETED",
            context_json={"source": "foreign"},
            capability_snapshot_json={"source": "foreign"},
            started_at=timestamp,
            completed_at=timestamp,
        )
        test_db.add_all([foreign_task, foreign_run])
        test_db.flush()

        if collision_kind == "event":
            test_db.add(AgentEvent(
                id=operation["data"]["events"][0]["id"],
                task_id=foreign_task_id,
                agent_run_id=foreign_run.id,
                sequence=1,
                event_type="TASK_COMPLETED",
                payload_json={},
                actor_type="system",
                created_at=timestamp,
            ))
        elif collision_kind == "model_call":
            test_db.add(ModelCall(
                id=operation["data"]["modelCalls"][0]["id"],
                task_id=foreign_task_id,
                agent_run_id=foreign_run.id,
                model_provider="foreign",
                model_name="foreign",
                status="SUCCESS",
                capability_snapshot_json={"source": "foreign"},
                request_json={},
                response_json={},
                created_at=timestamp,
            ))
        elif collision_kind in {"tool_call", "approval"}:
            tool_call_id = (
                operation["data"]["toolCalls"][0]["id"]
                if collision_kind == "tool_call"
                else foreign_tool_call_id
            )
            test_db.add(ToolCall(
                id=tool_call_id,
                task_id=foreign_task_id,
                agent_run_id=foreign_run.id,
                tool_name="workspace.write_text",
                status="SUCCESS",
                risk_level="HIGH",
                capability_snapshot_json={"source": "foreign"},
                input_json={},
                output_json={},
                created_at=timestamp,
            ))
            test_db.flush()
            if collision_kind == "approval":
                test_db.add(ToolApproval(
                    id=operation["data"]["approvals"][0]["id"],
                    task_id=foreign_task_id,
                    tool_call_id=tool_call_id,
                    organization_id="org-a",
                    requested_by=test_user.id,
                    status="APPROVED",
                    risk_level="HIGH",
                    reason="foreign approval",
                    request_json={},
                    decision_json={},
                    created_at=timestamp,
                    decided_at=timestamp,
                ))
        test_db.commit()

        response = TestClient(app).post(
            "/api/desktop/sync/operations",
            json={"operations": [operation]},
        )

        assert response.status_code == 200
        assert response.json()["applied"] == 0
        assert response.json()["conflicts"][0]["entity_id"] == run_id
        assert test_db.get(Task, run_id) is None


def _offline_agent_operation(timestamp: str, sync_revision: object = 2) -> dict:
    run_id = "11111111-1111-4111-8111-111111111111"
    return {
        "type": "create",
        "entity_type": "offline_agent_run",
        "entity_id": run_id,
        "data": {
            "schemaVersion": 1,
            "run": {
                "id": run_id,
                "prompt": "offline release check",
                "result": "done",
                "status": "COMPLETED",
                "modelProvider": "desktop-offline",
                "modelName": "deterministic-v1",
                "syncRevision": sync_revision,
                "startedAt": timestamp,
                "completedAt": timestamp,
            },
            "events": [{
                "id": "22222222-2222-4222-8222-222222222222",
                "runId": run_id,
                "sequence": 1,
                "eventType": "TASK_COMPLETED",
                "payload": {"offline": True},
                "actorType": "system",
                "createdAt": timestamp,
            }],
            "modelCalls": [{
                "id": "33333333-3333-4333-8333-333333333333",
                "runId": run_id,
                "modelProvider": "desktop-offline",
                "modelName": "deterministic-v1",
                "status": "SUCCESS",
                "durationMs": 4,
                "requestSha256": "a" * 64,
                "responseText": "done",
                "createdAt": timestamp,
            }],
            "toolCalls": [{
                "id": "44444444-4444-4444-8444-444444444444",
                "runId": run_id,
                "toolName": "workspace.write_text",
                "riskLevel": "HIGH",
                "status": "SUCCESS",
                "input": {"path": "report.txt"},
                "output": {"path": "report.txt"},
                "durationMs": 2,
                "createdAt": timestamp,
            }],
            "approvals": [{
                "id": "55555555-5555-4555-8555-555555555555",
                "runId": run_id,
                "toolCallId": "44444444-4444-4444-8444-444444444444",
                "toolName": "workspace.write_text",
                "status": "APPROVED",
                "reason": "approved",
                "request": {"path": "report.txt"},
                "decision": {"approved": True},
                "createdAt": timestamp,
                "decidedAt": timestamp,
            }],
        },
        "timestamp": timestamp,
    }
