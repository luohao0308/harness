import json

from sqlalchemy.orm import Session

from app.agents.model_gateway import ModelRequest, ModelResponse
from app.agents.specialist_llm_selector import SpecialistLLMSelector
from app.agents.specialists import ensure_system_specialists
from app.db.models import SystemSetting
from tests.test_subagents import create_task


class StaticSelectorGateway:
    def __init__(self, payload: dict | str) -> None:
        self.payload = payload
        self.requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        content = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        return ModelResponse(
            content=content,
            model_provider=request.model_provider,
            model_name=request.model_name,
            usage={"prompt_tokens": 1, "completion_tokens": 1},
            raw_response={"mode": "selector-test"},
        )


def test_llm_selector_uses_high_confidence_model_choice(db_session: Session) -> None:
    ensure_system_specialists(db_session)
    task = create_task(db_session)

    outcome = SpecialistLLMSelector(
        db_session,
        organization_id=task.organization_id,
        gateway=StaticSelectorGateway(
            {
                "selected_slug": "safety-checker",
                "confidence": 0.93,
                "reasoning": "The step asks for policy review.",
                "alternative_slugs": ["code-reviewer"],
            }
        ),
    ).select(
        task=task,
        plan_step_key="safety",
        plan_step_description="Check release safety risks",
        match_text="plain release step without matching keywords",
    )

    assert outcome.specialist is not None
    assert outcome.specialist.slug == "safety-checker"
    assert outcome.decision.selector == "llm"
    assert outcome.decision.confidence == 0.93
    assert outcome.trace["resolved_by"] == "llm"


def test_llm_selector_falls_back_when_json_is_invalid(db_session: Session) -> None:
    ensure_system_specialists(db_session)
    task = create_task(db_session)

    outcome = SpecialistLLMSelector(
        db_session,
        organization_id=task.organization_id,
        gateway=StaticSelectorGateway("not-json"),
    ).select(
        task=task,
        plan_step_key="research",
        plan_step_description="Investigate references",
        match_text="research this release with citations",
    )

    assert outcome.specialist is not None
    assert outcome.specialist.slug == "researcher"
    assert outcome.decision.selector == "keyword"
    assert "llm_unavailable" in outcome.decision.reasoning


def test_llm_selector_can_be_disabled_per_org(db_session: Session) -> None:
    ensure_system_specialists(db_session)
    task = create_task(db_session)
    db_session.add(
        SystemSetting(
            organization_id=task.organization_id,
            key="settings.specialists",
            value_json={"use_llm_selector": False},
            updated_by="test",
        )
    )
    db_session.flush()
    gateway = StaticSelectorGateway(
        {"selected_slug": "safety-checker", "confidence": 1, "reasoning": "ignored"}
    )

    outcome = SpecialistLLMSelector(
        db_session,
        organization_id=task.organization_id,
        gateway=gateway,
    ).select(
        task=task,
        plan_step_key="review",
        plan_step_description="Review patch",
        match_text="code review this patch",
    )

    assert gateway.requests == []
    assert outcome.specialist is not None
    assert outcome.specialist.slug == "code-reviewer"
    assert outcome.decision.selector == "keyword"
    assert outcome.decision.reasoning == "llm_selector_disabled"
