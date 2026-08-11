"""
Tests for Story 1.2: Wizard State Persistence

Following TDD: Write tests first, then implementation.

Requirements:
1. State persists on step transitions
2. Browser refresh returns to current step
3. State includes completed steps array
4. Mark wizard as complete on final step
"""
import pytest
from sqlalchemy.orm import Session

from app.db.models import User, utc_now
from app.services.onboarding_service import OnboardingService


@pytest.fixture
def onboarding_service(db_session: Session) -> OnboardingService:
    """Create onboarding service instance."""
    return OnboardingService(db_session)


@pytest.fixture
def test_user(db_session: Session) -> User:
    """Create a test user for state persistence tests."""
    user = User(
        id="test-user-state-1",
        email="state@example.com",
        name="State Test User",
        password_hash="hashed_password",
        status="active",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_transition_to_step_updates_current_step(
    db_session: Session, onboarding_service: OnboardingService, test_user: User
) -> None:
    """Test transitioning to a step updates current_step field."""
    # Start at step 0, transition to step 1
    result = onboarding_service.transition_to_step(test_user.id, 1)

    assert result["current_step"] == 1
    assert result["completed_steps"] == []


def test_complete_step_adds_to_completed_array(
    db_session: Session, onboarding_service: OnboardingService, test_user: User
) -> None:
    """Test completing a step adds it to completed_steps array."""
    # Complete step 1
    result = onboarding_service.complete_step(test_user.id, 1)

    assert 1 in result["completed_steps"]
    assert result["current_step"] == 1


def test_complete_step_does_not_duplicate_in_array(
    db_session: Session, onboarding_service: OnboardingService, test_user: User
) -> None:
    """Test completing same step twice doesn't duplicate in array."""
    # Complete step 1 twice
    onboarding_service.complete_step(test_user.id, 1)
    result = onboarding_service.complete_step(test_user.id, 1)

    assert result["completed_steps"].count(1) == 1


def test_state_persists_across_service_instances(
    db_session: Session, test_user: User
) -> None:
    """Test state persists when creating new service instance (simulates browser refresh)."""
    # Complete step 1 with first service
    service1 = OnboardingService(db_session)
    service1.transition_to_step(test_user.id, 1)
    service1.complete_step(test_user.id, 1)
    service1.transition_to_step(test_user.id, 2)

    # Create new service (simulates browser refresh)
    service2 = OnboardingService(db_session)
    state = service2.get_wizard_state(test_user.id)

    assert state["current_step"] == 2
    assert 1 in state["completed_steps"]


def test_get_wizard_state_returns_full_state(
    db_session: Session, onboarding_service: OnboardingService, test_user: User
) -> None:
    """Test get_wizard_state returns complete state information."""
    # Setup some state
    onboarding_service.transition_to_step(test_user.id, 2)
    onboarding_service.complete_step(test_user.id, 1)
    onboarding_service.complete_step(test_user.id, 2)

    state = onboarding_service.get_wizard_state(test_user.id)

    assert state["user_id"] == test_user.id
    assert state["current_step"] == 2
    assert state["completed_steps"] == [1, 2]
    assert state["is_completed"] is False
    assert "created_at" in state
    assert "updated_at" in state


def test_completing_final_step_marks_wizard_complete(
    db_session: Session, onboarding_service: OnboardingService, test_user: User
) -> None:
    """Test completing step 7 (final step) marks wizard as complete."""
    # Complete all steps 1-7
    for step in range(1, 8):
        onboarding_service.transition_to_step(test_user.id, step)
        onboarding_service.complete_step(test_user.id, step)

    state = onboarding_service.get_wizard_state(test_user.id)

    assert state["current_step"] == 7
    assert len(state["completed_steps"]) == 7
    assert state["is_completed"] is True
    assert state["completed_at"] is not None


def test_cannot_transition_to_invalid_step(
    db_session: Session, onboarding_service: OnboardingService, test_user: User
) -> None:
    """Test cannot transition to step < 0 or > 7."""
    with pytest.raises(ValueError, match="Step must be between 0 and 7"):
        onboarding_service.transition_to_step(test_user.id, -1)

    with pytest.raises(ValueError, match="Step must be between 0 and 7"):
        onboarding_service.transition_to_step(test_user.id, 8)


def test_cannot_complete_invalid_step(
    db_session: Session, onboarding_service: OnboardingService, test_user: User
) -> None:
    """Test cannot complete step < 1 or > 7."""
    with pytest.raises(ValueError, match="Step must be between 1 and 7"):
        onboarding_service.complete_step(test_user.id, 0)

    with pytest.raises(ValueError, match="Step must be between 1 and 7"):
        onboarding_service.complete_step(test_user.id, 8)


def test_state_updates_updated_at_timestamp(
    db_session: Session, onboarding_service: OnboardingService, test_user: User
) -> None:
    """Test that state operations update the updated_at timestamp."""
    # Get initial state
    state1 = onboarding_service.get_wizard_state(test_user.id)
    initial_updated_at = state1["updated_at"]

    # Wait and update state
    import time
    time.sleep(0.01)  # Small delay to ensure timestamp changes

    onboarding_service.transition_to_step(test_user.id, 1)
    state2 = onboarding_service.get_wizard_state(test_user.id)

    assert state2["updated_at"] > initial_updated_at


def test_wizard_state_isolated_per_user(
    db_session: Session, onboarding_service: OnboardingService
) -> None:
    """Test that wizard state is isolated per user."""
    # Create two users
    user1 = User(
        id="user-1",
        email="user1@example.com",
        name="User 1",
        password_hash="hash",
        status="active",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    user2 = User(
        id="user-2",
        email="user2@example.com",
        name="User 2",
        password_hash="hash",
        status="active",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add_all([user1, user2])
    db_session.commit()

    # Update user1 to step 3
    onboarding_service.transition_to_step(user1.id, 3)
    onboarding_service.complete_step(user1.id, 1)

    # Update user2 to step 5
    onboarding_service.transition_to_step(user2.id, 5)
    onboarding_service.complete_step(user2.id, 2)

    # Verify isolation
    state1 = onboarding_service.get_wizard_state(user1.id)
    state2 = onboarding_service.get_wizard_state(user2.id)

    assert state1["current_step"] == 3
    assert state1["completed_steps"] == [1]

    assert state2["current_step"] == 5
    assert state2["completed_steps"] == [2]
