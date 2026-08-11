"""Integration tests for the full desktop sync cycle.

Tests the complete flow:
1. Client goes offline and makes local changes
2. Client comes back online
3. Client fetches changes from server (GET /api/desktop/sync/changes)
4. Client detects conflicts
5. Client resolves conflicts and applies operations (POST /api/desktop/sync/operations)
"""

from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, User
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
        id="test-user-123",
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
            organization_id=None,
            roles=set(),
            role=None,
            permissions=set(),
            auth_type="jwt",
            api_key_id=None,
        )

    app.dependency_overrides[get_current_principal] = override_get_current_principal

    return user


@pytest.fixture
def client(test_user):
    """FastAPI test client. Depends on test_user to ensure auth is set up."""
    return TestClient(app)


def test_full_sync_cycle_no_conflicts(client: TestClient, test_user: User, test_db: Session):
    """Test full sync cycle when there are no conflicts."""
    # Step 1: Create a task on the server
    task_id = "task-001"
    create_time = datetime.now(UTC).isoformat()

    create_response = client.post(
        "/api/desktop/sync/operations",
        json={
            "operations": [
                {
                    "type": "create",
                    "entity_type": "task",
                    "entity_id": task_id,
                    "timestamp": create_time,
                    "data": {
                        "title": "Test Task",
                        "goal": "Test goal",
                        "status": "pending",
                        "model_provider": "anthropic",
                        "model_name": "claude-opus-4",
                    },
                }
            ]
        },
    )

    assert create_response.status_code == 200
    assert create_response.json()["applied"] == 1
    assert len(create_response.json()["conflicts"]) == 0

    # Step 2: Client fetches changes (should see the created task)
    last_sync = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    changes_response = client.get(
        f"/api/desktop/sync/changes?last_sync={quote(last_sync, safe='')}",
    )

    assert changes_response.status_code == 200
    changes = changes_response.json()
    assert changes["total"] == 1
    assert changes["changes"][0]["entity_id"] == task_id
    assert changes["changes"][0]["change_type"] == "created"

    # Step 3: Client updates the task without conflicts
    update_time = datetime.now(UTC).isoformat()
    update_response = client.post(
        "/api/desktop/sync/operations",
        json={
            "operations": [
                {
                    "type": "update",
                    "entity_type": "task",
                    "entity_id": task_id,
                    "timestamp": update_time,
                    "data": {"status": "running"},
                }
            ]
        },
    )

    assert update_response.status_code == 200
    assert update_response.json()["applied"] == 1
    assert len(update_response.json()["conflicts"]) == 0


def test_full_sync_cycle_with_conflict_resolution(
    client: TestClient, test_user: User, test_db: Session
):
    """Test full sync cycle with conflict detection and resolution."""
    # Step 1: Create a task on the server
    task_id = "task-002"
    create_time = datetime.now(UTC)

    create_response = client.post(
        "/api/desktop/sync/operations",
        json={
            "operations": [
                {
                    "type": "create",
                    "entity_type": "task",
                    "entity_id": task_id,
                    "timestamp": create_time.isoformat(),
                    "data": {
                        "title": "Original Title",
                        "goal": "Original goal",
                        "status": "pending",
                        "model_provider": "anthropic",
                        "model_name": "claude-opus-4",
                    },
                }
            ]
        },
    )

    assert create_response.status_code == 200
    assert create_response.json()["applied"] == 1

    # Step 2: Server updates the task (simulating another client)
    server_update_time = create_time + timedelta(minutes=2)
    server_update_response = client.post(
        "/api/desktop/sync/operations",
        json={
            "operations": [
                {
                    "type": "update",
                    "entity_type": "task",
                    "entity_id": task_id,
                    "timestamp": server_update_time.isoformat(),
                    "data": {"title": "Server Updated Title"},
                }
            ]
        },
    )

    assert server_update_response.status_code == 200
    assert server_update_response.json()["applied"] == 1

    # Step 3: Client tries to update with an older timestamp (conflict)
    client_update_time = create_time + timedelta(minutes=1)
    conflict_response = client.post(
        "/api/desktop/sync/operations",
        json={
            "operations": [
                {
                    "type": "update",
                    "entity_type": "task",
                    "entity_id": task_id,
                    "timestamp": client_update_time.isoformat(),
                    "data": {"title": "Client Updated Title"},
                }
            ]
        },
    )

    assert conflict_response.status_code == 200
    result = conflict_response.json()
    assert result["applied"] == 0
    assert len(result["conflicts"]) == 1

    conflict = result["conflicts"][0]
    assert conflict["entity_id"] == task_id
    assert conflict["entity_type"] == "task"
    assert "server_version" in conflict
    assert "client_version" in conflict
    assert conflict["server_version"]["title"] == "Server Updated Title"

    # Step 4: Client resolves conflict by using a timestamp newer than server version
    resolve_time = server_update_time + timedelta(seconds=1)
    resolve_response = client.post(
        "/api/desktop/sync/operations",
        json={
            "operations": [
                {
                    "type": "update",
                    "entity_type": "task",
                    "entity_id": task_id,
                    "timestamp": resolve_time.isoformat(),
                    "data": {"title": "Resolved Title"},
                }
            ]
        },
    )

    assert resolve_response.status_code == 200
    assert resolve_response.json()["applied"] == 1
    assert len(resolve_response.json()["conflicts"]) == 0


