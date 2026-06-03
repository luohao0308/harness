import importlib.util
from importlib.machinery import ModuleSpec

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.langgraph_runner import LangGraphBridgeResult, LangGraphRunnerAdapter
from app.agents.model_gateway import ModelRequest, ModelResponse
from app.agents.planner import DeterministicPlanner
from app.agents.schemas import PlanStep
from app.api.agents._tool_helpers import _infer_workspace_search_tool_mentions
from app.core.config import get_settings
from app.db.models import (
    Agent,
    AgentEvent,
    CapabilityPackage,
    CapabilityVersion,
    CitationRecord,
    EvalCase,
    EvalDataset,
    EvalResult,
    EvalRun,
    ExecutionPlan,
    PromptAssemblyManifest,
    RetrievalHit,
    Task,
    TaskStep,
    ToolCall,
    utc_now,
)
from app.events.event_store import EventStore
from app.events.replay import EventReplay
from app.knowledge.langchain_retriever_adapter import (
    LANGCHAIN_CONNECTOR_SOURCE_KIND,
    persist_langchain_grounding,
)
from app.main import app
from app.tools.adapter_registry import AdapterRegistry
from app.tools.adapters import register_builtin_adapters
from app.tools.adapters.langchain_adapter import LangChainToolAdapter, langchain_tool_metadata
from app.tools.capabilities import (
    CAPABILITY_TYPE_LANGGRAPH_WORKFLOW,
    EXECUTABLE_CAPABILITY_TYPES,
    CapabilityRegistry,
    CapabilityResolutionError,
    stable_json_sha256,
    validate_langgraph_workflow_package,
)
from app.tools.runner import ToolRunner
from tests.conftest import AUTH_HEADERS


@pytest.fixture()
def set_feature_flags(monkeypatch):
    def _set(flags: str) -> None:
        monkeypatch.setenv("FEATURE_FLAGS", flags)
        get_settings.cache_clear()

    yield _set
    get_settings.cache_clear()


