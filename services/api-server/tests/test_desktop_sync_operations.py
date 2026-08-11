from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, Task, User
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
def existing_task(test_db: Session, test_user: User):
    """Create an existing task in the database."""
    task = Task(
        id="existing-task-id",
        organization_id=None,
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
