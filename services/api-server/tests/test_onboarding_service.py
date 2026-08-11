"""
Tests for onboarding service - Story 1.1: First-Run Detection Logic

Following TDD: Write tests first, then implementation.
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
    """Create a test user for onboarding state tests."""
    user = User(
        id="test-user-1",
        email="test@example.com",
        name="Test User",
        password_hash="hashed_password",
        status="active",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_is_first_run_when_no_users(
    db_session: Session, onboarding_service: OnboardingService
) -> None:
    """Test first-run detection returns True when no users exist."""
    assert onboarding_service.is_first_run() is True


def test_is_first_run_when_users_exist(
    db_session: Session, onboarding_service: OnboardingService
) -> None:
    """Test first-run detection returns False when users exist."""
    # Create a user
    user = User(
        id="user-1",
        email="admin@example.com",
        name="Admin User",
        password_hash="hashed_password",
        status="active",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(user)
    db_session.commit()

    assert onboarding_service.is_first_run() is False


def test_is_first_run_when_only_inactive_users(
    db_session: Session, onboarding_service: OnboardingService
) -> None:
    """Test first-run detection returns True when only inactive users exist."""
    # Create inactive user
    user = User(
        id="user-1",
        email="deleted@example.com",
        name="Deleted User",
        password_hash="hashed_password",
        status="deleted",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(user)
    db_session.commit()

    assert onboarding_service.is_first_run() is True


def test_should_redirect_to_onboarding_on_first_run(
    db_session: Session, onboarding_service: OnboardingService
) -> None:
    """Test should redirect to onboarding when it's first run."""
    result = onboarding_service.get_onboarding_status()

    assert result["is_first_run"] is True
    assert result["should_show_wizard"] is True
    assert result["redirect_to"] == "/onboarding/welcome"


def test_should_not_redirect_when_users_exist(
    db_session: Session, onboarding_service: OnboardingService
) -> None:
    """Test should not redirect when users already exist."""
    # Create user
    user = User(
        id="user-1",
        email="admin@example.com",
        name="Admin User",
        password_hash="hashed_password",
        status="active",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(user)
    db_session.commit()

    result = onboarding_service.get_onboarding_status()

    assert result["is_first_run"] is False
    assert result["should_show_wizard"] is False
    assert result["redirect_to"] is None


def test_can_skip_wizard(
    db_session: Session, onboarding_service: OnboardingService, test_user: User
) -> None:
    """Test that wizard can be skipped (for advanced users)."""
    result = onboarding_service.get_onboarding_status(test_user.id)

    # Wizard should not be shown (user exists)
    assert result["should_show_wizard"] is False

    # Mark as skipped
    skip_result = onboarding_service.skip_wizard(test_user.id)

    assert skip_result["wizard_skipped"] is True
    assert skip_result["should_show_wizard"] is False


def test_onboarding_state_tracks_completion(
    db_session: Session, onboarding_service: OnboardingService, test_user: User
) -> None:
    """Test that onboarding state tracks wizard completion."""
    # Initial state
    status = onboarding_service.get_onboarding_status(test_user.id)
    assert status["is_completed"] is False

    # Mark as completed
    result = onboarding_service.mark_wizard_completed(test_user.id)

    assert result["is_completed"] is True
    assert result["completed_at"] is not None


def test_skip_wizard_when_already_completed(
    db_session: Session, onboarding_service: OnboardingService, test_user: User
) -> None:
    """Test skip wizard returns existing state when already completed."""
    # Complete wizard first
    onboarding_service.mark_wizard_completed(test_user.id)

    # Try to skip - should still show as completed
    result = onboarding_service.skip_wizard(test_user.id)

    assert result["is_completed"] is True
    assert result["wizard_skipped"] is False  # Not skipped, it was completed
