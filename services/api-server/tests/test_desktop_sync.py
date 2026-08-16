from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, Task, User
from app.db.session import get_db_session
from app.main import app
from app.security.auth import AuthenticatedPrincipal, get_current_principal


@pytest.fixture
def test_db():
    """Create in-memory SQLite database for testing."""
    from sqlalchemy.pool import StaticPool

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
def test_tasks(test_db: Session, test_user: User):
    """Create test tasks with different timestamps."""
    now = datetime.now(UTC)
    tasks = [
        Task(
            id="task-1",
            organization_id=None,
            created_by=test_user.id,
            title="Task 1",
            goal="Goal 1",
            status="pending",
            model_provider="anthropic",
            model_name="claude-opus-4",
            created_at=now - timedelta(days=5),
            updated_at=now - timedelta(days=5),
        ),
        Task(
            id="task-2",
            organization_id=None,
            created_by=test_user.id,
            title="Task 2",
            goal="Goal 2",
            status="in_progress",
            model_provider="anthropic",
            model_name="claude-opus-4",
            created_at=now - timedelta(days=3),
            updated_at=now - timedelta(days=1),
        ),
        Task(
            id="task-3",
            organization_id=None,
            created_by=test_user.id,
            title="Task 3",
            goal="Goal 3",
            status="completed",
            model_provider="anthropic",
            model_name="claude-opus-4",
            created_at=now - timedelta(days=1),
            updated_at=now - timedelta(hours=2),
            completed_at=now - timedelta(hours=2),
        ),
    ]
    for task in tasks:
        test_db.add(task)
    test_db.commit()
    return tasks


class TestDesktopSyncEndpoint:
    """Test GET /api/desktop/sync endpoint."""

    def test_sync_returns_all_tasks_without_since_parameter(self, test_user, test_tasks):
        """Should return all tasks when no 'since' parameter provided."""
        client = TestClient(app)

        response = client.get("/api/desktop/sync")

        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data
        assert "server_timestamp" in data
        assert len(data["tasks"]) == 3

    def test_sync_returns_tasks_after_since_timestamp(self, test_user, test_tasks):
        """Should return only tasks updated after 'since' timestamp."""
        client = TestClient(app)
        since = (datetime.now(UTC) - timedelta(days=2)).isoformat()

        response = client.get(
            "/api/desktop/sync",
            params={"since": since},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["tasks"]) == 2  # Only task-2 and task-3

    def test_sync_filters_by_date_range(self, test_user, test_tasks):
        """Should filter tasks by start_date and end_date."""
        client = TestClient(app)
        now = datetime.now(UTC)
        start_date = (now - timedelta(days=4)).date().isoformat()
        end_date = (now - timedelta(days=2)).date().isoformat()

        response = client.get(
            "/api/desktop/sync",
            params={"start_date": start_date, "end_date": end_date},
        )

        assert response.status_code == 200
        data = response.json()
        # Should include tasks created within the date range
        assert len(data["tasks"]) >= 1

    def test_sync_returns_server_timestamp(self, test_user, test_tasks):
        """Should return current server timestamp in ISO format."""
        client = TestClient(app)
        before_request = datetime.now(UTC)

        response = client.get("/api/desktop/sync")

        after_request = datetime.now(UTC)
        assert response.status_code == 200
        data = response.json()

        server_timestamp = datetime.fromisoformat(data["server_timestamp"].replace("Z", "+00:00"))
        assert before_request <= server_timestamp <= after_request

    def test_sync_requires_authentication(self):
        """Should return 401 when no authentication provided."""
        client = TestClient(app)

        response = client.get("/api/desktop/sync")

        assert response.status_code == 401

    def test_sync_returns_empty_list_when_no_matching_tasks(self, test_user, test_tasks):
        """Should return empty tasks list when no tasks match filters."""
        client = TestClient(app)
        # Request tasks updated after now (none should match)
        since = datetime.now(UTC).isoformat()

        response = client.get(
            "/api/desktop/sync",
            params={"since": since},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tasks"] == []

    def test_sync_task_includes_all_required_fields(self, test_user, test_tasks):
        """Should include all required fields in task response."""
        client = TestClient(app)

        response = client.get("/api/desktop/sync")

        assert response.status_code == 200
        data = response.json()
        task = data["tasks"][0]

        # Check all required fields are present
        assert "id" in task
        assert "title" in task
        assert "goal" in task
        assert "status" in task
        assert "created_at" in task
        assert "updated_at" in task

    def test_sync_handles_invalid_since_timestamp(self, test_user):
        """Should return 400 when 'since' parameter has invalid format."""
        client = TestClient(app)

        response = client.get(
            "/api/desktop/sync",
            params={"since": "invalid-timestamp"},
        )

        assert response.status_code == 400
        assert "detail" in response.json()
