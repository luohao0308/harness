from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AdminAuditEvent, AgentRun, SubagentOutput, Task, TeamEvent, TeamTask
from app.main import app
from tests.conftest import AUTH_HEADERS
from tests.test_teams import _create_team


def test_team_task_projects_to_enterprise_subagent_surfaces(db_session: Session) -> None:
    client = TestClient(app)
    team = _create_team(client, name="Enterprise Team Bridge")

    spawn = client.post(
        f"/api/teams/{team['id']}/tools/team_spawn_agent",
        headers=AUTH_HEADERS,
        json={
            "from_agent_slot_id": "leader",
            "args": {"name": "Review Agent", "agent_id": "default"},
        },
    )
    assert spawn.status_code == 200, spawn.text

    refreshed_team = client.get(f"/api/teams/{team['id']}", headers=AUTH_HEADERS).json()
    teammate = next(
        agent for agent in refreshed_team["agents"] if agent["agent_name"] == "Review Agent"
    )

    created = client.post(
        f"/api/teams/{team['id']}/tasks",
        headers=AUTH_HEADERS,
        json={
            "subject": "Review release chain",
            "description": "审查企业交付链路并报告风险。",
            "owner_slot_id": teammate["slot_id"],
        },
    )
    assert created.status_code == 201, created.text
    task_payload = created.json()
    projection = task_payload["metadata_json"]["enterprise_projection"]
    assert projection["source"] == "team_mode_enterprise_projection"
    assert projection["team_id"] == team["id"]
    assert projection["team_task_id"] == task_payload["id"]
    assert projection["team_agent_slot_id"] == teammate["slot_id"]
    assert projection["run_id"]
    assert projection["subagent_id"]
    assert projection["specialist_slug"] in {
        "code-reviewer",
        "researcher",
        "safety-checker",
        "synthesizer",
    }
    audit_events = db_session.execute(
        select(AdminAuditEvent).where(
            AdminAuditEvent.action == "team.subagent.projected",
            AdminAuditEvent.resource_type == "team",
            AdminAuditEvent.resource_id == team["id"],
        )
    ).scalars().all()
    assert len(audit_events) == 1
    assert audit_events[0].payload_json == {
        "source": "team_mode_enterprise_projection",
        "team_id": team["id"],
        "team_task_id": task_payload["id"],
        "team_agent_slot_id": teammate["slot_id"],
        "team_agent_id": "default",
        "team_agent_name": "Review Agent",
        "run_id": projection["run_id"],
        "subagent_id": projection["subagent_id"],
        "specialist_id": projection["specialist_id"],
        "specialist_slug": projection["specialist_slug"],
    }

    subagents = client.get("/api/subagents", headers=AUTH_HEADERS)
    assert subagents.status_code == 200
    projected = next(
        item for item in subagents.json()["items"] if item["id"] == projection["subagent_id"]
    )
    assert projected["task_id"] == projection["run_id"]
    assert projected["context_json"]["team_id"] == team["id"]
    assert projected["context_json"]["team_agent_slot_id"] == teammate["slot_id"]

    workspace = client.get(
        f"/api/agents/runs/{projection['run_id']}/workspace",
        headers=AUTH_HEADERS,
    )
    assert workspace.status_code == 200, workspace.text
    workspace_payload = workspace.json()
    assert workspace_payload["run"]["id"] == projection["run_id"]
    assert workspace_payload["run"]["status"] == "CREATED"
    workspace_subagent = next(
        item for item in workspace_payload["subagents"] if item["id"] == projection["subagent_id"]
    )
    assert workspace_subagent["context_json"]["source"] == "team_mode_enterprise_projection"
    assert workspace_subagent["context_json"]["team_task_id"] == task_payload["id"]

    in_progress = client.patch(
        f"/api/teams/{team['id']}/tasks/{task_payload['id']}",
        headers=AUTH_HEADERS,
        json={"status": "in_progress"},
    )
    assert in_progress.status_code == 200, in_progress.text
    in_progress_projection = in_progress.json()["metadata_json"]["enterprise_projection"]
    assert in_progress_projection["subagent_id"] == projection["subagent_id"]

    completed = client.patch(
        f"/api/teams/{team['id']}/tasks/{task_payload['id']}",
        headers=AUTH_HEADERS,
        json={"status": "completed"},
    )
    assert completed.status_code == 200, completed.text
    completed_projection = completed.json()["metadata_json"]["enterprise_projection"]
    assert completed_projection["run_id"] == projection["run_id"]

    db_session.expire_all()
    team_task = db_session.get(TeamTask, task_payload["id"])
    assert team_task is not None
    task_projection = team_task.metadata_json["enterprise_projection"]
    assert task_projection["subagent_id"] == projection["subagent_id"]
    agent_run = db_session.get(AgentRun, projection["subagent_id"])
    assert agent_run is not None
    assert agent_run.status == "SUCCESS"
    assert agent_run.context_json["team_task_status"] == "completed"
    output = db_session.execute(
        select(SubagentOutput).where(SubagentOutput.agent_run_id == projection["subagent_id"])
    ).scalar_one()
    assert output.output_json
    assert output.specialist_id == projection["specialist_id"]

    completed_again = client.patch(
        f"/api/teams/{team['id']}/tasks/{task_payload['id']}",
        headers=AUTH_HEADERS,
        json={"status": "completed"},
    )
    assert completed_again.status_code == 200
    repeated_audit_events = db_session.execute(
        select(AdminAuditEvent).where(
            AdminAuditEvent.action == "team.subagent.projected",
            AdminAuditEvent.resource_type == "team",
            AdminAuditEvent.resource_id == team["id"],
        )
    ).scalars().all()
    assert len(repeated_audit_events) == 1
    output_count = db_session.execute(
        select(SubagentOutput).where(SubagentOutput.agent_run_id == projection["subagent_id"])
    ).scalars().all()
    assert len(output_count) == 1

    stats = client.get(
        f"/api/subagent-specialists/{projection['specialist_id']}/stats",
        headers=AUTH_HEADERS,
    )
    assert stats.status_code == 200, stats.text
    assert stats.json()["total_invocations"] >= 1
    assert stats.json()["success_count"] >= 1

    summary = client.get("/api/observability/summary", headers=AUTH_HEADERS)
    assert summary.status_code == 200
    assert {"name": "SUCCESS", "count": 1} in summary.json()["subagents_by_status"]

    events = db_session.execute(
        select(TeamEvent).where(
            TeamEvent.team_id == team["id"],
            TeamEvent.event_type.in_(["TEAM_TASK_CREATED", "TEAM_TASK_UPDATED"]),
        )
    ).scalars().all()
    assert events