def _create_agent(db_session: Session, *, agent_id: str = "langgraph-agent") -> Agent:
    agent = Agent(
        id=agent_id,
        organization_id=None,
        name=f"{agent_id} Agent",
        description="LangGraph compatibility test agent",
        role="tester",
        status="ACTIVE",
        model_provider="default",
        model_name="default",
        system_prompt="Use only attached capabilities.",
        tools_json=[],
        routing_tags=[],
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(agent)
    db_session.flush()
    return agent


def _langgraph_manifest(name: str = "demo-langgraph") -> dict:
    return {
        "name": name,
        "version": "1.0.0",
        "description": "Demo LangGraph workflow",
        "package_type": "langgraph_workflow",
        "permissions": [],
    }


def _langgraph_json(graph_path: str = "./agent.py:graph") -> dict:
    return {
        "dependencies": ["."],
        "graphs": {"main": graph_path},
        "env": ["./.env"],
    }


def _langgraph_content(langgraph_json: dict | None = None) -> dict:
    return {"langgraph_json": langgraph_json or _langgraph_json()}


def _approved_langgraph_package(
    db_session: Session,
    *,
    name: str = "demo-langgraph",
    agent_id: str = "langgraph-agent",
) -> CapabilityPackage:
    registry = CapabilityRegistry(db_session, "dev-org")
    package = registry.stage_private_package(
        manifest=_langgraph_manifest(name),
        content=_langgraph_content(),
        created_by="test",
    )
    assert package.status == "staged"
    approved = registry.approve_package(package_id=package.id, approved_by="test")
    registry.attach_package_capability(
        package_id=approved.id,
        agent_id=agent_id,
        attached_by="test",
        enabled=True,
        priority=10,
    )
    db_session.flush()
    return approved


def _langgraph_execution_task(
    db_session: Session,
    *,
    title: str = "LangGraph run",
    agent_id: str = "langgraph-agent",
) -> Task:
    task = Task(
        organization_id="dev-org",
        agent_id=agent_id,
        created_by="dev-engineer",
        title=title,
        goal="Run imported workflow",
        status="CREATED",
        model_provider="default",
        model_name="default",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(task)
    db_session.flush()
    return task


def _langgraph_plan_row(db_session: Session, task: Task, step: PlanStep) -> ExecutionPlan:
    plan = ExecutionPlan(
        task_id=task.id,
        version=1,
        status="APPROVED",
        plan_json={"summary": "LangGraph plan", "steps": [step.model_dump()]},
        created_at=utc_now(),
    )
    db_session.add(plan)
    db_session.flush()
    return plan


def _patch_langgraph_optional_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    original_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str, *args, **kwargs):
        if name == "langgraph":
            return ModuleSpec("langgraph", loader=None)
        return original_find_spec(name, *args, **kwargs)

    monkeypatch.setattr("importlib.util.find_spec", fake_find_spec)


def test_langgraph_workflow_package_is_not_executable_tool(
    db_session: Session,
) -> None:
    _create_agent(db_session)
    package = _approved_langgraph_package(db_session)

    assert CAPABILITY_TYPE_LANGGRAPH_WORKFLOW not in EXECUTABLE_CAPABILITY_TYPES
    version = db_session.get(CapabilityVersion, package.capability_version_id)
    assert version is not None
    assert version.type == CAPABILITY_TYPE_LANGGRAPH_WORKFLOW
    assert version.content_json["langgraph_json"]["graphs"]["main"] == "./agent.py:graph"

    registry = CapabilityRegistry(db_session, "dev-org")
    tool_registry, snapshot = registry.tool_registry_for_agent("langgraph-agent")
    assert tool_registry.tools == {}
    assert package.capability_version_id not in snapshot["capability_version_ids"]
    assert registry.attached_langgraph_workflows("langgraph-agent")[0].graph_id == "main"
    assert registry.metadata_for_tool_name("demo-langgraph") is None
    assert (
        _infer_workspace_search_tool_mentions(
            content="正在搜索 demo-langgraph workflow，请稍等。",
            goal="demo-langgraph workflow",
            registry=tool_registry,
        )
        == []
    )
    with pytest.raises(CapabilityResolutionError):
        registry.resolve_tool(
            agent_id="langgraph-agent",
            tool_name="demo-langgraph",
            task_id=None,
        )

    client = TestClient(app)
    registry_response = client.get(
        "/api/tools/registry",
        headers=AUTH_HEADERS,
        params={"agent_id": "langgraph-agent"},
    )
    assert registry_response.status_code == 200
    assert "demo-langgraph" not in {item["name"] for item in registry_response.json()["items"]}

    mcp_servers = client.get(
        "/api/tools/mcp-servers",
        headers=AUTH_HEADERS,
        params={"agent_id": "langgraph-agent"},
    )
    assert mcp_servers.status_code == 200
    assert mcp_servers.json()["items"] == []

    mcp_discovery = client.post(
        "/api/tools/mcp-servers/demo-langgraph/discover",
        headers=AUTH_HEADERS,
        params={"agent_id": "langgraph-agent"},
    )
    assert mcp_discovery.status_code == 400
    assert "not attached" in mcp_discovery.json()["detail"]

    response = client.post(
        "/api/tools/capabilities/test-invoke",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "langgraph-agent",
            "tool_name": "demo-langgraph",
            "input_json": {},
        },
    )

    assert response.status_code == 400
    assert "unknown tool" in response.json()["detail"]
    assert db_session.execute(select(ToolCall)).scalar_one_or_none() is None


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ({}, "requires content.langgraph_json"),
        ({"langgraph_json": "{not json"}, "invalid JSON"),
        ({"langgraph_json": {"dependencies": ["."], "graphs": {}}}, "non-empty graphs"),
        (
            {
                "langgraph_json": (
                    '{"dependencies":["."],"graphs":{"main":"./agent.py:graph",'
                    '"main":"./other.py:graph"}}'
                )
            },
            "graph ids must be unique",
        ),
        (
            _langgraph_content({"dependencies": ["."], "graphs": {"main": "../agent.py:graph"}}),
            "must not escape package root",
        ),
        (
            _langgraph_content({"dependencies": ["."], "graphs": {"main": "C:\\agent.py:graph"}}),
            "must not escape package root",
        ),
        (
            _langgraph_content({"dependencies": ["."], "graphs": {"main": "C:/agent.py:graph"}}),
            "must not escape package root",
        ),
        (
            _langgraph_content(
                {"dependencies": ["."], "graphs": {"main": "./agent.py:graph"}, "env": "../.env"}
            ),
            "env paths must not escape package root",
        ),
        (
            _langgraph_content(
                {
                    "dependencies": ["."],
                    "graphs": {"main": "./agent.py:graph"},
                    "env": "C:\\Users\\secret.env",
                }
            ),
            "env paths must not escape package root",
        ),
        (
            _langgraph_content(
                {
                    "dependencies": ["."],
                    "graphs": {"main": "./agent.py:graph"},
                    "env": ["/etc/passwd"],
                }
            ),
            "env[0] path must not escape package root",
        ),
        (
            _langgraph_content(
                {
                    "dependencies": ["."],
                    "graphs": {"main": "./agent.py:graph"},
                    "env": ["C:/Users/secret.env"],
                }
            ),
            "env[0] path must not escape package root",
        ),
        (
            _langgraph_content(
                {
                    "dependencies": ["."],
                    "graphs": {"main": "./agent.py:graph"},
                    "env": {"api_key": "sk-test-secret"},
                }
            ),
            "must use a secret ref",
        ),
        (
            _langgraph_content(
                {"dependencies": ["./other"], "graphs": {"main": "./agent.py:graph"}}
            ),
            "not covered by dependencies",
        ),
        (
            _langgraph_content(
                {"dependencies": ["C:\\deps"], "graphs": {"main": "./agent.py:graph"}}
            ),
            "dependency paths must not escape package root",
        ),
    ],
)
def test_langgraph_json_validation_rejects_unsafe_shapes(content: dict, expected: str) -> None:
    result = validate_langgraph_workflow_package(_langgraph_manifest(), content)

    assert result["status"] == "invalid"
    assert expected in "; ".join(result["errors"])


