from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import AUTH_HEADERS


def test_plugin_marketplace_install_is_organization_scoped() -> None:
    client = TestClient(app)

    installed = client.post(
        "/api/plugins/marketplace/release-prompt-pack/install",
        headers=AUTH_HEADERS,
        json={"enabled": True, "config_json": {"review_gate": "beta"}},
    )
    assert installed.status_code == 200
    assert installed.json()["install_state"] == "installed"

    same_org = client.get("/api/plugins/marketplace", headers=AUTH_HEADERS)
    assert same_org.status_code == 200
    release_plugin = next(
        item for item in same_org.json()["items"] if item["id"] == "release-prompt-pack"
    )
    assert release_plugin["install_state"] == "installed"
    assert release_plugin["config_json"]["review_gate"] == "beta"

    other_org = client.get(
        "/api/plugins/marketplace",
        headers={"Authorization": "Bearer dev-other-org-token"},
    )
    assert other_org.status_code == 200
    other_release_plugin = next(
        item for item in other_org.json()["items"] if item["id"] == "release-prompt-pack"
    )
    assert other_release_plugin["install_state"] == "available"


def test_prompt_templates_support_custom_and_plugin_templates() -> None:
    client = TestClient(app)

    created = client.post(
        "/api/plugins/prompt-templates",
        headers=AUTH_HEADERS,
        json={
            "id": "my-release-template",
            "name": "自定义发布模板",
            "description": "Summarize release readiness.",
            "body": "请检查 {{run_id}} 的发布风险。",
            "tags": ["release"],
        },
    )
    assert created.status_code == 200
    assert created.json()["id"] == "my-release-template"

    client.post(
        "/api/plugins/marketplace/release-prompt-pack/install",
        headers=AUTH_HEADERS,
        json={"enabled": True, "config_json": {}},
    )

    listed = client.get("/api/plugins/prompt-templates", headers=AUTH_HEADERS)
    assert listed.status_code == 200
    templates = {item["id"]: item for item in listed.json()["items"]}
    assert templates["release-readiness"]["source"] == "built-in"
    assert templates["my-release-template"]["source"] == "custom"
    assert templates["plugin-release-risk-summary"]["source"] == "plugin"

    updated = client.put(
        "/api/plugins/prompt-templates/my-release-template",
        headers=AUTH_HEADERS,
        json={
            "name": "自定义发布模板 v2",
            "description": "Updated",
            "body": "请输出阻塞项。",
            "tags": ["release", "risk"],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "自定义发布模板 v2"

    deleted = client.delete(
        "/api/plugins/prompt-templates/my-release-template",
        headers=AUTH_HEADERS,
    )
    assert deleted.status_code == 200
    assert "my-release-template" not in {item["id"] for item in deleted.json()["items"]}
