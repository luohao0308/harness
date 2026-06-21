from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Agent, AgentVersion
from app.main import app

AUTH_HEADERS = {"Authorization": "Bearer dev-engineer-token"}
OTHER_ORG_HEADERS = {"Authorization": "Bearer dev-other-org-token"}


def test_agent_version_create_list_and_monotonic_numbers(db_session: Session) -> None:
    client = TestClient(app)

    first = client.post(
        "/api/agents/default/versions",
        headers=AUTH_HEADERS,
        json={"activate": True},
    )
    second = client.post(
        "/api/agents/default/versions",
        headers=AUTH_HEADERS,
        json={},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["version_number"] == 1
    assert first.json()["is_active"] is True
    assert second.json()["version_number"] == 2
    assert second.json()["is_active"] is False
    assert first.json()["config_snapshot"]["system_prompt"]

    listed = client.get("/api/agents/default/versions", headers=AUTH_HEADERS)
    assert listed.status_code == 200
    assert [item["version_number"] for item in listed.json()["items"]] == [2, 1]


def test_agent_version_activation_restores_agent_config(db_session: Session) -> None:
    client = TestClient(app)
    version_one = client.post(
        "/api/agents/default/versions",
        headers=AUTH_HEADERS,
        json={"activate": True},
    ).json()
    agent = db_session.get(Agent, "default")
    assert agent is not None
    original_prompt = agent.system_prompt

    agent.system_prompt = "Temporary broken prompt"
    agent.model_provider = "broken-provider"
    agent.tools_json = ["broken_tool"]
    db_session.commit()
    version_two = client.post(
        "/api/agents/default/versions",
        headers=AUTH_HEADERS,
        json={},
    ).json()

    activated = client.patch(
        f"/api/agents/default/versions/{version_one['id']}/activate",
        headers=AUTH_HEADERS,
    )

    assert activated.status_code == 200
    assert activated.json()["id"] == version_one["id"]
    assert activated.json()["is_active"] is True
    db_session.refresh(agent)
    assert agent.system_prompt == original_prompt
    assert agent.model_provider == version_one["config_snapshot"]["model_provider"]
    assert agent.tools_json == version_one["config_snapshot"]["tools_json"]

    versions = db_session.execute(select(AgentVersion)).scalars().all()
    active_ids = [version.id for version in versions if version.is_active]
    assert active_ids == [version_one["id"]]
    assert version_two["id"] not in active_ids


def test_agent_versions_are_scoped_to_principal_org(db_session: Session) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/versions",
        headers=AUTH_HEADERS,
        json={},
    )
    assert created.status_code == 201

    other_list = client.get("/api/agents/default/versions", headers=OTHER_ORG_HEADERS)
    assert other_list.status_code == 200
    assert other_list.json()["items"] == []

    other_activate = client.patch(
        f"/api/agents/default/versions/{created.json()['id']}/activate",
        headers=OTHER_ORG_HEADERS,
    )
    assert other_activate.status_code == 404