def test_langgraph_import_feature_flag_gates_staging(
    db_session: Session,
    set_feature_flags,
) -> None:
    set_feature_flags("trusted_url_install,langchain_adapter_enabled")

    package = CapabilityRegistry(db_session, "dev-org").stage_private_package(
        manifest=_langgraph_manifest(),
        content=_langgraph_content(),
        created_by="test",
    )

    assert package.status == "invalid"
    assert "langgraph_workflow_import_enabled" in "; ".join(package.validation_json["errors"])


def test_public_langgraph_package_requires_matching_sha256(
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.tools.capabilities._resolved_public_host_errors",
        lambda _host: [],
    )
    registry = CapabilityRegistry(db_session, "dev-org")
    content = _langgraph_content()
    matching_ref = f"sha256:{stable_json_sha256(content)}"

    with pytest.raises(CapabilityResolutionError, match="hash mismatch"):
        registry.stage_public_package(
            manifest=_langgraph_manifest("public-langgraph-bad"),
            source_kind="public_url",
            source_uri="https://example.com/langgraph.json",
            pinned_ref="sha256:" + "0" * 64,
            content=content,
            created_by="test",
        )

    package = registry.stage_public_package(
        manifest=_langgraph_manifest("public-langgraph-good"),
        source_kind="public_url",
        source_uri="https://example.com/langgraph.json",
        pinned_ref=matching_ref,
        content=content,
        created_by="test",
    )

    assert package.status == "staged"
    assert package.pinned_ref == matching_ref
    assert package.validation_json["staging_execution"] == "manifest_only_no_code_execution"


def test_public_langgraph_staging_requires_pin_hash_and_approval_without_remote_execution(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.tools.capabilities._resolved_public_host_errors",
        lambda _host: [],
    )
    download_calls: list[str] = []

    def fail_if_downloaded(source_uri: str):
        download_calls.append(source_uri)
        raise AssertionError("public LangGraph staging must not download or execute remote content")

    monkeypatch.setattr(
        "app.tools.capabilities.download_remote_package_content",
        fail_if_downloaded,
    )
    _create_agent(db_session)
    registry = CapabilityRegistry(db_session, "dev-org")
    content = _langgraph_content()

    with pytest.raises(CapabilityResolutionError, match="pinned"):
        registry.stage_public_package(
            manifest=_langgraph_manifest("public-langgraph-missing-pin"),
            source_kind="public_url",
            source_uri="https://example.com/langgraph.json",
            pinned_ref=None,  # type: ignore[arg-type]
            content=content,
            created_by="test",
        )

    with pytest.raises(CapabilityResolutionError, match="sha256 content hash"):
        registry.stage_public_package(
            manifest=_langgraph_manifest("public-langgraph-commit-only"),
            source_kind="public_git",
            source_uri="git+https://github.com/example/langgraph-workflow.git",
            pinned_ref="commit:0123456789abcdef",
            content=content,
            created_by="test",
        )

    pinned_ref = f"sha256:{stable_json_sha256(content)}"
    package = registry.stage_public_package(
        manifest=_langgraph_manifest("public-langgraph-approval"),
        source_kind="public_git",
        source_uri="git+https://github.com/example/langgraph-workflow.git",
        pinned_ref=pinned_ref,
        content=content,
        created_by="test",
    )

    assert package.status == "staged"
    assert package.capability_version_id is None
    assert package.validation_json["staging_execution"] == "manifest_only_no_code_execution"
    assert download_calls == []
    with pytest.raises(CapabilityResolutionError, match="approved before attachment"):
        registry.attach_package_capability(
            package_id=package.id,
            agent_id="langgraph-agent",
            attached_by="test",
        )


