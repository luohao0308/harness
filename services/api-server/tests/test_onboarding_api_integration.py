"""
Integration tests for Story 1.2: Wizard State Persistence API

Tests the complete flow from API endpoints through service layer to database.

Requirements:
1. State persists on step transitions
2. Browser refresh returns to current step (GET /wizard/state)
3. State includes completed steps array
4. Mark wizard as complete on final step
5. Validate authentication and authorization
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import OnboardingState, Organization, OrganizationMember, User, utc_now
from app.main import app


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def test_user_with_org(db_session: Session) -> tuple[User, Organization, str]:
    """Create test user with organization and auth token."""
    # Create user
    user = User(
        id="test-user-api",
        email="api@example.com",
        name="API Test User",
        password_hash="hashed_password",
        status="active",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(user)

    # Create organization
    org = Organization(
        id="test-org-api",
        name="Test Org",
        slug="test-org",
        owner_user_id=user.id,
        created_at=utc_now(),
    )
    db_session.add(org)

    # Create membership
    member = OrganizationMember(
        organization_id=org.id,
        user_id=user.id,
        role="admin",
        accepted_at=utc_now(),
    )
    db_session.add(member)

    db_session.commit()

    # Generate mock auth token (in real app this would be JWT)
    token = f"Bearer mock-token-{user.id}"

    return user, org, token


def test_get_wizard_state_returns_initial_state(
    client: TestClient, test_user_with_org: tuple, db_session: Session
) -> None:
    """Test GET /wizard/state/{user_id} returns initial state."""
    user, org, token = test_user_with_org

    response = client.get(
        f"/api/onboarding/wizard/state/{user.id}",
        headers={"Authorization": token},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["user_id"] == user.id
    assert data["current_step"] == 0
    assert data["completed_steps"] == []
    assert data["is_completed"] is False
    assert data["completed_at"] is None


def test_transition_to_step_updates_state(
    client: TestClient, test_user_with_org: tuple, db_session: Session
) -> None:
    """Test POST /wizard/transition updates current_step."""
    user, org, token = test_user_with_org

    response = client.post(
        "/api/onboarding/wizard/transition",
        headers={"Authorization": token},
        json={"step": 2},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["current_step"] == 2
    assert data["completed_steps"] == []


def test_complete_step_adds_to_completed_array(
    client: TestClient, test_user_with_org: tuple, db_session: Session
) -> None:
    """Test POST /wizard/complete-step adds to completed_steps."""
    user, org, token = test_user_with_org

    # Complete step 1
    response = client.post(
        "/api/onboarding/wizard/complete-step",
        headers={"Authorization": token},
        json={"step": 1},
    )

    assert response.status_code == 200
    data = response.json()

    assert 1 in data["completed_steps"]


def test_state_persists_across_requests(
    client: TestClient, test_user_with_org: tuple, db_session: Session
) -> None:
    """Test state persists across multiple API calls (simulates browser refresh)."""
    user, org, token = test_user_with_org

    # Step 1: Transition to step 3
    client.post(
        "/api/onboarding/wizard/transition",
        headers={"Authorization": token},
        json={"step": 3},
    )

    # Step 2: Complete step 1
    client.post(
        "/api/onboarding/wizard/complete-step",
        headers={"Authorization": token},
        json={"step": 1},
    )

    # Step 3: Complete step 2
    client.post(
        "/api/onboarding/wizard/complete-step",
        headers={"Authorization": token},
        json={"step": 2},
    )

    # Step 4: Get state (simulates browser refresh)
    response = client.get(
        f"/api/onboarding/wizard/state/{user.id}",
        headers={"Authorization": token},
    )

    data = response.json()
    assert data["current_step"] == 3
    assert sorted(data["completed_steps"]) == [1, 2]


def test_completing_all_steps_marks_wizard_complete(
    client: TestClient, test_user_with_org: tuple, db_session: Session
) -> None:
    """Test completing all 7 steps marks wizard as complete."""
    user, org, token = test_user_with_org

    # Complete all steps 1-7
    for step in range(1, 8):
        client.post(
            "/api/onboarding/wizard/transition",
            headers={"Authorization": token},
            json={"step": step},
        )
        client.post(
            "/api/onboarding/wizard/complete-step",
            headers={"Authorization": token},
            json={"step": step},
        )

    # Get final state
    response = client.get(
        f"/api/onboarding/wizard/state/{user.id}",
        headers={"Authorization": token},
    )

    data = response.json()
    assert data["current_step"] == 7
    assert len(data["completed_steps"]) == 7
    assert data["is_completed"] is True
    assert data["completed_at"] is not None


def test_transition_with_invalid_step_returns_error(
    client: TestClient, test_user_with_org: tuple
) -> None:
    """Test transition to invalid step returns 422 validation error."""
    user, org, token = test_user_with_org

    # Try step -1
    response = client.post(
        "/api/onboarding/wizard/transition",
        headers={"Authorization": token},
        json={"step": -1},
    )
    assert response.status_code == 422

    # Try step 8
    response = client.post(
        "/api/onboarding/wizard/transition",
        headers={"Authorization": token},
        json={"step": 8},
    )
    assert response.status_code == 422


def test_complete_step_with_invalid_step_returns_error(
    client: TestClient, test_user_with_org: tuple
) -> None:
    """Test complete step with invalid number returns 422 validation error."""
    user, org, token = test_user_with_org

    # Try step 0
    response = client.post(
        "/api/onboarding/wizard/complete-step",
        headers={"Authorization": token},
        json={"step": 0},
    )
    assert response.status_code == 422

    # Try step 8
    response = client.post(
        "/api/onboarding/wizard/complete-step",
        headers={"Authorization": token},
        json={"step": 8},
    )
    assert response.status_code == 422


def test_endpoints_require_authentication(client: TestClient, test_user_with_org: tuple) -> None:
    """Test that wizard endpoints require authentication."""
    user, org, token = test_user_with_org

    # No auth header
    response = client.post(
        "/api/onboarding/wizard/transition",
        json={"step": 1},
    )
    assert response.status_code in [401, 403]

    response = client.post(
        "/api/onboarding/wizard/complete-step",
        json={"step": 1},
    )
    assert response.status_code in [401, 403]


def test_state_isolated_per_user(
    client: TestClient, db_session: Session
) -> None:
    """Test that wizard state is isolated per user."""
    # Create two users
    user1 = User(
        id="user-1-isolation",
        email="user1@example.com",
        name="User 1",
        password_hash="hash",
        status="active",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    user2 = User(
        id="user-2-isolation",
        email="user2@example.com",
        name="User 2",
        password_hash="hash",
        status="active",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add_all([user1, user2])

    org = Organization(
        id="test-org-isolation",
        name="Test Org",
        slug="test-org-isolation",
        owner_user_id=user1.id,
        created_at=utc_now(),
    )
    db_session.add(org)

    # Add memberships
    member1 = OrganizationMember(
        organization_id=org.id,
        user_id=user1.id,
        role="admin",
        accepted_at=utc_now(),
    )
    member2 = OrganizationMember(
        organization_id=org.id,
        user_id=user2.id,
        role="engineer",
        accepted_at=utc_now(),
    )
    db_session.add_all([member1, member2])
    db_session.commit()

    token1 = f"Bearer mock-token-{user1.id}"
    token2 = f"Bearer mock-token-{user2.id}"

    # User 1 goes to step 3
    client.post(
        "/api/onboarding/wizard/transition",
        headers={"Authorization": token1},
        json={"step": 3},
    )

    # User 2 goes to step 5
    client.post(
        "/api/onboarding/wizard/transition",
        headers={"Authorization": token2},
        json={"step": 5},
    )

    # Verify isolation
    response1 = client.get(
        f"/api/onboarding/wizard/state/{user1.id}",
        headers={"Authorization": token1},
    )
    response2 = client.get(
        f"/api/onboarding/wizard/state/{user2.id}",
        headers={"Authorization": token2},
    )

    assert response1.json()["current_step"] == 3
    assert response2.json()["current_step"] == 5
