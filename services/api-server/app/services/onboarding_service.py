"""
Onboarding Service - Story 1.1: First-Run Detection Logic

Handles first-run detection, wizard state management, and onboarding flow.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from sqlalchemy import select

from app.db.models import OnboardingState, User, utc_now

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session


class OnboardingStatusDict(TypedDict):
    """Onboarding status response structure."""

    is_first_run: bool
    should_show_wizard: bool
    is_completed: bool
    wizard_skipped: bool
    redirect_to: str | None
    completed_at: datetime | None


class OnboardingService:
    """
    Service for managing onboarding state and first-run detection.

    This service handles:
    - Detecting first deployment (no active users in database)
    - Determining if onboarding wizard should be shown
    - Managing wizard completion and skip states
    - Persisting state to onboarding_state table
    """

    def __init__(self, session: Session) -> None:
        """Initialize onboarding service with database session."""
        self.session = session

    def is_first_run(self) -> bool:
        """
        Detect if this is the first deployment.

        Returns True if no active users exist in the database.
        Only checks for users with status='active' to ignore deleted/inactive accounts.
        """
        active_user_count = self.session.scalar(
            select(User.id).where(User.status == "active").limit(1)
        )
        return active_user_count is None

    def get_onboarding_status(self, user_id: str | None = None) -> OnboardingStatusDict:
        """
        Get current onboarding status.

        Args:
            user_id: Optional user ID to check their specific onboarding state

        Returns:
            Dictionary with:
            - is_first_run: Whether this is a fresh deployment
            - should_show_wizard: Whether to show the onboarding wizard
            - is_completed: Whether wizard has been completed
            - wizard_skipped: Whether user skipped the wizard (dismissed)
            - redirect_to: URL to redirect to (or None)
            - completed_at: When wizard was completed (or None)
        """
        first_run = self.is_first_run()

        # Check if any user has completed or dismissed onboarding
        is_completed = False
        wizard_skipped = False
        completed_at = None

        if user_id:
            # Check specific user's onboarding state
            state = self._get_user_state(user_id)
            if state:
                is_completed = state.completed_at is not None
                wizard_skipped = state.dismissed
                completed_at = state.completed_at

        # Show wizard if it's first run and not completed/skipped
        should_show_wizard = first_run and not is_completed and not wizard_skipped

        # Redirect to welcome page on first run
        redirect_to = "/onboarding/welcome" if should_show_wizard else None

        return {
            "is_first_run": first_run,
            "should_show_wizard": should_show_wizard,
            "is_completed": is_completed,
            "wizard_skipped": wizard_skipped,
            "redirect_to": redirect_to,
            "completed_at": completed_at,
        }

    def skip_wizard(self, user_id: str) -> OnboardingStatusDict:
        """
        Skip the onboarding wizard (for advanced users).

        Args:
            user_id: User ID who is skipping the wizard

        Returns:
            Updated onboarding status
        """
        state = self._get_or_create_state(user_id)

        # If already completed, don't override with skip
        if state.completed_at is None:
            state.dismissed = True
            state.updated_at = utc_now()
            self.session.commit()

        return self.get_onboarding_status(user_id)

    def mark_wizard_completed(self, user_id: str) -> OnboardingStatusDict:
        """
        Mark the onboarding wizard as completed.

        Args:
            user_id: User ID who completed the wizard

        Returns:
            Updated onboarding status
        """
        state = self._get_or_create_state(user_id)

        state.completed_at = utc_now()
        state.updated_at = state.completed_at
        state.dismissed = False
        state.current_step = 7  # All 7 steps completed
        self.session.commit()

        return self.get_onboarding_status(user_id)

    def _get_user_state(self, user_id: str) -> OnboardingState | None:
        """Get onboarding state for a specific user."""
        return self.session.scalar(
            select(OnboardingState).where(OnboardingState.user_id == user_id)
        )

    def _get_or_create_state(self, user_id: str) -> OnboardingState:
        """Get or create onboarding state for a user."""
        state = self._get_user_state(user_id)
        if state is not None:
            return state

        state = OnboardingState(
            user_id=user_id,
            current_step=0,
            completed_steps=[],
            dismissed=False,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self.session.add(state)
        self.session.flush()
        return state