def test_langgraph_node_plan_execution_fails_closed_with_harness_events(
    db_session: Session,
    monkeypatch,
) -> None:
    _create_agent(db_session)
    _approved_langgraph_package(db_session)

    class FakeGateway:
        def __init__(self, **kwargs) -> None:
            pass

        def complete(self, request_payload: ModelRequest) -> ModelResponse:
            return ModelResponse(
                content="""
                {
                  "summary": "Run approved workflow",
                  "steps": [
                    {
                      "key": "workflow_step",
                      "description": "Run imported LangGraph workflow",
                      "execution_mode": "langgraph_node",
                      "requires_sandbox": true,
                      "can_spawn_subagent": false,
                      "depends_on": [],
                      "tool_hints": ["langgraph:main"],
                      "acceptance_criteria": ["Workflow emits Harness evidence"],
                      "risk_level": "medium",
                      "artifact_expectations": ["workflow event trace"]
                    }
                  ]
                }
                """,
                model_provider=request_payload.model_provider,
                model_name=request_payload.model_name,
                usage={},
                raw_response={"mode": "fake"},
            )

    monkeypatch.setattr("app.agents.executor.AuditedModelGateway", FakeGateway)
    task = Task(
        organization_id="dev-org",
        agent_id="langgraph-agent",
        created_by="dev-engineer",
        title="LangGraph run",
        goal="Run imported workflow",
        status="CREATED",
        model_provider="default",
        model_name="default",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(task)
    db_session.flush()

    response = TestClient(app).post(f"/api/tasks/{task.id}/start", headers=AUTH_HEADERS)

    assert response.status_code == 202
    assert response.json()["status"] == "FAILED"
    step = db_session.execute(select(TaskStep).where(TaskStep.task_id == task.id)).scalar_one()
    assert step.execution_mode == "langgraph_node"
    assert step.status == "STEP_FAILED"
    assert db_session.execute(select(ToolCall).where(ToolCall.task_id == task.id)).first() is None

    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == task.id).order_by(AgentEvent.sequence)
        ).scalars()
    ]
    assert "LANGGRAPH_WORKFLOW_STARTED" in event_types
    assert "LANGGRAPH_NODE_STARTED" in event_types
    assert "LANGGRAPH_TOOL_NODE_REQUESTED" in event_types
    assert "LANGGRAPH_TOOL_NODE_DENIED" in event_types
    assert "LANGGRAPH_NODE_FAILED" in event_types
    assert "LANGGRAPH_WORKFLOW_FAILED" in event_types
    denied_event = db_session.execute(
        select(AgentEvent).where(
            AgentEvent.task_id == task.id,
            AgentEvent.event_type == "LANGGRAPH_TOOL_NODE_DENIED",
        )
    ).scalar_one()
    assert denied_event.payload_json["status"] == "DENIED"
    assert denied_event.payload_json["denial_code"] == "langgraph_execution_disabled"

    replay_state = EventReplay(db_session).replay_state_json(task_id=task.id)
    assert replay_state["status"] == "FAILED"
    assert [event["event_type"] for event in replay_state["langgraph_events"]] == [
        "LANGGRAPH_WORKFLOW_STARTED",
        "LANGGRAPH_NODE_STARTED",
        "LANGGRAPH_TOOL_NODE_REQUESTED",
        "LANGGRAPH_TOOL_NODE_DENIED",
        "LANGGRAPH_NODE_FAILED",
        "LANGGRAPH_WORKFLOW_FAILED",
    ]

    plan_response = TestClient(app).get(f"/api/tasks/{task.id}/plan", headers=AUTH_HEADERS)
    assert plan_response.status_code == 200
    trace_types = [
        item["event_type"] for item in plan_response.json()["steps"][0]["execution_trace"]
    ]
    assert "LANGGRAPH_TOOL_NODE_DENIED" in trace_types