def test_sync_cycle_with_delete_operation(client: TestClient, test_user: User, test_db: Session):
    """Test sync cycle including delete operations."""
    # Step 1: Create a task
    task_id = "task-003"
    create_time = datetime.now(UTC).isoformat()

    create_response = client.post(
        "/api/desktop/sync/operations",
        json={
            "operations": [
                {
                    "type": "create",
                    "entity_type": "task",
                    "entity_id": task_id,
                    "timestamp": create_time,
                    "data": {
                        "title": "To Be Deleted",
                        "goal": "Test deletion",
                        "status": "pending",
                        "model_provider": "anthropic",
                        "model_name": "claude-opus-4",
                    },
                }
            ]
        },
    )

    assert create_response.status_code == 200
    assert create_response.json()["applied"] == 1

    # Step 2: Delete the task
    delete_time = datetime.now(UTC).isoformat()
    delete_response = client.post(
        "/api/desktop/sync/operations",
        json={
            "operations": [
                {
                    "type": "delete",
                    "entity_type": "task",
                    "entity_id": task_id,
                    "timestamp": delete_time,
                }
            ]
        },
    )

    assert delete_response.status_code == 200
    assert delete_response.json()["applied"] == 1

    # Step 3: Verify task is deleted by fetching changes
    last_sync = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    changes_response = client.get(
        f"/api/desktop/sync/changes?last_sync={quote(last_sync, safe='')}",
    )

    assert changes_response.status_code == 200
    changes = changes_response.json()

    # The task should appear as deleted in changes
    deleted_task = next(
        (c for c in changes["changes"] if c["entity_id"] == task_id), None
    )
    assert deleted_task is not None
    assert deleted_task["change_type"] == "deleted"


def test_batch_operations_sync_cycle(client: TestClient, test_user: User, test_db: Session):
    """Test sync cycle with multiple operations in a single batch."""
    # Create multiple tasks in one batch
    base_time = datetime.now(UTC)
    operations = []

    for i in range(5):
        operations.append(
            {
                "type": "create",
                "entity_type": "task",
                "entity_id": f"batch-task-{i}",
                "timestamp": (base_time + timedelta(seconds=i)).isoformat(),
                "data": {
                    "title": f"Batch Task {i}",
                    "goal": f"Goal {i}",
                    "status": "pending",
                    "model_provider": "anthropic",
                    "model_name": "claude-opus-4",
                },
            }
        )

    batch_response = client.post(
        "/api/desktop/sync/operations",
        json={"operations": operations},
    )

    assert batch_response.status_code == 200
    assert batch_response.json()["applied"] == 5
    assert len(batch_response.json()["conflicts"]) == 0

    # Fetch all changes
    last_sync = (base_time - timedelta(minutes=1)).isoformat()
    changes_response = client.get(
        f"/api/desktop/sync/changes?last_sync={quote(last_sync, safe='')}",
    )

    assert changes_response.status_code == 200
    changes = changes_response.json()
    assert changes["total"] == 5


def test_sync_cycle_authorization(client: TestClient, test_db: Session):
    """Test that sync operations are properly authorized by user."""
    # Create two test users
    user1 = User(
        id="user-1",
        email="user1@example.com",
        name="User 1",
        password_hash="dummy_hash",
        email_verified=True,
    )
    user2 = User(
        id="user-2",
        email="user2@example.com",
        name="User 2",
        password_hash="dummy_hash",
        email_verified=True,
    )
    test_db.add(user1)
    test_db.add(user2)
    test_db.commit()

    # Override authentication for user 1
    def override_get_current_principal_user1():
        return AuthenticatedPrincipal(
            user_id=user1.id,
            organization_id=None,
            roles=set(),
            role=None,
            permissions=set(),
            auth_type="jwt",
            api_key_id=None,
        )

    app.dependency_overrides[get_current_principal] = override_get_current_principal_user1

    # User 1 creates a task
    task_id = "task-auth-001"
    create_time = datetime.now(UTC).isoformat()

    create_response = client.post(
        "/api/desktop/sync/operations",
        json={
            "operations": [
                {
                    "type": "create",
                    "entity_type": "task",
                    "entity_id": task_id,
                    "timestamp": create_time,
                    "data": {
                        "title": "User 1 Task",
                        "goal": "Test authorization",
                        "status": "pending",
                        "model_provider": "anthropic",
                        "model_name": "claude-opus-4",
                    },
                }
            ]
        },
    )

    assert create_response.status_code == 200
    assert create_response.json()["applied"] == 1

    # Override authentication for user 2
    def override_get_current_principal_user2():
        return AuthenticatedPrincipal(
            user_id=user2.id,
            organization_id=None,
            roles=set(),
            role=None,
            permissions=set(),
            auth_type="jwt",
            api_key_id=None,
        )

    app.dependency_overrides[get_current_principal] = override_get_current_principal_user2

    # User 2 should not see User 1's task in changes
    last_sync = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    user2_changes = client.get(
        f"/api/desktop/sync/changes?last_sync={quote(last_sync, safe='')}",
    )

    assert user2_changes.status_code == 200
    changes = user2_changes.json()
    assert changes["total"] == 0

    # User 2 cannot update User 1's task
    update_time = datetime.now(UTC).isoformat()
    user2_update = client.post(
        "/api/desktop/sync/operations",
        json={
            "operations": [
                {
                    "type": "update",
                    "entity_type": "task",
                    "entity_id": task_id,
                    "timestamp": update_time,
                    "data": {"title": "Unauthorized Update"},
                }
            ]
        },
    )

    assert user2_update.status_code == 200
    # Update is silently ignored (not applied) for security
    assert user2_update.json()["applied"] == 0
