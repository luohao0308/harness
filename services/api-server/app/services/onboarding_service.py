"""
Onboarding Service - Stories 1.1 & 1.2

Story 1.1: First-Run Detection Logic
Story 1.2: Wizard State Persistence

Handles first-run detection, wizard state management, step transitions, and onboarding flow.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, TypedDict

from sqlalchemy import select

from app.db.models import OnboardingState, User, utc_now

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class OnboardingStatusDict(TypedDict):
    """Onboarding status response structure."""

    is_first_run: bool
    should_show_wizard: bool
    is_completed: bool
    wizard_skipped: bool
    redirect_to: str | None
    completed_at: datetime | None


class WizardStateDict(TypedDict):
    """Wizard state response structure for Story 1.2."""

    user_id: str
    current_step: int
    completed_steps: list[int]
    is_completed: bool
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class OnboardingService:
    """
    Service for managing onboarding state and first-run detection.

    This service handles:
    - Story 1.1: Detecting first deployment (no active users in database)
    - Story 1.1: Determining if onboarding wizard should be shown
    - Story 1.1: Managing wizard completion and skip states
    - Story 1.2: Step transitions with state persistence
    - Story 1.2: Completed steps tracking
    - Story 1.2: Browser refresh state recovery
    - Persisting state to onboarding_state table

    Wizard has 7 steps total (steps 1-7):
    1. Welcome & Setup
    2. Model Provider Configuration
    3. Create First Agent
    4. Knowledge Base Setup
    5. Tool Configuration
    6. Run First Task
    7. Review & Complete
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

    # Story 1.2: Wizard State Persistence Methods

    def transition_to_step(self, user_id: str, step: int) -> WizardStateDict:
        """
        Transition user to a specific wizard step.

        Updates current_step without marking previous step as completed.
        Useful for navigation between steps.

        Args:
            user_id: User ID
            step: Target step number (0-7, where 0 is initial state)

        Returns:
            Updated wizard state

        Raises:
            ValueError: If step is out of valid range
        """
        if not (0 <= step <= 7):
            raise ValueError("Step must be between 0 and 7")

        state = self._get_or_create_state(user_id)
        state.current_step = step
        state.updated_at = utc_now()

        # Check if all steps completed (auto-complete wizard)
        if step == 7 and len(state.completed_steps) == 7:
            state.completed_at = utc_now()
            state.updated_at = state.completed_at

        self.session.commit()

        return self.get_wizard_state(user_id)

    def complete_step(self, user_id: str, step: int) -> WizardStateDict:
        """
        Mark a specific step as completed.

        Adds step to completed_steps array if not already present.
        Advances current_step when completing a later step.

        Args:
            user_id: User ID
            step: Step number to mark complete (1-7)

        Returns:
            Updated wizard state

        Raises:
            ValueError: If step is out of valid range
        """
        if not (1 <= step <= 7):
            raise ValueError("Step must be between 1 and 7")

        state = self._get_or_create_state(user_id)

        # Add to completed_steps if not already there
        if step not in state.completed_steps:
            state.completed_steps = sorted([*state.completed_steps, step])

        state.current_step = max(state.current_step, step)
        state.updated_at = utc_now()

        # If all 7 steps completed, mark wizard as complete
        if len(state.completed_steps) == 7 and state.current_step == 7:
            state.completed_at = utc_now()
            state.updated_at = state.completed_at

        self.session.commit()

        return self.get_wizard_state(user_id)

    def get_wizard_state(self, user_id: str) -> WizardStateDict:
        """
        Get current wizard state for a user.

        Retrieves persisted state from database, supporting browser refresh.

        Args:
            user_id: User ID

        Returns:
            Complete wizard state including:
            - user_id: User identifier
            - current_step: Current step in wizard (0-7)
            - completed_steps: Array of completed step numbers
            - is_completed: Whether wizard is fully completed
            - completed_at: Completion timestamp (or None)
            - created_at: State creation timestamp
            - updated_at: Last update timestamp
        """
        state = self._get_or_create_state(user_id)

        return {
            "user_id": state.user_id,
            "current_step": state.current_step,
            "completed_steps": state.completed_steps,
            "is_completed": state.completed_at is not None,
            "completed_at": self._as_utc(state.completed_at),
            "created_at": self._as_utc(state.created_at),
            "updated_at": self._as_utc(state.updated_at),
        }

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

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