def test_langgraph_node_execution_uses_sandbox_bridge_when_enabled(
    db_session: Session,
    monkeypatch,
    set_feature_flags,
) -> None:
    set_feature_flags("langgraph_workflow_import_enabled,langgraph_workflow_execution_enabled")
    _create_agent(db_session)
    _approved_langgraph_package(db_session)

    class FakeGateway:
        def __init__(self, **kwargs) -> None:
            pass

        def complete(self, request_payload: ModelRequest) -> ModelResponse:
            return ModelResponse(
                content="""
                {
                  "summary": "Run approved workflow",
                  "steps": [
                    {
                      "key": "workflow_step",
                      "description": "Run imported LangGraph workflow",
                      "execution_mode": "langgraph_node",
                      "requires_sandbox": true,
                      "can_spawn_subagent": false,
                      "depends_on": [],
                      "tool_hints": ["langgraph:main"],
                      "acceptance_criteria": ["Workflow emits Harness evidence"],
                      "risk_level": "medium",
                      "artifact_expectations": ["workflow event trace"]
                    }
                  ]
                }
                """,
                model_provider=request_payload.model_provider,
                model_name=request_payload.model_name,
                usage={},
                raw_response={"mode": "fake"},
            )

    class FakeBridge:
        def invoke(self, *, workflow, task, plan, step) -> LangGraphBridgeResult:
            assert workflow.graph_id == "main"
            assert workflow.version.type == CAPABILITY_TYPE_LANGGRAPH_WORKFLOW
            assert task.agent_id == "langgraph-agent"
            assert step.execution_mode == "langgraph_node"
            return LangGraphBridgeResult(
                summary="Fake compiled graph completed",
                output="langgraph-output",
                metadata={"compiled_graph": "fake", "graph_id": workflow.graph_id},
            )

    original_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str, *args, **kwargs):
        if name == "langgraph":
            return ModuleSpec("langgraph", loader=None)
        return original_find_spec(name, *args, **kwargs)

    monkeypatch.setattr("app.agents.executor.AuditedModelGateway", FakeGateway)
    monkeypatch.setattr("importlib.util.find_spec", fake_find_spec)
    monkeypatch.setattr(
        "app.agents.langgraph_runner.get_langgraph_sandbox_bridge",
        lambda: FakeBridge(),
    )
    task = Task(
        organization_id="dev-org",
        agent_id="langgraph-agent",
        created_by="dev-engineer",
        title="LangGraph bridge run",
        goal="Run imported workflow through bridge",
        status="CREATED",
        model_provider="default",
        model_name="default",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(task)
    db_session.flush()

    response = TestClient(app).post(f"/api/tasks/{task.id}/start", headers=AUTH_HEADERS)

    assert response.status_code == 202
    assert response.json()["status"] == "COMPLETED"
    step = db_session.execute(select(TaskStep).where(TaskStep.task_id == task.id)).scalar_one()
    assert step.execution_mode == "langgraph_node"
    assert step.status == "STEP_COMPLETED"
    assert db_session.execute(select(ToolCall).where(ToolCall.task_id == task.id)).first() is None

    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == task.id).order_by(AgentEvent.sequence)
        ).scalars()
    ]
    assert "LANGGRAPH_WORKFLOW_STARTED" in event_types
    assert "LANGGRAPH_NODE_STARTED" in event_types
    assert "LANGGRAPH_TOOL_NODE_REQUESTED" in event_types
    assert "LANGGRAPH_TOOL_NODE_COMPLETED" in event_types
    assert "LANGGRAPH_NODE_COMPLETED" in event_types
    assert "LANGGRAPH_WORKFLOW_COMPLETED" in event_types
    assert "LANGGRAPH_TOOL_NODE_DENIED" not in event_types

    completed_event = db_session.execute(
        select(AgentEvent).where(
            AgentEvent.task_id == task.id,
            AgentEvent.event_type == "LANGGRAPH_TOOL_NODE_COMPLETED",
        )
    ).scalar_one()
    assert completed_event.payload_json["status"] == "COMPLETED"
    assert completed_event.payload_json["result"]["compiled_graph"] == "fake"


