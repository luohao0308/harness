from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    OnboardingCompleteRequest,
    OnboardingStateResponse,
    OnboardingStateUpdateRequest,
    OnboardingStatusResponse,
    WizardCompleteStepRequest,
    WizardStateResponse,
    WizardTransitionRequest,
)
from app.db.models import UserOnboardingState, utc_now
from app.db.session import get_db_session
from app.demo.seed_data import sync_onboarding_demo_state
from app.security.auth import Principal, require_role
from app.services.onboarding_service import OnboardingService

router = APIRouter(prefix="/onboarding", tags=["onboarding"])
DbSession = Annotated[Session, Depends(get_db_session)]


@router.get(
    "/status",
    response_model=OnboardingStatusResponse,
    summary="Get onboarding status (first-run detection)",
)
def get_onboarding_status(session: DbSession) -> dict:
    """
    Get onboarding status - detects first deployment and wizard state.

    Story 1.1: First-Run Detection Logic
    - Detects first deployment (no admin users in database)
    - Returns redirect URL for first access
    - Indicates if wizard was completed or skipped
    """
    service = OnboardingService(session)
    return service.get_onboarding_status()


@router.get(
    "/state",
    response_model=OnboardingStateResponse,
    summary="查询当前用户引导状态",
)
def get_onboarding_state(session: DbSession, principal: Principal) -> UserOnboardingState:
    require_role(principal, {"admin", "engineer", "operator"})
    state = sync_onboarding_demo_state(
        session,
        organization_id=principal.organization_id,
        user_id=principal.user_id,
    )
    session.commit()
    session.refresh(state)
    return state


@router.patch(
    "/state",
    response_model=OnboardingStateResponse,
    summary="更新当前用户引导进度",
)
def update_onboarding_state(
    payload: OnboardingStateUpdateRequest,
    session: DbSession,
    principal: Principal,
) -> UserOnboardingState:
    require_role(principal, {"admin", "engineer", "operator"})
    state = _get_or_create_state(session=session, principal=principal)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(state, key, value)
    state.updated_at = utc_now()
    session.commit()
    session.refresh(state)
    return state


@router.post(
    "/complete",
    response_model=OnboardingStateResponse,
    summary="完成当前用户引导",
)
def complete_onboarding(
    payload: OnboardingCompleteRequest,
    session: DbSession,
    principal: Principal,
) -> UserOnboardingState:
    require_role(principal, {"admin", "engineer", "operator"})
    state = _get_or_create_state(session=session, principal=principal)
    state.current_step = 4
    state.completed = True
    state.skipped = False
    if payload.agent_id is not None:
        state.agent_id = payload.agent_id
    if payload.demo_task_id is not None:
        state.demo_task_id = payload.demo_task_id
    state.completed_at = utc_now()
    state.updated_at = state.completed_at
    session.commit()
    session.refresh(state)
    return state


def _get_or_create_state(*, session: Session, principal) -> UserOnboardingState:
    state = session.execute(
        select(UserOnboardingState).where(
            UserOnboardingState.organization_id == principal.organization_id,
            UserOnboardingState.user_id == principal.user_id,
        )
    ).scalar_one_or_none()
    if state is not None:
        return state
    state = UserOnboardingState(
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        current_step=1,
        completed=False,
        skipped=False,
        demo_loaded=False,
        provider_json={},
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    session.add(state)
    session.flush()
    return state


# Story 1.2: Wizard State Persistence Endpoints


@router.get(
    "/wizard/state/{user_id}",
    response_model=WizardStateResponse,
    summary="Get wizard state for user (Story 1.2)",
)
def get_wizard_state(user_id: str, session: DbSession) -> dict:
    """
    Get current wizard state for a user.

    Story 1.2: Returns persisted wizard state including:
    - current_step: Current step in wizard (0-7)
    - completed_steps: Array of completed step numbers
    - is_completed: Whether wizard is fully completed
    - Supports browser refresh - state persists across sessions
    """
    service = OnboardingService(session)
    return service.get_wizard_state(user_id)


@router.post(
    "/wizard/transition",
    response_model=WizardStateResponse,
    summary="Transition to wizard step (Story 1.2)",
)
def transition_wizard_step(
    payload: WizardTransitionRequest,
    session: DbSession,
    principal: Principal,
) -> dict:
    """
    Transition user to a specific wizard step.

    Story 1.2: Updates current_step without marking previous step as completed.
    Used for navigation between wizard steps.
    """
    require_role(principal, {"admin", "engineer", "operator"})
    service = OnboardingService(session)
    return service.transition_to_step(principal.user_id, payload.step)


@router.post(
    "/wizard/complete-step",
    response_model=WizardStateResponse,
    summary="Mark wizard step as completed (Story 1.2)",
)
def complete_wizard_step(
    payload: WizardCompleteStepRequest,
    session: DbSession,
    principal: Principal,
) -> dict:
    """
    Mark a specific wizard step as completed.

    Story 1.2: Adds step to completed_steps array.
    Automatically marks wizard as complete when all 7 steps are done.
    """
    require_role(principal, {"admin", "engineer", "operator"})
    service = OnboardingService(session)
    return service.complete_step(principal.user_id, payload.step)