def test_team_task_projection_owner_removal_and_reassignment_do_not_reactivate_cancelled_run(
    db_session: Session,
) -> None:
    client = TestClient(app)
    team = _create_team(client, name="Enterprise Team Reassignment")

    spawn = client.post(
        f"/api/teams/{team['id']}/tools/team_spawn_agent",
        headers=AUTH_HEADERS,
        json={
            "from_agent_slot_id": "leader",
            "args": {"name": "Verifier Agent", "agent_id": "default"},
        },
    )
    assert spawn.status_code == 200, spawn.text
    teammate = next(
        agent
        for agent in client.get(f"/api/teams/{team['id']}", headers=AUTH_HEADERS).json()["agents"]
        if agent["agent_name"] == "Verifier Agent"
    )

    created = client.post(
        f"/api/teams/{team['id']}/tasks",
        headers=AUTH_HEADERS,
        json={
            "subject": "Verify release bridge",
            "description": "验证 Team 到子智能体投影生命周期。",
            "owner_slot_id": teammate["slot_id"],
        },
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    first_projection = created.json()["metadata_json"]["enterprise_projection"]

    unassigned = client.patch(
        f"/api/teams/{team['id']}/tasks/{task_id}",
        headers=AUTH_HEADERS,
        json={"owner_slot_id": None},
    )
    assert unassigned.status_code == 200, unassigned.text
    cancelled_projection = unassigned.json()["metadata_json"]["enterprise_projection"]
    assert cancelled_projection["subagent_id"] == first_projection["subagent_id"]
    assert cancelled_projection["projection_status"] == "cancelled"
    assert cancelled_projection["team_agent_slot_id"] is None

    db_session.expire_all()
    first_agent_run = db_session.get(AgentRun, first_projection["subagent_id"])
    assert first_agent_run is not None
    assert first_agent_run.status == "CANCELLED"
    assert first_agent_run.context_json["projection_cancelled"] is True
    first_projection_task = db_session.get(Task, first_projection["run_id"])
    assert first_projection_task is not None
    assert first_projection_task.status == "CANCELLED"

    reassigned = client.patch(
        f"/api/teams/{team['id']}/tasks/{task_id}",
        headers=AUTH_HEADERS,
        json={"owner_slot_id": teammate["slot_id"]},
    )
    assert reassigned.status_code == 200, reassigned.text
    second_projection = reassigned.json()["metadata_json"]["enterprise_projection"]
    assert second_projection["subagent_id"] != first_projection["subagent_id"]
    assert second_projection["run_id"] != first_projection["run_id"]
    assert second_projection["team_agent_slot_id"] == teammate["slot_id"]
    assert "projection_status" not in second_projection
    assert "cancelled_at" not in second_projection

    db_session.expire_all()
    second_agent_run = db_session.get(AgentRun, second_projection["subagent_id"])
    assert second_agent_run is not None
    assert second_agent_run.status == "PENDING"
    assert "projection_cancelled" not in second_agent_run.context_json

    deleted = client.patch(
        f"/api/teams/{team['id']}/tasks/{task_id}",
        headers=AUTH_HEADERS,
        json={"status": "deleted"},
    )
    assert deleted.status_code == 200, deleted.text
    deleted_projection = deleted.json()["metadata_json"]["enterprise_projection"]
    assert deleted_projection["subagent_id"] == second_projection["subagent_id"]
    assert deleted_projection["projection_status"] == "cancelled"

    db_session.expire_all()
    second_agent_run = db_session.get(AgentRun, second_projection["subagent_id"])
    assert second_agent_run is not None
    assert second_agent_run.status == "CANCELLED"

    projected_audits = db_session.execute(
        select(AdminAuditEvent).where(
            AdminAuditEvent.action == "team.subagent.projected",
            AdminAuditEvent.resource_type == "team",
            AdminAuditEvent.resource_id == team["id"],
        )
    ).scalars().all()
    cancelled_audits = db_session.execute(
        select(AdminAuditEvent).where(
            AdminAuditEvent.action == "team.subagent.projection_cancelled",
            AdminAuditEvent.resource_type == "team",
            AdminAuditEvent.resource_id == team["id"],
        )
    ).scalars().all()
    assert len(projected_audits) == 2
    assert len(cancelled_audits) == 2