@pytest.mark.parametrize(
    "request_kind",
    [
        "direct_network",
        "host_file",
        "raw_secret",
        "model_gateway",
        "retriever",
        "side_effect_tool",
    ],
)
def test_langgraph_bridge_permission_denials_emit_harness_denied_events(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    set_feature_flags,
    request_kind: str,
) -> None:
    set_feature_flags("langgraph_workflow_import_enabled,langgraph_workflow_execution_enabled")
    _create_agent(db_session)
    _approved_langgraph_package(db_session)
    _patch_langgraph_optional_dependency(monkeypatch)

    class DenyingBridge:
        def invoke(self, *, workflow, task, plan, step) -> LangGraphBridgeResult:
            raise PermissionError(
                f"{request_kind} access denied; route external effects through Harness bridges"
            )

    monkeypatch.setattr(
        "app.agents.langgraph_runner.get_langgraph_sandbox_bridge",
        lambda: DenyingBridge(),
    )
    task = _langgraph_execution_task(db_session, title=f"LangGraph denied {request_kind}")
    step = PlanStep(
        key="workflow_step",
        description="Run imported LangGraph workflow",
        execution_mode="langgraph_node",
        requires_sandbox=True,
        can_spawn_subagent=False,
        tool_hints=["langgraph:main"],
        acceptance_criteria=["Workflow emits Harness evidence"],
        risk_level="medium",
    )
    plan = _langgraph_plan_row(db_session, task, step)

    result = LangGraphRunnerAdapter(
        session=db_session,
        event_store=EventStore(db_session),
    ).execute(task=task, plan=plan, step=step)

    assert result.status == "STEP_FAILED"
    assert result.tool_calls == []
    denied_event = db_session.execute(
        select(AgentEvent).where(
            AgentEvent.task_id == task.id,
            AgentEvent.event_type == "LANGGRAPH_TOOL_NODE_DENIED",
        )
    ).scalar_one()
    assert denied_event.payload_json["denial_code"] == "langgraph_bridge_permission_denied"
    assert request_kind in denied_event.payload_json["reason"]
    assert db_session.execute(select(ToolCall).where(ToolCall.task_id == task.id)).first() is None


def test_planner_preserves_langgraph_node_and_never_marks_it_subagent(
    db_session: Session,
) -> None:
    task = Task(
        organization_id="dev-org",
        created_by="dev-engineer",
        title="Plan LangGraph",
        goal="Use imported workflow",
        status="CREATED",
        model_provider="default",
        model_name="default",
    )
    db_session.add(task)
    db_session.flush()

    plan = DeterministicPlanner().create_plan(
        task,
        model_content="""
        {
          "summary": "LangGraph plan",
          "steps": [
            {
              "key": "workflow_step",
              "description": "Run workflow",
              "execution_mode": "langgraph_node",
              "requires_sandbox": true,
              "can_spawn_subagent": true,
              "tool_hints": ["langgraph:main"],
              "acceptance_criteria": ["done"],
              "risk_level": "medium"
            }
          ]
        }
        """,
    )

    assert plan.steps[0].execution_mode == "langgraph_node"
    assert plan.steps[0].can_spawn_subagent is False
    assert any("LangGraph workflow" in warning for warning in plan.validation_warnings)


def test_langchain_tool_adapter_is_mcp_shaped_and_reports_optional_dependency(
    set_feature_flags,
) -> None:
    set_feature_flags("langgraph_workflow_import_enabled,langchain_adapter_enabled")
    metadata = langchain_tool_metadata()
    result = LangChainToolAdapter().execute(
        metadata=metadata,
        input_json={"tool_name": "demo", "arguments": {"api_key": "sk-secret"}},
        config_json={},
        secret_value=None,
    )

    assert metadata.source == "mcp"
    assert metadata.mcp_server == "langchain"
    assert result.output_json["metadata"].get("source", "mcp") != "langchain"
    if importlib.util.find_spec("langchain_core") is None:
        assert result.output_json["status"] == "error"
        assert result.output_json["error"]["code"] == "missing_optional_dependency"
    else:
        assert result.output_json["status"] == "ok"
        assert result.output_json["result"]["arguments"]["api_key"] == "[REDACTED]"
        assert result.output_json["metadata"]["source"] == "mcp"


def test_langchain_tool_adapter_rejects_non_mcp_metadata() -> None:
    metadata = langchain_tool_metadata().model_copy(update={"source": "builtin"})

    result = LangChainToolAdapter().execute(
        metadata=metadata,
        input_json={"tool_name": "demo"},
        config_json={},
        secret_value=None,
    )

    assert result.output_json["status"] == "error"
    assert result.output_json["error"]["code"] == "invalid_metadata_source"


