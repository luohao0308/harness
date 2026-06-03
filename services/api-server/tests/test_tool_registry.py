import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.tools import _runtime_endpoint_errors
from app.db.models import (
    Agent,
    AgentCapabilityAttachment,
    AgentEvent,
    Capability,
    CapabilityVersion,
    Task,
    ToolCall,
)
from app.knowledge_dify import read_connector_secret_ref
from app.main import app
from app.tools import capabilities as capabilities_module
from app.tools import marketplace as marketplace_module
from app.tools.capabilities import CapabilityRegistry
from tests.conftest import AUTH_HEADERS


def _create_task(client: TestClient) -> str:
    response = client.post(
        "/api/tasks",
        headers=AUTH_HEADERS,
        json={
            "title": "MCP runtime",
            "goal": "Exercise MCP-shaped tools",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_runtime_seconds": 1800,
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _create_agent(db_session: Session, *, agent_id: str, tools: list[str]) -> None:
    db_session.add(
        Agent(
            id=agent_id,
            organization_id=None,
            name=f"{agent_id} Agent",
            description="Capability-scoped test agent",
            role="tester",
            status="ACTIVE",
            model_provider="default",
            model_name="default",
            system_prompt="Use only attached tools.",
            tools_json=tools,
            routing_tags=[],
        )
    )
    db_session.flush()
    CapabilityRegistry(db_session, "dev-org").backfill_agent_attachments(
        agent_id,
        attached_by="test",
    )


class _FakeBraveResponse:
    status_code = 200
    text = ""

    def json(self) -> dict:
        return {
            "web": {
                "results": [
                    {
                        "title": "MCP 教程 - Brave result",
                        "url": "https://example.com/mcp",
                        "description": "Model Context Protocol tutorial result",
                    }
                ]
            }
        }


def test_stdio_runtime_config_rejects_shell_fragments() -> None:
    assert _runtime_endpoint_errors(
        transport="stdio",
        endpoint_url=None,
        command="node",
    ) == []
    errors = _runtime_endpoint_errors(
        transport="stdio",
        endpoint_url=None,
        command="node -e 'bad'",
    )

    assert "single executable" in "; ".join(errors)


def test_tool_registry_exposes_builtin_and_mcp_tools() -> None:
    response = TestClient(app).get("/api/tools/registry", headers=AUTH_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    names = {item["name"] for item in payload["items"]}
    assert "read_file" in names
    assert "mcp_context_search" in names
    assert "mcp" in payload["sources"]
    mcp_tool = next(item for item in payload["items"] if item["name"] == "mcp_context_search")
    assert mcp_tool["source"] == "mcp"
    assert mcp_tool["mcp_server"] == "local-context"
    assert mcp_tool["mcp_method"] == "context.search"


def test_agent_scoped_tool_registry_reflects_attached_marketplace_mcp(
    db_session: Session,
    monkeypatch,
) -> None:
    _create_agent(db_session, agent_id="registry-agent", tools=[])
    client = TestClient(app)

    monkeypatch.setattr(
        capabilities_module,
        "download_remote_package_content",
        lambda _source_uri: pytest.fail("marketplace registry listing must not download sources"),
    )
    monkeypatch.setattr(
        capabilities_module,
        "_resolved_public_host_errors",
        lambda _host: pytest.fail("marketplace registry listing must not resolve hosts"),
    )

    before_attach = client.get(
        "/api/tools/registry?agent_id=registry-agent",
        headers=AUTH_HEADERS,
    )
    assert before_attach.status_code == 200
    assert "brave" not in {item["name"] for item in before_attach.json()["items"]}

    preflight = client.post(
        "/api/tools/capabilities/preflight/marketplace",
        headers=AUTH_HEADERS,
        json={
            "source_uri": "https://brave.com/search/api/",
            "pinned_ref": "marketplace-sha256:brave-registry",
            "marketplace_source": "smithery_mcp",
            "marketplace_item_id": "smithery-mcp::brave",
            "display_name": "Brave Search",
            "description": "Search the web through Brave Search.",
            "package_type": "mcp_server",
            "permissions": ["mcp:remote"],
            "manifest": {
                "name": "brave",
                "version": "1.0.0",
                "description": "Search the web through Brave Search.",
                "package_type": "mcp_server",
                "permissions": ["mcp:remote"],
                "transport": "http",
                "secret_refs": [],
                "mcp_server": {
                    "registry": "smithery_mcp",
                    "qualified_name": "brave",
                    "homepage": "https://brave.com/search/api/",
                },
            },
            "content": {"marketplace": {"source": "smithery_mcp"}},
        },
    )
    assert preflight.status_code == 201
    package_id = preflight.json()["package"]["id"]

    approved = client.post(
        f"/api/tools/capabilities/packages/{package_id}/approve",
        headers=AUTH_HEADERS,
        json={"reason": "registry metadata reviewed"},
    )
    assert approved.status_code == 200

    attached = client.post(
        f"/api/tools/capabilities/packages/{package_id}/attachments",
        headers=AUTH_HEADERS,
        json={"agent_id": "registry-agent", "enabled": True, "priority": 10},
    )
    assert attached.status_code == 201

    after_attach = client.get(
        "/api/tools/registry?agent_id=registry-agent",
        headers=AUTH_HEADERS,
    )

    assert after_attach.status_code == 200
    payload = after_attach.json()
    names = {item["name"] for item in payload["items"]}
    assert "brave" in names
    brave_tool = next(item for item in payload["items"] if item["name"] == "brave")
    assert brave_tool["source"] == "mcp"
    assert brave_tool["mcp_server"] == "brave"
    assert brave_tool["mcp_method"] == "search"
    assert "mcp" in payload["sources"]


def test_agent_scoped_tool_registry_keeps_marketplace_mcp_org_scoped(
    db_session: Session,
    monkeypatch,
) -> None:
    _create_agent(db_session, agent_id="shared-default-agent", tools=[])
    client = TestClient(app)
    monkeypatch.setattr(
        capabilities_module,
        "download_remote_package_content",
        lambda _source_uri: pytest.fail("marketplace registry listing must not download sources"),
    )
    monkeypatch.setattr(
        capabilities_module,
        "_resolved_public_host_errors",
        lambda _host: pytest.fail("marketplace registry listing must not resolve hosts"),
    )

    preflight = client.post(
        "/api/tools/capabilities/preflight/marketplace",
        headers=AUTH_HEADERS,
        json={
            "source_uri": "https://brave.com/search/api/",
            "pinned_ref": "marketplace-sha256:brave-org-scope",
            "marketplace_source": "smithery_mcp",
            "marketplace_item_id": "smithery-mcp::brave",
            "display_name": "Brave Search",
            "description": "Search the web through Brave Search.",
            "package_type": "mcp_server",
            "permissions": ["mcp:remote"],
            "manifest": {
                "name": "brave",
                "version": "1.0.0",
                "description": "Search the web through Brave Search.",
                "package_type": "mcp_server",
                "permissions": ["mcp:remote"],
                "transport": "http",
                "secret_refs": [],
                "mcp_server": {"qualified_name": "brave"},
            },
            "content": {"marketplace": {"source": "smithery_mcp"}},
        },
    )
    assert preflight.status_code == 201
    package_id = preflight.json()["package"]["id"]
    approved = client.post(
        f"/api/tools/capabilities/packages/{package_id}/approve",
        headers=AUTH_HEADERS,
        json={"reason": "registry metadata reviewed"},
    )
    assert approved.status_code == 200
    attached = client.post(
        f"/api/tools/capabilities/packages/{package_id}/attachments",
        headers=AUTH_HEADERS,
        json={"agent_id": "shared-default-agent", "enabled": True, "priority": 10},
    )
    assert attached.status_code == 201

    same_org = client.get(
        "/api/tools/registry?agent_id=shared-default-agent",
        headers=AUTH_HEADERS,
    )
    other_org = client.get(
        "/api/tools/registry?agent_id=shared-default-agent",
        headers={"Authorization": "Bearer dev-other-org-token"},
    )

    assert same_org.status_code == 200
    assert "brave" in {item["name"] for item in same_org.json()["items"]}
    assert other_org.status_code == 200
    assert "brave" not in {item["name"] for item in other_org.json()["items"]}


class _FakeMarketplaceResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeMarketplaceClient:
    def __init__(self, *_, **__) -> None:
        self.calls: list[tuple[str, dict]] = []

    def __enter__(self) -> "_FakeMarketplaceClient":
        return self

    def __exit__(self, *_args) -> None:
        return None

    def get(self, url: str, *, params: dict | None = None) -> _FakeMarketplaceResponse:
        self.calls.append((url, params or {}))
        if "registry.modelcontextprotocol.io" in url:
            return _FakeMarketplaceResponse(
                {
                    "servers": [
                        {
                            "server": {
                                "name": "io.github.example/search",
                                "title": "Example Search",
                                "description": "Search external knowledge.",
                                "version": "1.2.3",
                                "repository": {
                                    "url": "https://github.com/example/search-mcp",
                                    "source": "github",
                                },
                                "remotes": [
                                    {
                                        "type": "streamable-http",
                                        "url": "https://mcp.example.com",
                                    }
                                ],
                            },
                            "_meta": {
                                "io.modelcontextprotocol.registry/official": {
                                    "status": "active",
                                    "isLatest": True,
                                    "publishedAt": "2026-04-01T00:00:00Z",
                                }
                            },
                        }
                    ],
                    "metadata": {"count": 1},
                }
            )
        if url.endswith("/servers"):
            return _FakeMarketplaceResponse(
                {
                    "servers": [
                        {
                            "id": "server-1",
                            "qualifiedName": "smithery/github",
                            "displayName": "GitHub",
                            "description": "Connect Agent to GitHub",
                            "verified": True,
                            "useCount": 12,
                            "remote": True,
                            "isDeployed": True,
                            "homepage": "https://smithery.ai/servers/github",
                            "createdAt": "2026-02-01T00:00:00Z",
                        }
                    ],
                    "pagination": {"totalCount": 1},
                }
            )
        if url.endswith("/skills"):
            return _FakeMarketplaceResponse(
                {
                    "skills": [
                        {
                            "id": "skill-1",
                            "namespace": "acme",
                            "slug": "review",
                            "qualifiedName": "acme/review",
                            "displayName": "Review Skill",
                            "description": "Review code with policy.",
                            "categories": ["Coding"],
                            "gitUrl": "https://github.com/acme/review/tree/main/skill",
                            "qualityScore": 0.9,
                            "externalStars": 42,
                            "totalActivations": 7,
                            "verified": False,
                            "listed": True,
                            "createdAt": "2026-02-02T00:00:00Z",
                            "servers": ["smithery/github"],
                        }
                    ],
                    "pagination": {"totalCount": 1},
                }
            )
        return _FakeMarketplaceResponse({})


def test_capability_marketplace_aggregates_mcp_and_skill_sources(monkeypatch) -> None:
    fake_client = _FakeMarketplaceClient()
    monkeypatch.setattr(
        marketplace_module.httpx,
        "Client",
        lambda *args, **kwargs: fake_client,
    )

    response = TestClient(app).get(
        "/api/tools/capabilities/marketplace?kind=all&query=search&limit=10",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "all"
    assert payload["query"] == "search"
    assert payload["errors"] == []
    sources = {source["id"]: source for source in payload["sources"]}
    assert sources["official_mcp_registry"]["status"] == "ready"
    assert sources["smithery_mcp"]["status"] == "ready"
    assert sources["smithery_skills"]["status"] == "ready"
    names = {item["name"]: item for item in payload["items"]}
    assert names["io.github.example/search"]["install_mode"] == "marketplace_preflight"
    assert names["io.github.example/search"]["install_payload"]["package_type"] == "mcp_server"
    assert (
        names["io.github.example/search"]["install_payload"]["marketplace_source"]
        == "official_mcp_registry"
    )
    assert (
        names["io.github.example/search"]["install_payload"]["marketplace_item_id"]
        == "official-mcp::io.github.example/search@1.2.3"
    )
    assert names["io.github.example/search"]["install_payload"]["manifest"]["transport"] == "http"
    assert names["acme/review"]["kind"] == "skill"
    assert names["acme/review"]["install_mode"] == "marketplace_preflight"
    assert names["acme/review"]["install_payload"]["marketplace_source"] == "smithery_skills"
    assert names["acme/review"]["install_payload"]["manifest"]["package_type"] == "skill_pack"
    assert names["acme/review"]["install_payload"]["manifest"]["skill"][
        "depends_on_mcp_servers"
    ] == ["smithery/github"]
    assert any(
        call[0].endswith("/v0/servers")
        and call[1]["search"] == "search"
        and call[1]["version"] == "latest"
        for call in fake_client.calls
    )


def test_capability_marketplace_degrades_when_external_sources_fail(monkeypatch) -> None:
    class FailingMarketplaceClient:
        def __enter__(self) -> "FailingMarketplaceClient":
            return self

        def __exit__(self, *_args) -> None:
            return None

        def get(self, *_args, **_kwargs) -> _FakeMarketplaceResponse:
            raise marketplace_module.httpx.ConnectError("offline")

    monkeypatch.setattr(
        marketplace_module.httpx,
        "Client",
        lambda *args, **kwargs: FailingMarketplaceClient(),
    )

    response = TestClient(app).get(
        "/api/tools/capabilities/marketplace?kind=mcp&limit=5",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert any(item["source"] == "harness_curated" for item in payload["items"])
    assert {error["source"] for error in payload["errors"]} == {
        "official_mcp_registry",
        "smithery_mcp",
    }
    source_status = {source["id"]: source["status"] for source in payload["sources"]}
    assert source_status["official_mcp_registry"] == "unavailable"
    assert source_status["smithery_mcp"] == "unavailable"


def test_compat_tool_execute_denies_task_without_agent_scope(db_session: Session) -> None:
    client = TestClient(app)
    task_id = _create_task(client)

    response = client.post(
        f"/api/tasks/{task_id}/tools/execute",
        headers=AUTH_HEADERS,
        json={
            "tool_name": "mcp_context_search",
            "input_json": {"query": "event sourcing replay", "limit": 2},
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["allowed"] is False
    assert payload["tool_call"]["tool_name"] == "mcp_context_search"
    assert payload["tool_call"]["status"] == "DENIED"
    assert payload["tool_call"]["error_message"] == "agent not found: __missing_agent__"
    assert payload["tool_call"]["capability_version_id"] is None
    assert payload["output"] == {}

    tool_call = db_session.execute(
        select(ToolCall).where(
            ToolCall.task_id == task_id,
            ToolCall.tool_name == "mcp_context_search",
        )
    ).scalar_one()
    assert tool_call.status == "DENIED"
    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == task_id).order_by(AgentEvent.sequence)
        ).scalars()
    ]
    assert "POLICY_CHECKED" in event_types
    assert "TOOL_DENIED_BY_POLICY" in event_types


def test_agent_scoped_mcp_test_invocation_uses_tool_runner_policy_and_audit_path(
    db_session: Session,
) -> None:
    _create_agent(db_session, agent_id="mcp-agent", tools=["mcp_context_search"])

    response = TestClient(app).post(
        "/api/tools/capabilities/test-invoke",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "mcp-agent",
            "tool_name": "mcp_context_search",
            "input_json": {"query": "event sourcing replay", "limit": 2},
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["allowed"] is True
    assert payload["tool_call"]["tool_name"] == "mcp_context_search"
    assert payload["tool_call"]["status"] == "SUCCESS"
    assert payload["tool_call"]["capability_version_id"] is not None
    assert payload["tool_call"]["capability_content_sha256"] is not None
    assert payload["tool_call"]["capability_snapshot_json"]["agent_id"] == "mcp-agent"
    assert payload["output"]["mcp_server"] == "local-context"
    assert payload["output"]["mcp_method"] == "context.search"
    assert len(payload["output"]["result"]["items"]) == 2

    tool_call = db_session.get(ToolCall, payload["tool_call"]["id"])
    assert tool_call is not None
    assert tool_call.status == "SUCCESS"
    assert tool_call.output_json["mcp_server"] == "local-context"
    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent)
            .where(AgentEvent.task_id == tool_call.task_id)
            .order_by(AgentEvent.sequence)
        ).scalars()
    ]
    assert "POLICY_CHECKED" in event_types
    assert "TOOL_CALLED" in event_types
    assert "TOOL_RESULT_RECEIVED" in event_types


def test_admin_validation_redacts_secrets_and_does_not_create_tool_call(
    db_session: Session,
) -> None:
    response = TestClient(app).post(
        "/api/tools/capabilities/admin-validate",
        headers=AUTH_HEADERS,
        json={
            "content": {"name": "private-tool"},
            "config": {
                "api_key": "clear-secret",
                "secret_ref": "vault://tool/api-key",
                "nested": {"authorization": "Bearer clear-secret"},
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "valid"
    assert payload["redacted_payload"]["config"]["api_key"] == "[REDACTED]"
    assert payload["redacted_payload"]["config"]["secret_ref"] == "vault://tool/api-key"
    assert payload["redacted_payload"]["config"]["nested"]["authorization"] == "[REDACTED]"
    assert db_session.execute(select(ToolCall)).scalar_one_or_none() is None


def test_disabled_attachment_denies_even_when_tool_remains_in_legacy_tools_json(
    db_session: Session,
) -> None:
    _create_agent(db_session, agent_id="locked-agent", tools=["read_file"])
    registry = CapabilityRegistry(db_session, "dev-org")
    registry.backfill_agent_attachments("locked-agent", attached_by="test")
    attachment = db_session.execute(
        select(AgentCapabilityAttachment).where(
            AgentCapabilityAttachment.agent_id == "locked-agent",
        )
    ).scalar_one()
    attachment.enabled = False
    db_session.flush()

    response = TestClient(app).post(
        "/api/tools/capabilities/test-invoke",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "locked-agent",
            "tool_name": "read_file",
            "input_json": {"path": "pyproject.toml"},
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["allowed"] is False
    assert payload["tool_call"]["status"] == "DENIED"
    assert "not attached to capability read_file" in payload["tool_call"]["error_message"]
    assert payload["tool_call"]["capability_version_id"] is None


def test_legacy_tools_json_alone_does_not_authorize_or_lazy_backfill(
    db_session: Session,
) -> None:
    db_session.add(
        Agent(
            id="legacy-only-agent",
            organization_id=None,
            name="Legacy Only Agent",
            description="Has tools_json but no persisted capability attachment",
            role="tester",
            status="ACTIVE",
            model_provider="default",
            model_name="default",
            system_prompt="Legacy metadata only.",
            tools_json=["read_file"],
            routing_tags=[],
        )
    )
    db_session.flush()

    response = TestClient(app).post(
        "/api/tools/capabilities/test-invoke",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "legacy-only-agent",
            "tool_name": "read_file",
            "input_json": {"path": "pyproject.toml"},
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["allowed"] is False
    assert payload["tool_call"]["status"] == "DENIED"
    assert "not attached to capability read_file" in payload["tool_call"]["error_message"]
    assert (
        db_session.execute(
            select(AgentCapabilityAttachment).where(
                AgentCapabilityAttachment.agent_id == "legacy-only-agent",
            )
        ).scalar_one_or_none()
        is None
    )


def _package_manifest(name: str = "packaged_echo", *, risk_level: str = "low") -> dict:
    return {
        "name": name,
        "version": "1.0.0",
        "description": "Packaged echo tool",
        "package_type": "tool_definition",
        "risk_level": risk_level,
        "permissions": [] if risk_level == "low" else ["shell"],
        "secret_refs": ["secret://capability/echo"] if risk_level == "high" else [],
        "provenance": {"builder": "test"},
        "tool_metadata": {
            "name": name,
            "description": "Echoes redacted input for package smoke tests.",
            "category": "package",
            "source": "builtin",
            "risk_level": risk_level,
            "requires_sandbox": risk_level == "high",
            "network_policy": "none",
            "timeout_seconds": 10,
            "allowed_roles": ["admin", "engineer"],
            "audit_level": "standard" if risk_level == "low" else "elevated",
            "idempotent": True,
            "input_schema": {"type": "object"},
        },
    }


def _context_optimizer_manifest(name: str = "conservative-token-saver") -> dict:
    return {
        "name": name,
        "version": "1.0.0",
        "description": "Declarative Agent context optimizer",
        "package_type": "context_optimizer",
        "schema_version": "context-optimizer-v1",
        "risk_level": "low",
        "permissions": ["context:optimize"],
        "provenance": {"builder": "test"},
        "optimizer": {
            "mode": "budget_overlay",
            "max_candidate_tokens_ratio": 0.8,
            "section_limits": {
                "recent_window": 12,
                "long_term_memory": 8,
                "rag_evidence": 6,
            },
            "drop_order": [
                "rag_evidence_low_relevance_first",
                "long_term_memory_low_score_first",
                "recent_window_oldest_first",
            ],
            "prefer_valid_compressed_summary": True,
            "low_cost_route_hint": "summarization under budget",
        },
    }


def _fake_downloaded_package(source_uri: str) -> capabilities_module.DownloadedPackageContent:
    return capabilities_module.DownloadedPackageContent(
        content={
            "download": {
                "source_uri": source_uri,
                "final_url": source_uri,
                "content_type": "text/markdown",
                "size_bytes": 8,
                "sha256": "downloaded-sha",
                "redirects": [],
            },
            "body": "# Skill\n",
        },
        pinned_ref="sha256:downloaded-sha",
        metadata={
            "source_uri": source_uri,
            "final_url": source_uri,
            "sha256": "downloaded-sha",
            "size_bytes": 8,
            "content_type": "text/markdown",
            "redirect_count": 0,
            "redirects": [],
            "fetch_client": "httpx",
            "no_code_execution": True,
        },
    )


def test_private_package_upload_approve_attach_and_test_invoke(
    db_session: Session,
) -> None:
    _create_agent(db_session, agent_id="package-agent", tools=[])
    client = TestClient(app)

    staged = client.post(
        "/api/tools/capabilities/packages/private",
        headers=AUTH_HEADERS,
        json={"manifest": _package_manifest(), "content": {"api_key": "clear-secret"}},
    )

    assert staged.status_code == 201
    staged_payload = staged.json()
    assert staged_payload["validation_json"]["errors"] == []
    assert staged_payload["status"] == "staged"
    assert staged_payload["validation_json"]["no_code_execution"] is True
    assert staged_payload["validation_json"]["jsonschema_draft"] == "2020-12"
    assert (
        staged_payload["validation_json"]["staging_execution"]
        == "manifest_only_no_code_execution"
    )
    assert staged_payload["provenance_json"]["source_sha256"] == staged_payload["source_sha256"]

    approved = client.post(
        f"/api/tools/capabilities/packages/{staged_payload['id']}/approve",
        headers=AUTH_HEADERS,
        json={"reason": "test install"},
    )

    assert approved.status_code == 200
    approved_payload = approved.json()
    assert approved_payload["status"] == "approved"
    assert approved_payload["capability_version_id"] is not None
    assert approved_payload["audit_json"]["approval"]["immutable_version"] is True

    attached = client.post(
        f"/api/tools/capabilities/packages/{staged_payload['id']}/attachments",
        headers=AUTH_HEADERS,
        json={"agent_id": "package-agent", "enabled": True, "priority": 10},
    )

    assert attached.status_code == 201
    attachment_payload = attached.json()
    assert attachment_payload["capability_version_id"] == approved_payload["capability_version_id"]

    invoked = client.post(
        "/api/tools/capabilities/test-invoke",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "package-agent",
            "tool_name": "packaged_echo",
            "input_json": {"api_key": "clear-secret", "message": "hello"},
        },
    )

    assert invoked.status_code == 202
    invoke_payload = invoked.json()
    assert invoke_payload["allowed"] is True
    assert invoke_payload["tool_call"]["status"] == "SUCCESS"
    assert invoke_payload["tool_call"]["input_json"]["api_key"] == "[REDACTED]"
    assert invoke_payload["tool_call"]["capability_snapshot_json"]["agent_id"] == "package-agent"
    assert invoke_payload["output"]["package_tool"] == "packaged_echo"
    task = db_session.get(Task, invoke_payload["tool_call"]["task_id"])
    assert task is not None
    assert task.enable_sandbox is True


def test_context_optimizer_package_installs_and_attaches_without_tool_execution(
    db_session: Session,
) -> None:
    _create_agent(db_session, agent_id="optimizer-agent", tools=["read_file"])
    client = TestClient(app)

    staged = client.post(
        "/api/tools/capabilities/packages/private",
        headers=AUTH_HEADERS,
        json={"manifest": _context_optimizer_manifest(), "content": {}},
    )

    assert staged.status_code == 201
    staged_payload = staged.json()
    assert staged_payload["validation_json"]["errors"] == []
    assert staged_payload["status"] == "staged"
    assert staged_payload["package_type"] == "context_optimizer"
    assert staged_payload["validation_json"]["no_code_execution"] is True

    approved = client.post(
        f"/api/tools/capabilities/packages/{staged_payload['id']}/approve",
        headers=AUTH_HEADERS,
        json={"reason": "attach optimizer"},
    )

    assert approved.status_code == 200
    approved_payload = approved.json()
    assert approved_payload["capability_version_id"] is not None
    capability = db_session.get(Capability, approved_payload["capability_id"])
    assert capability is not None
    assert capability.type == "context_optimizer"

    attached = client.post(
        f"/api/tools/capabilities/packages/{staged_payload['id']}/attachments",
        headers=AUTH_HEADERS,
        json={"agent_id": "optimizer-agent", "enabled": True, "priority": 10},
    )

    assert attached.status_code == 201
    attachment_payload = attached.json()
    assert attachment_payload["capability_version_id"] == approved_payload["capability_version_id"]

    registry, snapshot = CapabilityRegistry(db_session, "dev-org").tool_registry_for_agent(
        "optimizer-agent"
    )
    assert set(registry.tools) == {"read_file"}
    assert approved_payload["capability_version_id"] not in snapshot["capability_version_ids"]

    invoked = client.post(
        "/api/tools/capabilities/test-invoke",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "optimizer-agent",
            "tool_name": "read_file",
            "input_json": {"path": "pyproject.toml"},
        },
    )

    assert invoked.status_code == 202
    invoke_payload = invoked.json()
    assert invoke_payload["tool_call"]["status"] in {"SUCCESS", "DENIED"}
    assert invoke_payload["tool_call"]["capability_version_id"] != approved_payload[
        "capability_version_id"
    ]


def test_context_optimizer_manifest_rejects_unknown_or_executing_fields() -> None:
    manifest = _context_optimizer_manifest()
    manifest["optimizer"]["unsupported"] = True
    manifest["secret_refs"] = ["secret://not-needed"]
    manifest["runtime"] = {"type": "python"}

    validation = capabilities_module.validate_package_manifest(manifest)

    assert validation["status"] == "invalid"
    assert any("optimizer has unsupported fields" in error for error in validation["errors"])
    assert any("manifest has unsupported fields" in error for error in validation["errors"])
    assert any("must not require secret_refs" in error for error in validation["errors"])


def test_simple_trusted_url_install_downloads_enables_and_attaches(
    db_session: Session,
    monkeypatch,
) -> None:
    _create_agent(db_session, agent_id="trusted-url-agent", tools=[])
    client = TestClient(app)
    monkeypatch.setattr(
        capabilities_module,
        "download_remote_package_content",
        _fake_downloaded_package,
    )

    response = client.post(
        "/api/tools/capabilities/install/trusted-url",
        headers=AUTH_HEADERS,
        json={
            "source_uri": "https://example.com/customer-research.skill",
            "display_name": "customer research skill",
            "package_type": "skill_pack",
            "agent_id": "trusted-url-agent",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["ready_state"] == "attached"
    assert payload["package"]["status"] == "approved"
    assert payload["package"]["source_kind"] == "trusted_url"
    assert payload["package"]["pinned_ref"] == "sha256:downloaded-sha"
    assert payload["package"]["validation_json"]["download"]["fetch_client"] == "httpx"
    assert payload["capability_version_id"] is not None
    assert payload["attachment"]["agent_id"] == "trusted-url-agent"


def test_simple_public_url_preflight_does_not_activate(
    db_session: Session,
    monkeypatch,
) -> None:
    _create_agent(db_session, agent_id="public-preflight-agent", tools=[])
    client = TestClient(app)
    monkeypatch.setattr(
        capabilities_module,
        "download_remote_package_content",
        _fake_downloaded_package,
    )

    response = client.post(
        "/api/tools/capabilities/preflight/public-url",
        headers=AUTH_HEADERS,
        json={
            "source_uri": "https://example.com/public.skill",
            "display_name": "public skill",
            "package_type": "skill_pack",
            "agent_id": "public-preflight-agent",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["ready_state"] == "staged"
    assert payload["staged_capability_id"] == payload["package"]["id"]
    assert payload["package"]["pinned_ref"] == "sha256:downloaded-sha"
    assert payload["package"]["validation_json"]["download"]["no_code_execution"] is True
    assert payload["capability_id"] is None
    assert payload["capability_version_id"] is None
    assert payload["attachment"] is None
    assert payload["next_step_label"] == "Enable after validation"

    enabled = client.post(
        f"/api/tools/capabilities/staged/{payload['staged_capability_id']}/enable",
        headers=AUTH_HEADERS,
        json={"reason": "validated in v1 public preflight"},
    )

    assert enabled.status_code == 200
    enabled_payload = enabled.json()
    assert enabled_payload["ready_state"] == "ready"
    assert enabled_payload["capability_version_id"] is not None
    assert enabled_payload["next_step_label"] == "Attach to Agent"


def test_simple_public_url_preflight_is_idempotent_for_same_marketplace_package(
    monkeypatch,
) -> None:
    client = TestClient(app)
    monkeypatch.setattr(
        capabilities_module,
        "download_remote_package_content",
        _fake_downloaded_package,
    )
    payload = {
        "source_uri": "https://example.com/public.skill",
        "display_name": "public skill",
        "package_type": "skill_pack",
        "agent_id": "public-preflight-agent",
    }

    first = client.post(
        "/api/tools/capabilities/preflight/public-url",
        headers=AUTH_HEADERS,
        json=payload,
    )
    second = client.post(
        "/api/tools/capabilities/preflight/public-url",
        headers=AUTH_HEADERS,
        json=payload,
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["staged_capability_id"] == first.json()["staged_capability_id"]
    assert second.json()["package"]["validation_json"]["idempotent_preflight"] is True


def test_marketplace_preflight_registers_metadata_without_public_source_resolution(
    db_session: Session,
    monkeypatch,
) -> None:
    _create_agent(db_session, agent_id="marketplace-agent", tools=[])
    client = TestClient(app)

    def fail_download(_source_uri: str) -> capabilities_module.DownloadedPackageContent:
        raise AssertionError("marketplace preflight must not fetch listed URLs")

    def fail_resolver(_host: str) -> list[str]:
        raise AssertionError("marketplace preflight must not resolve listed hosts")

    monkeypatch.setattr(capabilities_module, "download_remote_package_content", fail_download)
    monkeypatch.setattr(capabilities_module, "_resolved_public_host_errors", fail_resolver)

    response = client.post(
        "/api/tools/capabilities/preflight/marketplace",
        headers=AUTH_HEADERS,
        json={
            "source_uri": "https://localhost/internal-mcp",
            "pinned_ref": "marketplace-sha256:abc123",
            "marketplace_source": "official_mcp_registry",
            "marketplace_item_id": "official-mcp::local-test@1.0.0",
            "display_name": "Local Test MCP",
            "description": "Registry metadata only.",
            "package_type": "mcp_server",
            "permissions": ["mcp:remote"],
            "manifest": {
                "name": "local-test-mcp",
                "version": "1.0.0",
                "description": "Registry metadata only.",
                "package_type": "mcp_server",
                "permissions": ["mcp:remote"],
                "transport": "http",
                "secret_refs": [],
            },
            "content": {
                "marketplace": {
                    "source": "official_mcp_registry",
                    "server": {"name": "local-test-mcp"},
                }
            },
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["ready_state"] == "staged"
    assert payload["staged_capability_id"] == payload["package"]["id"]
    assert payload["next_step_label"] == "Approve marketplace version"
    package = payload["package"]
    assert package["source_kind"] == "marketplace_preflight"
    assert package["source_uri"] == "https://localhost/internal-mcp"
    assert package["validation_json"]["marketplace_preflight"] is True
    assert (
        package["validation_json"]["source_resolution"]
        == "registry_metadata_only_no_url_fetch"
    )
    assert package["provenance_json"]["marketplace_registry_metadata_only"] is True
    assert package["audit_json"]["marketplace_preflight"]["no_source_download"] is True
    assert package["audit_json"]["marketplace_preflight"]["requires_approval"] is True

    approved = client.post(
        f"/api/tools/capabilities/packages/{package['id']}/approve",
        headers=AUTH_HEADERS,
        json={"reason": "registry metadata reviewed"},
    )

    assert approved.status_code == 200
    approved_payload = approved.json()
    assert approved_payload["status"] == "approved"
    assert approved_payload["capability_version_id"] is not None


def test_marketplace_mcp_package_can_be_attached_and_test_invoked(
    db_session: Session,
    monkeypatch,
) -> None:
    _create_agent(db_session, agent_id="brave-agent", tools=[])
    client = TestClient(app)

    def fail_download(_source_uri: str) -> capabilities_module.DownloadedPackageContent:
        raise AssertionError("marketplace MCP smoke must not download source URLs")

    def fail_resolver(_host: str) -> list[str]:
        raise AssertionError("marketplace MCP smoke must not resolve listed hosts")

    monkeypatch.setattr(capabilities_module, "download_remote_package_content", fail_download)
    monkeypatch.setattr(capabilities_module, "_resolved_public_host_errors", fail_resolver)

    preflight = client.post(
        "/api/tools/capabilities/preflight/marketplace",
        headers=AUTH_HEADERS,
        json={
            "source_uri": "https://brave.com/search/api/",
            "pinned_ref": "marketplace-sha256:brave-test",
            "marketplace_source": "smithery_mcp",
            "marketplace_item_id": "smithery-mcp::brave",
            "display_name": "Brave Search",
            "description": "Search the web through Brave Search.",
            "package_type": "mcp_server",
            "permissions": ["mcp:remote"],
            "manifest": {
                "name": "brave",
                "version": "1.0.0",
                "description": "Search the web through Brave Search.",
                "package_type": "mcp_server",
                "permissions": ["mcp:remote"],
                "transport": "http",
                "secret_refs": [],
                "mcp_server": {
                    "registry": "smithery_mcp",
                    "qualified_name": "brave",
                    "homepage": "https://brave.com/search/api/",
                    "smithery_connection_required": True,
                },
            },
            "content": {"marketplace": {"source": "smithery_mcp"}},
        },
    )
    assert preflight.status_code == 201
    package_id = preflight.json()["package"]["id"]

    approved = client.post(
        f"/api/tools/capabilities/packages/{package_id}/approve",
        headers=AUTH_HEADERS,
        json={"reason": "registry metadata reviewed"},
    )
    assert approved.status_code == 200
    approved_payload = approved.json()

    attached = client.post(
        f"/api/tools/capabilities/packages/{package_id}/attachments",
        headers=AUTH_HEADERS,
        json={"agent_id": "brave-agent", "enabled": True, "priority": 10},
    )
    assert attached.status_code == 201

    registry, _snapshot = CapabilityRegistry(db_session, "dev-org").tool_registry_for_agent(
        "brave-agent"
    )
    assert "brave" in registry.tools
    assert registry.tools["brave"].mcp_server == "brave"

    invoked = client.post(
        "/api/tools/capabilities/test-invoke",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "brave-agent",
            "tool_name": "brave",
            "input_json": {"query": "OpenAI latest news", "limit": 3},
        },
    )

    assert invoked.status_code == 202
    payload = invoked.json()
    assert payload["allowed"] is True
    assert payload["tool_call"]["tool_name"] == "brave"
    assert payload["tool_call"]["status"] == "SUCCESS"
    assert payload["tool_call"]["capability_version_id"] == approved_payload[
        "capability_version_id"
    ]
    assert payload["output"]["mcp_server"] == "brave"
    assert payload["output"]["mcp_method"] == "search"
    assert payload["output"]["result"]["source"] == "mcp-marketplace-adapter"
    assert len(payload["output"]["result"]["items"]) == 3


def test_mcp_runtime_config_creates_new_version_and_live_brave_test(
    db_session: Session,
    monkeypatch,
) -> None:
    _create_agent(db_session, agent_id="brave-config-agent", tools=[])
    client = TestClient(app)
    monkeypatch.setattr(
        capabilities_module,
        "download_remote_package_content",
        lambda _source_uri: pytest.fail("runtime config must not download package sources"),
    )
    monkeypatch.setattr(
        capabilities_module,
        "_resolved_public_host_errors",
        lambda _host: pytest.fail("marketplace preflight must not resolve listed hosts"),
    )

    preflight = client.post(
        "/api/tools/capabilities/preflight/marketplace",
        headers=AUTH_HEADERS,
        json={
            "source_uri": "https://brave.com/search/api/",
            "pinned_ref": "marketplace-sha256:brave-runtime-config",
            "marketplace_source": "smithery_mcp",
            "marketplace_item_id": "smithery-mcp::brave-runtime-config",
            "display_name": "Brave Search",
            "description": "Search the web through Brave Search.",
            "package_type": "mcp_server",
            "permissions": ["mcp:remote"],
            "manifest": {
                "name": "brave",
                "version": "1.0.0",
                "description": "Search the web through Brave Search.",
                "package_type": "mcp_server",
                "permissions": ["mcp:remote"],
                "transport": "http",
                "secret_refs": [],
                "mcp_server": {"qualified_name": "brave"},
            },
            "content": {"marketplace": {"source": "smithery_mcp"}},
        },
    )
    assert preflight.status_code == 201
    package_id = preflight.json()["package"]["id"]
    approved = client.post(
        f"/api/tools/capabilities/packages/{package_id}/approve",
        headers=AUTH_HEADERS,
        json={"reason": "registry metadata reviewed"},
    )
    assert approved.status_code == 200
    original_version_id = approved.json()["capability_version_id"]
    attached = client.post(
        f"/api/tools/capabilities/packages/{package_id}/attachments",
        headers=AUTH_HEADERS,
        json={"agent_id": "brave-config-agent", "enabled": True, "priority": 10},
    )
    assert attached.status_code == 201
    attachment_id = attached.json()["attachment_id"]

    before_config = client.get(
        "/api/tools/capabilities/runtime-config",
        headers=AUTH_HEADERS,
        params={"agent_id": "brave-config-agent", "tool_name": "brave"},
    )
    assert before_config.status_code == 200
    assert before_config.json()["configured"] is False
    assert "endpoint_url" in before_config.json()["missing_fields"]

    configured = client.patch(
        "/api/tools/capabilities/runtime-config",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "brave-config-agent",
            "tool_name": "brave",
            "transport": "http",
            "endpoint_url": "https://api.search.brave.com/res/v1/web/search",
            "secret_ref": "secret://mcp/brave-config-agent/brave/api-key",
            "secret_value": "brave-test-token",
            "timeout_seconds": 9,
        },
    )
    assert configured.status_code == 200
    payload = configured.json()
    assert payload["configured"] is True
    assert payload["secret_configured"] is True
    assert payload["endpoint_url"] == "https://api.search.brave.com/res/v1/web/search"
    assert payload["capability_version_id"] != original_version_id
    assert "brave-test-token" not in str(payload)

    old_version = db_session.get(CapabilityVersion, original_version_id)
    new_version = db_session.get(CapabilityVersion, payload["capability_version_id"])
    attachment = db_session.get(AgentCapabilityAttachment, attachment_id)
    assert old_version is not None
    assert new_version is not None
    assert attachment is not None
    assert old_version.config_json.get("runtime") is None
    assert new_version.config_json["runtime"]["endpoint_url"] == (
        "https://api.search.brave.com/res/v1/web/search"
    )
    assert new_version.config_json["secret_ref"] == "secret://mcp/brave-config-agent/brave/api-key"
    assert "secret_value" not in new_version.config_json
    assert attachment.capability_version_id == new_version.id
    assert read_connector_secret_ref(
        db_session,
        organization_id="dev-org",
        secret_ref="secret://mcp/brave-config-agent/brave/api-key",
    ) == "brave-test-token"

    brave_calls: list[dict] = []

    def fake_brave_get(*args, **kwargs) -> _FakeBraveResponse:
        brave_calls.append({"args": args, "kwargs": kwargs})
        return _FakeBraveResponse()

    monkeypatch.setattr("app.tools.mcp_adapter.httpx.get", fake_brave_get)
    invoked = client.post(
        "/api/tools/capabilities/test-invoke",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "brave-config-agent",
            "tool_name": "brave",
            "input_json": {"query": "MCP 教程", "limit": 3},
        },
    )
    assert invoked.status_code == 202
    invoke_payload = invoked.json()
    assert invoke_payload["tool_call"]["capability_version_id"] == new_version.id
    assert invoke_payload["output"]["result"]["source"] == "brave-search-api"
    assert invoke_payload["output"]["result"]["items"][0]["title"] == "MCP 教程 - Brave result"
    assert brave_calls[0]["args"][0] == "https://api.search.brave.com/res/v1/web/search"
    assert brave_calls[0]["kwargs"]["headers"]["X-Subscription-Token"] == "brave-test-token"


def test_simple_public_git_preflight_requires_pin_or_content_hash() -> None:
    response = TestClient(app).post(
        "/api/tools/capabilities/preflight/public-url",
        headers=AUTH_HEADERS,
        json={
            "source_uri": "git+https://github.com/example/public-skill.git",
            "display_name": "public skill",
            "package_type": "skill_pack",
        },
    )

    assert response.status_code == 400
    assert "pinned_ref" in response.json()["detail"]


def test_trusted_url_install_still_rejects_unsafe_source_url() -> None:
    response = TestClient(app).post(
        "/api/tools/capabilities/install/trusted-url",
        headers=AUTH_HEADERS,
        json={
            "source_uri": "http://example.com/customer-research.skill",
            "display_name": "customer research skill",
            "package_type": "skill_pack",
        },
    )

    assert response.status_code == 400
    assert "https" in response.json()["detail"]


def test_simple_upload_install_enables_without_manifest_editing(
    db_session: Session,
) -> None:
    _create_agent(db_session, agent_id="upload-install-agent", tools=[])
    client = TestClient(app)

    response = client.post(
        "/api/tools/capabilities/install/upload",
        headers=AUTH_HEADERS,
        json={
            "display_name": "uploaded skill",
            "package_type": "skill_pack",
            "agent_id": "upload-install-agent",
            "content": {"filename": "SKILL.md", "body": "# Skill\n"},
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["ready_state"] == "attached"
    assert payload["package"]["source_kind"] == "private_upload"
    assert payload["package"]["manifest_json"]["package_type"] == "skill_pack"
    assert payload["attachment"]["agent_id"] == "upload-install-agent"


def test_dependency_preflight_reports_no_container_v1_path() -> None:
    response = TestClient(app).get(
        "/api/tools/capabilities/dependency-preflight",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["local_release_path"] == "no-container"
    assert payload["docker_private_smoke"] == "optional"
    assert payload["required_v1"]["jsonschema"] == "draft-2020-12-validator-active"
    assert "trusted_url_install" in payload["feature_flags"]


class _FakeDownloadResponse:
    def __init__(
        self,
        status_code: int,
        *,
        content: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        return None


class _FakeDownloadClient:
    def __init__(self, responses: list[_FakeDownloadResponse]) -> None:
        self.responses = responses
        self.urls: list[str] = []

    def __enter__(self) -> "_FakeDownloadClient":
        return self

    def __exit__(self, *_args) -> None:
        return None

    def get(self, url: str, *, headers: dict[str, str]) -> _FakeDownloadResponse:
        self.urls.append(url)
        return self.responses.pop(0)


def test_remote_package_download_records_hash_and_metadata(monkeypatch) -> None:
    monkeypatch.setattr(
        capabilities_module.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (
                capabilities_module.socket.AF_INET,
                capabilities_module.socket.SOCK_STREAM,
                6,
                "",
                ("93.184.216.34", 443),
            )
        ],
    )
    fake_client = _FakeDownloadClient(
        [
            _FakeDownloadResponse(
                200,
                content=b"# Skill\n",
                headers={"content-type": "text/markdown"},
            )
        ]
    )
    monkeypatch.setattr(
        capabilities_module.httpx,
        "Client",
        lambda **_kwargs: fake_client,
    )

    downloaded = capabilities_module.download_remote_package_content(
        "https://example.com/public.skill"
    )

    assert fake_client.urls == ["https://example.com/public.skill"]
    assert downloaded.pinned_ref.startswith("sha256:")
    assert downloaded.content["body"] == "# Skill\n"
    assert downloaded.metadata["fetch_client"] == "httpx"
    assert downloaded.metadata["no_code_execution"] is True


def test_remote_package_download_rejects_cross_host_redirect(monkeypatch) -> None:
    monkeypatch.setattr(
        capabilities_module.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (
                capabilities_module.socket.AF_INET,
                capabilities_module.socket.SOCK_STREAM,
                6,
                "",
                ("93.184.216.34", 443),
            )
        ],
    )
    fake_client = _FakeDownloadClient(
        [
            _FakeDownloadResponse(
                302,
                headers={"location": "https://other.example/public.skill"},
            )
        ]
    )
    monkeypatch.setattr(
        capabilities_module.httpx,
        "Client",
        lambda **_kwargs: fake_client,
    )

    with pytest.raises(capabilities_module.CapabilityResolutionError, match="across hosts"):
        capabilities_module.download_remote_package_content("https://example.com/public.skill")


def test_public_source_resolver_blocks_private_addresses(monkeypatch) -> None:
    monkeypatch.setattr(
        capabilities_module.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (
                capabilities_module.socket.AF_INET,
                capabilities_module.socket.SOCK_STREAM,
                6,
                "",
                ("10.0.0.10", 443),
            )
        ],
    )

    result = capabilities_module.validate_public_source(
        "https://example.com/package.json",
        pinned_ref="sha256:abc",
    )

    assert result["status"] == "invalid"
    assert "resolver returned private" in " ".join(result["errors"])


def test_public_url_package_blocks_private_ip_and_requires_pinned_source() -> None:
    client = TestClient(app)

    blocked = client.post(
        "/api/tools/capabilities/packages/public",
        headers=AUTH_HEADERS,
        json={
            "manifest": _package_manifest("blocked_public_package"),
            "source_kind": "public_url",
            "source_uri": "https://127.0.0.1/package.json",
            "pinned_ref": "sha256:abc",
            "content": {},
        },
    )

    assert blocked.status_code == 400
    assert "not publicly routable" in blocked.json()["detail"]

    unpinned = client.post(
        "/api/tools/capabilities/packages/public",
        headers=AUTH_HEADERS,
        json={
            "manifest": _package_manifest("unpinned_public_package"),
            "source_kind": "public_url",
            "source_uri": "https://example.com/package.json",
            "pinned_ref": "",
            "content": {},
        },
    )

    assert unpinned.status_code == 422


def test_public_git_package_requires_approval_before_activation(
    db_session: Session,
) -> None:
    _create_agent(db_session, agent_id="public-package-agent", tools=[])
    client = TestClient(app)

    staged = client.post(
        "/api/tools/capabilities/packages/public",
        headers=AUTH_HEADERS,
        json={
            "manifest": _package_manifest("public_packaged_echo"),
            "source_kind": "public_git",
            "source_uri": "git+https://github.com/example/capability.git",
            "pinned_ref": "commit:0123456789abcdef",
            "content": {},
        },
    )

    assert staged.status_code == 201
    staged_payload = staged.json()
    assert staged_payload["status"] == "staged"
    assert staged_payload["capability_version_id"] is None
    assert staged_payload["validation_json"]["public_source_policy"]["status"] == "valid"

    attach_before_approval = client.post(
        f"/api/tools/capabilities/packages/{staged_payload['id']}/attachments",
        headers=AUTH_HEADERS,
        json={"agent_id": "public-package-agent"},
    )

    assert attach_before_approval.status_code == 400
    assert "approved before attachment" in attach_before_approval.json()["detail"]

    approved = client.post(
        f"/api/tools/capabilities/packages/{staged_payload['id']}/approve",
        headers=AUTH_HEADERS,
        json={"reason": "trusted commit"},
    )

    assert approved.status_code == 200
    assert approved.json()["capability_version_id"] is not None


def test_attachment_disable_blocks_future_runtime_and_uninstall_requires_no_active_attachment(
    db_session: Session,
) -> None:
    _create_agent(db_session, agent_id="toggle-package-agent", tools=[])
    client = TestClient(app)
    staged = client.post(
        "/api/tools/capabilities/packages/private",
        headers=AUTH_HEADERS,
        json={"manifest": _package_manifest("toggle_packaged_echo"), "content": {}},
    ).json()
    approved = client.post(
        f"/api/tools/capabilities/packages/{staged['id']}/approve",
        headers=AUTH_HEADERS,
        json={"reason": "test"},
    ).json()
    attached = client.post(
        f"/api/tools/capabilities/packages/{staged['id']}/attachments",
        headers=AUTH_HEADERS,
        json={"agent_id": "toggle-package-agent", "enabled": True},
    ).json()

    uninstall_blocked = client.post(
        f"/api/tools/capabilities/packages/{staged['id']}/uninstall",
        headers=AUTH_HEADERS,
    )
    assert uninstall_blocked.status_code == 400
    assert "active attachments" in uninstall_blocked.json()["detail"]

    disabled = client.patch(
        f"/api/tools/capabilities/attachments/{attached['attachment_id']}",
        headers=AUTH_HEADERS,
        json={"enabled": False},
    )
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False

    denied = client.post(
        "/api/tools/capabilities/test-invoke",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "toggle-package-agent",
            "tool_name": "toggle_packaged_echo",
            "input_json": {},
        },
    )
    assert denied.status_code == 202
    assert denied.json()["allowed"] is False
    assert "not attached" in denied.json()["tool_call"]["error_message"]

    uninstalled = client.post(
        f"/api/tools/capabilities/packages/{staged['id']}/uninstall",
        headers=AUTH_HEADERS,
    )
    assert uninstalled.status_code == 200
    assert uninstalled.json()["status"] == "uninstalled"
    assert approved["capability_version_id"] is not None


def test_package_manifest_rejects_raw_secret_values() -> None:
    response = TestClient(app).post(
        "/api/tools/capabilities/packages/private",
        headers=AUTH_HEADERS,
        json={
            "manifest": {
                **_package_manifest("raw_secret_package"),
                "api_key": "clear-secret",
            },
            "content": {},
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "invalid"
    assert "raw secret-like values" in " ".join(payload["validation_json"]["errors"])


def test_admin_validate_accepts_ui_commit_key_and_rejects_bad_secret_refs() -> None:
    response = TestClient(app).post(
        "/api/tools/capabilities/admin-validate",
        headers=AUTH_HEADERS,
        json={
            "content": {
                "package_manifest": {
                    **_package_manifest("validate_commit_package"),
                    "secret_refs": [{"name": "missing-ref"}],
                }
            },
            "config": {
                "source_type": "public_git",
                "source_url": "git+https://github.com/example/capability.git",
                "commit": "commit:0123456789abcdef",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "invalid"
    assert "must declare secret_ref" in " ".join(payload["errors"])
    assert payload["source_policy"]["pinned"] is True


def test_package_capability_identifiers_are_bounded_for_postgres_columns(
    db_session: Session,
) -> None:
    _create_agent(db_session, agent_id="long-package-agent", tools=[])
    long_name = "capability-" + ("very-long-name-" * 14)
    client = TestClient(app)
    staged = client.post(
        "/api/tools/capabilities/packages/private",
        headers=AUTH_HEADERS,
        json={"manifest": _package_manifest(long_name), "content": {}},
    )
    assert staged.status_code == 201

    approved = client.post(
        f"/api/tools/capabilities/packages/{staged.json()['id']}/approve",
        headers=AUTH_HEADERS,
        json={"reason": "bounded id regression"},
    )

    assert approved.status_code == 200
    payload = approved.json()
    assert len(payload["package_key"]) <= 128
    assert len(payload["capability_version_id"]) <= 64
    capability = db_session.get(Capability, payload["capability_id"])
    assert capability is not None
    assert len(capability.capability_key) <= 128
