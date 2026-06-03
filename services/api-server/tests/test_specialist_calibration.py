from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agents.specialists import ensure_system_specialists
from app.agents.subagent_manager import SubagentManager
from app.db.models import SpecialistSelectionDecision, SubagentSpecialist, utc_now
from app.main import app
from tests.conftest import AUTH_HEADERS
from tests.test_subagents import create_task


def test_specialist_calibration_reports_low_sample_and_buckets(db_session: Session) -> None:
    ensure_system_specialists(db_session)
    task = create_task(db_session)
    specialist = db_session.query(SubagentSpecialist).filter_by(slug="code-reviewer").first()
    assert specialist is not None
    decision = SpecialistSelectionDecision(
        organization_id=task.organization_id,
        task_id=task.id,
        plan_step_key="review",
        selected_slug="code-reviewer",
        confidence=0.85,
        reasoning="high confidence",
        selector="llm",
        alternative_slugs_json=["safety-checker"],
        candidate_slugs_json=["code-reviewer", "safety-checker"],
        trace_json={},
        created_at=utc_now(),
    )
    db_session.add(decision)
    db_session.flush()
    run = SubagentManager(db_session).spawn(
        task=task,
        assignment={"step_key": "review", "specialist_selection_decision_id": decision.id},
        specialist=specialist,
    )
    SubagentManager(db_session).finalize_with_output(
        agent_run=run,
        raw_output_dict={"issues": [], "summary": "clean"},
    )
    db_session.commit()

    response = TestClient(app).get(
        "/api/subagent-specialists/calibration?window=30d",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision_count"] == 1
    assert body["low_sample"] is True
    assert body["ece"] is None
    high_bucket = body["buckets"][4]
    assert high_bucket["decision_count"] == 1
    assert high_bucket["success_count"] == 1
    assert high_bucket["success_rate"] == 1.0


def test_specialist_calibration_ignores_runs_from_other_tasks(db_session: Session) -> None:
    ensure_system_specialists(db_session)
    task = create_task(db_session)
    other_task = create_task(db_session, organization_id="other-org")
    specialist = db_session.query(SubagentSpecialist).filter_by(slug="code-reviewer").first()
    assert specialist is not None
    decision = SpecialistSelectionDecision(
        organization_id=task.organization_id,
        task_id=task.id,
        plan_step_key="review",
        selected_slug="code-reviewer",
        confidence=0.85,
        reasoning="high confidence",
        selector="llm",
        alternative_slugs_json=[],
        candidate_slugs_json=["code-reviewer"],
        trace_json={},
        created_at=utc_now(),
    )
    db_session.add(decision)
    db_session.flush()
    other_run = SubagentManager(db_session).spawn(
        task=other_task,
        assignment={"step_key": "review", "specialist_selection_decision_id": decision.id},
        specialist=specialist,
    )
    SubagentManager(db_session).finalize_with_output(
        agent_run=other_run,
        raw_output_dict={"issues": [], "summary": "clean"},
    )
    db_session.commit()

    response = TestClient(app).get(
        "/api/subagent-specialists/calibration?window=30d",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    high_bucket = response.json()["buckets"][4]
    assert high_bucket["decision_count"] == 1
    assert high_bucket["success_count"] == 0
    assert high_bucket["success_rate"] is None