def test_langchain_adapter_feature_flag_registration_and_toolrunner_policy_authority(
    db_session: Session,
    set_feature_flags,
) -> None:
    set_feature_flags("langgraph_workflow_import_enabled")
    disabled_registry = AdapterRegistry()
    register_builtin_adapters(disabled_registry)
    assert disabled_registry.get("langchain.invoke_tool") is None

    set_feature_flags("langgraph_workflow_import_enabled,langchain_adapter_enabled")
    enabled_registry = AdapterRegistry()
    register_builtin_adapters(enabled_registry)
    assert enabled_registry.get("langchain.invoke_tool") is not None

    _create_agent(db_session, agent_id="langchain-agent")
    metadata = langchain_tool_metadata()
    registry = CapabilityRegistry(db_session, "dev-org")
    package = registry.stage_private_package(
        manifest={
            "name": "langchain-invoke-tool",
            "version": "1.0.0",
            "description": "LangChain MCP-shaped adapter package",
            "package_type": "tool_definition",
            "permissions": [],
            "tool_metadata": metadata.model_dump(mode="json"),
        },
        content={},
        created_by="test",
    )
    approved = registry.approve_package(package_id=package.id, approved_by="test")
    registry.attach_package_capability(
        package_id=approved.id,
        agent_id="langchain-agent",
        attached_by="test",
        enabled=True,
        priority=10,
    )
    task = Task(
        organization_id="dev-org",
        agent_id="langchain-agent",
        created_by="dev-engineer",
        title="LangChain policy",
        goal="Verify ToolRunner authority",
        status="RUNNING",
        model_provider="system",
        model_name="capability-registry",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(task)
    db_session.flush()

    execution = ToolRunner(
        session=db_session,
        agent_id="langchain-agent",
        capability_registry=registry,
    ).execute(
        task_id=task.id,
        tool_name="langchain.invoke_tool",
        input_json={"tool_name": "demo", "arguments": {"query": "release readiness"}},
        roles=["viewer"],
    )

    assert execution.allowed is False
    assert execution.tool_call.status == "DENIED"
    assert execution.tool_call.capability_version_id == approved.capability_version_id
    assert execution.tool_call.capability_snapshot_json["agent_id"] == "langchain-agent"
    assert execution.tool_call.error_message == "role is not allowed to run tool"


def test_langchain_retriever_grounding_persists_harness_evidence(
    db_session: Session,
) -> None:
    _create_agent(db_session, agent_id="retriever-agent")
    task = Task(
        organization_id="dev-org",
        agent_id="retriever-agent",
        created_by="dev-engineer",
        title="Retriever grounding",
        goal="Ground with LangChain retriever",
        status="COMPLETED",
        model_provider="default",
        model_name="default",
        created_at=utc_now(),
        updated_at=utc_now(),
        completed_at=utc_now(),
    )
    db_session.add(task)
    db_session.flush()

    retrieval_session, hits, citations, manifest = persist_langchain_grounding(
        session=db_session,
        organization_id="dev-org",
        agent_id="retriever-agent",
        run_id=task.id,
        query="orion",
        documents=[
            {
                "page_content": "orion fact from langchain retriever",
                "metadata": {"source": "fixture", "score": 0.87},
            }
        ],
        grounding_correlation_id="lc-grounding-1",
    )

    assert retrieval_session.metadata_json["source_kind"] == LANGCHAIN_CONNECTOR_SOURCE_KIND
    assert hits[0].source_kind == LANGCHAIN_CONNECTOR_SOURCE_KIND
    assert citations[0].source_kind == LANGCHAIN_CONNECTOR_SOURCE_KIND
    assert manifest.metadata_json["grounding_provider"] == LANGCHAIN_CONNECTOR_SOURCE_KIND
    assert db_session.get(RetrievalHit, hits[0].id) is not None
    assert db_session.get(CitationRecord, citations[0].id) is not None
    assert db_session.get(PromptAssemblyManifest, manifest.id) is not None

    dataset = EvalDataset(
        organization_id="dev-org",
        name="LangChain connector grounding eval",
        description="Eval evidence over LangChain retriever grounding",
        status="ACTIVE",
        created_by="test",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(dataset)
    db_session.flush()
    eval_case = EvalCase(
        dataset_id=dataset.id,
        source_task_id=task.id,
        input_json={"query": "orion"},
        expected_json={
            "grounding_contract": {
                "retrieval_session_id": retrieval_session.id,
                "prompt_manifest_id": manifest.id,
                "citation_hit_ids": [hits[0].id],
            }
        },
        capability_snapshot_json={},
        tags_json=["grounding", "langchain_connector"],
        created_at=utc_now(),
    )
    eval_run = EvalRun(
        dataset_id=dataset.id,
        organization_id="dev-org",
        agent_id="retriever-agent",
        status="COMPLETED",
        capability_snapshot_json={
            "source_kind": LANGCHAIN_CONNECTOR_SOURCE_KIND,
            "prompt_manifest_id": manifest.id,
        },
        metrics_json={"grounding_pass_rate": 1.0, "case_total": 1},
        created_by="test",
        started_at=utc_now(),
        completed_at=utc_now(),
        created_at=utc_now(),
    )
    db_session.add_all([eval_case, eval_run])
    db_session.flush()
    db_session.add(
        EvalResult(
            eval_run_id=eval_run.id,
            eval_case_id=eval_case.id,
            task_id=task.id,
            status="PASSED",
            scores_json={"grounding": 1.0},
            grader_trace_json={
                "passed": True,
                "grader": "deterministic_grounding_grader_v1",
                "grounding_provider": LANGCHAIN_CONNECTOR_SOURCE_KIND,
                "grounding_failures": [],
                "retrieval_session_id": retrieval_session.id,
                "prompt_manifest_id": manifest.id,
                "citation_hit_ids": [hits[0].id],
                "citation_keys": [citations[0].citation_key],
            },
            latency_ms=0,
            cost_usd="0",
            created_at=utc_now(),
        )
    )
    db_session.flush()

    quality = TestClient(app).get(
        "/api/observability/grounding-quality",
        headers=AUTH_HEADERS,
        params={"eval_run_id": eval_run.id},
    )
    assert quality.status_code == 200
    quality_item = quality.json()["items"][0]
    assert quality_item["retrieval_session_id"] == retrieval_session.id
    assert quality_item["prompt_manifest_id"] == manifest.id
    assert quality_item["citation_hit_ids"] == [hits[0].id]


def test_langgraph_package_version_reuse_new_version_and_rollback_disable(
    db_session: Session,
) -> None:
    _create_agent(db_session)
    registry = CapabilityRegistry(db_session, "dev-org")
    manifest = _langgraph_manifest("versioned-langgraph")
    package_a = registry.stage_private_package(
        manifest=manifest,
        content=_langgraph_content(),
        created_by="test",
    )
    approved_a = registry.approve_package(package_id=package_a.id, approved_by="test")
    version_a = approved_a.capability_version_id
    version_a_row = db_session.get(CapabilityVersion, version_a)
    assert version_a_row is not None

    same_package = registry.stage_private_package(
        manifest=manifest,
        content=_langgraph_content(),
        created_by="test",
    )
    assert same_package.id == package_a.id
    same_approved = registry.approve_package(package_id=same_package.id, approved_by="test")
    assert same_approved.capability_version_id == version_a

    package_b = registry.stage_private_package(
        manifest=manifest,
        content=_langgraph_content({"dependencies": ["."], "graphs": {"main": "./v2.py:graph"}}),
        created_by="test",
    )
    approved_b = registry.approve_package(package_id=package_b.id, approved_by="test")
    version_b = approved_b.capability_version_id
    assert version_b != version_a

    attachment = registry.attach_package_capability(
        package_id=approved_b.id,
        agent_id="langgraph-agent",
        attached_by="test",
        enabled=True,
        priority=10,
    )
    historical_task = _langgraph_execution_task(db_session, title="Historical LangGraph snapshot")
    historical_task.capability_snapshot_json = registry.create_snapshot(
        agent_id="langgraph-agent",
        task_id=historical_task.id,
        source="langgraph_workflow_run",
        versions=[version_a_row],
    )
    registry.set_attachment_enabled(attachment_id=attachment.id, enabled=False)
    assert registry.attached_langgraph_workflows("langgraph-agent") == []

    rolled_back = registry.rollback_package(
        package_id=approved_b.id,
        capability_version_id=version_a,
        updated_by="test",
    )
    assert rolled_back.capability_version_id == version_a
    assert db_session.get(CapabilityVersion, version_b) is not None
    assert db_session.get(CapabilityVersion, version_a) is not None
    assert historical_task.capability_snapshot_json["capability_version_ids"] == [version_a]
    assert historical_task.capability_snapshot_json["content_sha256_values"] == [
        version_a_row.content_sha256
    ]
