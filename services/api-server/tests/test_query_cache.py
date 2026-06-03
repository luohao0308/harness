from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cache.invalidation import entity_version
from app.cache.query_cache import query_cache
from app.db.models import Agent
from app.main import app
from tests.conftest import AUTH_HEADERS


def test_list_agents_cache_hits_and_invalidates_after_create(
    db_session: Session,
    monkeypatch: MonkeyPatch,
) -> None:
    _force_memory_cache(monkeypatch)
    client = TestClient(app)

    first = client.get("/api/agents", headers=AUTH_HEADERS, params={"limit": 20})
    assert first.status_code == 200
    first_payload = first.json()
    first_names = {item["id"] for item in first_payload["items"]}
    assert "cache-agent" not in first_names
    assert query_cache.get("agents:v1:dev-org:list:20:first") is not None

    second = client.get("/api/agents", headers=AUTH_HEADERS, params={"limit": 20})
    assert second.status_code == 200
    assert second.json() == first_payload

    created = client.post(
        "/api/agents",
        headers=AUTH_HEADERS,
        json={
            "id": "cache-agent",
            "name": "Cache Agent",
            "description": "Cache invalidation test",
            "role": "researcher",
            "model_provider": "default",
            "model_name": "default",
            "system_prompt": "Return concise evidence.",
            "tools_json": ["read_file"],
            "routing_tags": ["cache"],
            "max_parallel_assignments": 1,
        },
    )
    assert created.status_code == 201
    assert entity_version(db_session, organization_id="dev-org", entity="agents") == 2

    after_create = client.get("/api/agents", headers=AUTH_HEADERS, params={"limit": 20})
    assert after_create.status_code == 200
    assert "cache-agent" in {item["id"] for item in after_create.json()["items"]}
    assert query_cache.get("agents:v2:dev-org:list:20:first") is not None


def test_cached_agent_list_is_scoped_by_organization(
    db_session: Session,
    monkeypatch: MonkeyPatch,
) -> None:
    _force_memory_cache(monkeypatch)
    db_session.add(
        Agent(
            id="other-org-agent",
            organization_id="other-org",
            name="Other Org Agent",
            description="Must not leak through cache",
            role="researcher",
            status="ACTIVE",
            model_provider="default",
            model_name="default",
            system_prompt="Do not leak.",
            tools_json=[],
            routing_tags=[],
            max_parallel_assignments=1,
        )
    )
    db_session.commit()

    client = TestClient(app)
    dev_response = client.get("/api/agents", headers=AUTH_HEADERS, params={"limit": 20})
    other_response = client.get(
        "/api/agents",
        headers={"Authorization": "Bearer dev-other-org-token"},
        params={"limit": 20},
    )

    assert dev_response.status_code == 200
    assert other_response.status_code == 200
    assert "other-org-agent" not in {item["id"] for item in dev_response.json()["items"]}
    assert "other-org-agent" in {item["id"] for item in other_response.json()["items"]}
    assert db_session.execute(select(Agent).where(Agent.id == "other-org-agent")).scalar_one()


def test_agent_list_cache_invalidates_after_token_optimizer_selection(
    db_session: Session,
    monkeypatch: MonkeyPatch,
) -> None:
    _force_memory_cache(monkeypatch)
    client = TestClient(app)

    first = client.get("/api/agents", headers=AUTH_HEADERS, params={"limit": 20})
    assert first.status_code == 200
    default_before = next(item for item in first.json()["items"] if item["id"] == "default")
    assert not any(
        item["capability_key"] == "builtin:context-optimizer:balanced"
        for item in default_before["capability_attachments"]
    )
    assert query_cache.get("agents:v1:dev-org:list:20:first") is not None

    selected = client.post(
        "/api/agents/default/token-optimizer",
        headers=AUTH_HEADERS,
        json={"preset_id": "balanced"},
    )

    assert selected.status_code == 200
    assert entity_version(db_session, organization_id="dev-org", entity="agents") == 2
    after_selection = client.get("/api/agents", headers=AUTH_HEADERS, params={"limit": 20})
    assert after_selection.status_code == 200
    default_after = next(
        item for item in after_selection.json()["items"] if item["id"] == "default"
    )
    assert any(
        item["capability_key"] == "builtin:context-optimizer:balanced"
        and item["enabled"] is True
        for item in default_after["capability_attachments"]
    )
    assert query_cache.get("agents:v2:dev-org:list:20:first") is not None


def _force_memory_cache(monkeypatch: MonkeyPatch) -> None:
    query_cache.clear_memory()
    monkeypatch.setattr(query_cache, "_redis", None)
    monkeypatch.setattr(query_cache, "_redis_failed", True)
