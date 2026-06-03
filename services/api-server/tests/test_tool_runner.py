from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Agent,
    Capability,
    CapabilityVersion,
    SandboxInstance,
    SystemSetting,
    Task,
    ToolApproval,
    ToolCall,
    utc_now,
)
from app.events.event_store import EventStore
from app.sandbox.docker_manager import SandboxCommandResult
from app.tools.capabilities import CapabilityRegistry
from app.tools.runner import ToolRunner


def create_task(
    db_session: Session,
    *,
    agent_id: str = "tool-runner-agent",
    tools: list[str] | None = None,
) -> Task:
    db_session.add(
        Agent(
            id=agent_id,
            organization_id=None,
            name="Tool Runner Agent",
            description="Owns explicit tool attachments for ToolRunner tests",
            role="tester",
            status="ACTIVE",
            model_provider="default",
            model_name="default",
            system_prompt="Run tools under attachment policy.",
            tools_json=tools or ["read_file", "list_files", "run_shell", "network_request"],
            routing_tags=[],
        )
    )
    db_session.flush()
    task = Task(
        organization_id="dev-org",
        agent_id=agent_id,
        created_by="dev-engineer",
        title="Tool runner",
        goal="Audit tool execution",
        status="RUNNING",
        model_provider="openai-compatible",
        model_name="default",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(task)
    db_session.flush()
    CapabilityRegistry(db_session, task.organization_id).backfill_agent_attachments(
        agent_id,
        attached_by="test",
    )
    return task


def test_tool_runner_executes_read_file_and_writes_audit(
    db_session: Session,
    tmp_path: Path,
) -> None:
    task = create_task(db_session)
    target = tmp_path / "result.md"
    target.write_text("hello", encoding="utf-8")

    execution = ToolRunner(
        session=db_session,
        workspace_root=tmp_path,
        agent_id=task.agent_id,
    ).execute(
        task_id=task.id,
        tool_name="read_file",
        input_json={"path": "result.md"},
        roles=["engineer"],
    )

    assert execution.allowed is True
    assert execution.tool_call.status == "SUCCESS"
    assert execution.tool_call.capability_version_id is not None
    assert execution.tool_call.capability_content_sha256 is not None
    assert execution.tool_call.capability_snapshot_json["agent_id"] == task.agent_id
    assert execution.output["content"] == "hello"
    events = EventStore(db_session).list_by_task(task_id=task.id)
    assert [event.event_type for event in events] == [
        "POLICY_CHECKED",
        "TOOL_CALLED",
        "TOOL_RESULT_RECEIVED",
    ]


def test_tool_runner_records_adapter_snapshot_for_real_adapter(db_session: Session) -> None:
    task = create_task(db_session, tools=["github.list_issues"])

    execution = ToolRunner(session=db_session, agent_id=task.agent_id).execute(
        task_id=task.id,
        tool_name="github.list_issues",
        input_json={"repo": "acme/repo"},
        roles=["engineer"],
    )

    assert execution.allowed is True
    assert execution.output["result"]["error"] == "missing_secret"
    snapshot = execution.tool_call.capability_snapshot_json
    assert snapshot["adapter"]["slug"] == "github.list_issues"
    assert len(snapshot["adapter"]["adapter_sha256"]) == 64
    assert len(snapshot["adapter"]["input_schema_sha256"]) == 64


def test_tool_runner_requests_approval_for_sandbox_file_write(db_session: Session) -> None:
    task = create_task(db_session, tools=["sandbox.write_file"])

    execution = ToolRunner(session=db_session, agent_id=task.agent_id).execute(
        task_id=task.id,
        tool_name="sandbox.write_file",
        input_json={"path": "result.txt", "content": "hello", "idempotency_key": "file-1"},
        roles=["engineer"],
    )

    assert execution.allowed is False
    assert execution.tool_call.status == "PENDING_APPROVAL"
    assert execution.tool_call.requires_sandbox is True
    assert execution.tool_call.capability_snapshot_json["adapter"]["slug"] == "sandbox.write_file"
    approval = db_session.execute(select(ToolApproval)).scalar_one()
    assert approval.tool_call_id == execution.tool_call.id


def test_tool_runner_denies_non_idempotent_mcp_tool_without_idempotency_key(
    db_session: Session,
) -> None:
    task = create_task(db_session, tools=["slack.post_message"])
    db_session.add(
        SystemSetting(
            organization_id=task.organization_id,
            key="settings.policies",
            value_json={
                "risk_levels": [
                    {
                        "name": "high",
                        "requires_sandbox": False,
                        "approval": "auto",
                        "allowed_roles": ["admin", "engineer"],
                    }
                ],
                "approvals": {"manual_review": True, "deny_on_missing_policy": True},
                "sandbox": {"default_network": False, "default_timeout_seconds": 60},
                "audit": {"model_calls": True, "tool_calls": True, "policy_actions": True},
            },
            updated_by="test",
            updated_at=utc_now(),
        )
    )
    db_session.flush()

    execution = ToolRunner(session=db_session, agent_id=task.agent_id).execute(
        task_id=task.id,
        tool_name="slack.post_message",
        input_json={"channel": "C1", "text": "hello"},
        roles=["admin", "engineer"],
    )

    assert execution.allowed is False
    assert execution.tool_call.status == "DENIED"
    assert execution.tool_call.error_message == "non-idempotent MCP tool requires idempotency_key"


def test_tool_runner_denies_approval_request_without_idempotency_key(
    db_session: Session,
) -> None:
    task = create_task(db_session, tools=["slack.post_message"])

    execution = ToolRunner(session=db_session, agent_id=task.agent_id).request_approval(
        task_id=task.id,
        tool_name="slack.post_message",
        input_json={"channel": "C1", "text": "hello"},
    )

    assert execution.allowed is False
    assert execution.tool_call.status == "DENIED"
    assert execution.tool_call.error_message == "non-idempotent MCP tool requires idempotency_key"


def test_tool_runner_replays_write_tool_by_idempotency_key(db_session: Session) -> None:
    task = create_task(db_session, tools=["slack.post_message"])
    db_session.add(
        SystemSetting(
            organization_id=task.organization_id,
            key="settings.policies",
            value_json={
                "risk_levels": [
                    {
                        "name": "high",
                        "requires_sandbox": False,
                        "approval": "auto",
                        "allowed_roles": ["admin", "engineer"],
                    }
                ],
                "approvals": {"manual_review": True, "deny_on_missing_policy": True},
                "sandbox": {"default_network": False, "default_timeout_seconds": 60},
                "audit": {"model_calls": True, "tool_calls": True, "policy_actions": True},
            },
            updated_by="test",
            updated_at=utc_now(),
        )
    )
    db_session.flush()

    class FakeMCPAdapter:
        calls = 0

        def execute(self, **kwargs):
            from app.tools.mcp_adapter import MCPToolResult

            self.calls += 1
            return MCPToolResult(
                server="slack",
                method="post_message",
                output_json={"message": {"ts": "1.000"}, "source": "slack-api"},
            )

    adapter = FakeMCPAdapter()
    runner = ToolRunner(session=db_session, agent_id=task.agent_id, mcp_adapter=adapter)

    first = runner.execute(
        task_id=task.id,
        tool_name="slack.post_message",
        input_json={"channel": "C1", "text": "hello", "idempotency_key": "same-key"},
        roles=["admin", "engineer"],
    )
    second = runner.execute(
        task_id=task.id,
        tool_name="slack.post_message",
        input_json={"channel": "C1", "text": "hello", "idempotency_key": "same-key"},
        roles=["admin", "engineer"],
    )

    assert first.tool_call.status == "SUCCESS"
    assert second.tool_call.status == "SUCCESS"
    assert adapter.calls == 1
    assert second.output["idempotent_replay"] is True
    assert second.output["original_tool_call_id"] == first.tool_call.id


def test_tool_runner_denies_sandbox_tool_without_sandbox(db_session: Session) -> None:
    task = create_task(db_session)

    execution = ToolRunner(session=db_session, agent_id=task.agent_id).execute(
        task_id=task.id,
        tool_name="run_shell",
        input_json={"command": "pytest"},
        roles=["admin"],
    )

    assert execution.allowed is False
    assert execution.tool_call.status == "DENIED"
    tool_call = db_session.execute(select(ToolCall)).scalar_one()
    assert tool_call.error_message == "sandbox is required for tool"
    events = EventStore(db_session).list_by_task(task_id=task.id)
    assert [event.event_type for event in events] == [
        "POLICY_CHECKED",
        "POLICY_DENIED",
        "TOOL_DENIED_BY_POLICY",
    ]


def test_tool_runner_requires_agent_attachment_boundary(db_session: Session) -> None:
    task = create_task(db_session)

    execution = ToolRunner(session=db_session).execute(
        task_id=task.id,
        tool_name="read_file",
        input_json={"path": "pyproject.toml"},
        roles=["engineer"],
    )

    assert execution.allowed is False
    assert execution.tool_call.status == "DENIED"
    assert execution.tool_call.error_message == (
        "agent capability attachment is required for tool execution"
    )
    assert execution.tool_call.capability_version_id is None


def test_tool_runner_denies_network_request_for_engineer(db_session: Session) -> None:
    task = create_task(db_session)

    execution = ToolRunner(session=db_session, agent_id=task.agent_id).execute(
        task_id=task.id,
        tool_name="network_request",
        input_json={"method": "GET", "url": "https://example.com", "headers": {}},
        roles=["engineer"],
    )

    assert execution.allowed is False
    assert execution.tool_call.status == "DENIED"
    assert execution.tool_call.error_message == "role is not allowed to run tool"


def test_tool_runner_reads_policy_settings_for_risk_level(db_session: Session) -> None:
    task = create_task(db_session)
    db_session.add(
        SystemSetting(
            organization_id=task.organization_id,
            key="settings.policies",
            value_json={
                "risk_levels": [
                    {
                        "name": "low",
                        "requires_sandbox": True,
                        "approval": "auto",
                        "allowed_roles": ["admin", "engineer"],
                    }
                ],
                "approvals": {"manual_review": True, "deny_on_missing_policy": True},
                "sandbox": {"default_network": False, "default_timeout_seconds": 60},
                "audit": {"model_calls": True, "tool_calls": True, "policy_actions": True},
            },
            updated_by="dev-admin",
            updated_at=utc_now(),
        )
    )
    db_session.flush()

    execution = ToolRunner(session=db_session, agent_id=task.agent_id).execute(
        task_id=task.id,
        tool_name="read_file",
        input_json={"path": "pyproject.toml"},
        roles=["engineer"],
    )

    assert execution.allowed is False
    assert execution.tool_call.status == "DENIED"
    assert execution.tool_call.requires_sandbox is True
    assert execution.tool_call.error_message == "sandbox is required for tool"


def test_tool_runner_uses_policy_settings_admin_approval(db_session: Session) -> None:
    task = create_task(db_session)
    db_session.add(
        SystemSetting(
            organization_id=task.organization_id,
            key="settings.policies",
            value_json={
                "risk_levels": [
                    {
                        "name": "low",
                        "requires_sandbox": False,
                        "approval": "admin",
                        "allowed_roles": ["admin", "engineer"],
                    }
                ],
                "approvals": {"manual_review": True, "deny_on_missing_policy": True},
                "sandbox": {"default_network": False, "default_timeout_seconds": 60},
                "audit": {"model_calls": True, "tool_calls": True, "policy_actions": True},
            },
            updated_by="dev-admin",
            updated_at=utc_now(),
        )
    )
    db_session.flush()

    execution = ToolRunner(session=db_session, agent_id=task.agent_id).execute(
        task_id=task.id,
        tool_name="read_file",
        input_json={"path": "pyproject.toml"},
        roles=["engineer"],
    )

    assert execution.allowed is False
    assert execution.tool_call.status == "PENDING_APPROVAL"
    assert execution.tool_call.error_message == "tool requires admin approval"
    approval = db_session.execute(select(ToolApproval)).scalar_one()
    assert approval.status == "PENDING"
    assert approval.tool_call_id == execution.tool_call.id
    events = [event.event_type for event in EventStore(db_session).list_by_task(task_id=task.id)]
    assert events == ["POLICY_CHECKED", "TOOL_APPROVAL_REQUESTED"]


class FakeShellTool:
    def run(self, **kwargs) -> SandboxCommandResult:
        return SandboxCommandResult(
            stdout='{"status_code": 200, "body_preview": "ok"}',
            stderr="",
            exit_code=0,
            duration_ms=12,
        )


def test_tool_runner_enforces_network_allowlist(db_session: Session) -> None:
    task = create_task(db_session)
    sandbox = SandboxInstance(
        task_id=task.id,
        container_id="container-network",
        image="agent-runtime:latest",
        status="IDLE",
        cpu_limit="1.0",
        memory_limit_mb=1024,
        network_enabled=True,
        warm_pool_reused=False,
    )
    db_session.add_all(
        [
            sandbox,
            SystemSetting(
                organization_id=task.organization_id,
                key="settings.policies",
                value_json={
                    "risk_levels": [
                        {
                            "name": "high",
                            "requires_sandbox": True,
                            "approval": "admin",
                            "allowed_roles": ["admin"],
                        }
                    ],
                    "approvals": {"manual_review": True, "deny_on_missing_policy": True},
                    "sandbox": {
                        "default_network": True,
                        "default_timeout_seconds": 60,
                        "memory_mb": 1024,
                        "cpus": "1.0",
                        "workspace_quota_mb": 1024,
                        "network_allowlist": ["api.example.test", "*.service.example.test"],
                    },
                    "audit": {
                        "model_calls": True,
                        "tool_calls": True,
                        "policy_actions": True,
                    },
                },
                updated_by="dev-admin",
                updated_at=utc_now(),
            ),
        ]
    )
    db_session.flush()
    runner = ToolRunner(session=db_session, agent_id=task.agent_id, shell_tool=FakeShellTool())

    blocked = runner.execute(
        task_id=task.id,
        tool_name="network_request",
        input_json={"method": "GET", "url": "https://blocked.example.test", "headers": {}},
        roles=["admin"],
        sandbox=sandbox,
    )
    allowed = runner.execute(
        task_id=task.id,
        tool_name="network_request",
        input_json={"method": "GET", "url": "https://api.example.test/v1", "headers": {}},
        roles=["admin"],
        sandbox=sandbox,
    )
    exact_subdomain_blocked = runner.execute(
        task_id=task.id,
        tool_name="network_request",
        input_json={
            "method": "GET",
            "url": "https://sub.api.example.test/v1",
            "headers": {},
        },
        roles=["admin"],
        sandbox=sandbox,
    )
    wildcard_allowed = runner.execute(
        task_id=task.id,
        tool_name="network_request",
        input_json={
            "method": "GET",
            "url": "https://worker.service.example.test/v1",
            "headers": {},
        },
        roles=["admin"],
        sandbox=sandbox,
    )

    assert blocked.allowed is False
    assert blocked.tool_call.status == "DENIED"
    assert blocked.tool_call.error_message == "network host is not in allowlist"
    assert allowed.allowed is True
    assert allowed.tool_call.status == "SUCCESS"
    assert allowed.output["status_code"] == 200
    assert exact_subdomain_blocked.allowed is False
    assert exact_subdomain_blocked.tool_call.status == "DENIED"
    assert wildcard_allowed.allowed is True
    assert wildcard_allowed.tool_call.status == "SUCCESS"


def test_high_risk_package_test_invoke_is_policy_bounded_without_sandbox(
    db_session: Session,
) -> None:
    task = create_task(db_session, agent_id="high-risk-package-agent", tools=[])
    registry = CapabilityRegistry(db_session, task.organization_id)
    package = registry.stage_private_package(
        manifest={
            "name": "high_risk_packaged_tool",
            "version": "1.0.0",
            "description": "High risk packaged tool",
            "package_type": "tool_definition",
            "risk_level": "high",
            "permissions": ["shell"],
            "secret_refs": ["secret://capability/high-risk"],
            "tool_metadata": {
                "name": "high_risk_packaged_tool",
                "description": "High risk packaged tool",
                "category": "package",
                "source": "builtin",
                "risk_level": "high",
                "requires_sandbox": True,
                "network_policy": "none",
                "timeout_seconds": 10,
                "allowed_roles": ["admin", "engineer"],
                "audit_level": "elevated",
                "idempotent": False,
                "input_schema": {"type": "object"},
            },
        },
        content={},
        created_by="test",
    )
    registry.approve_package(package_id=package.id, approved_by="test")
    registry.attach_package_capability(
        package_id=package.id,
        agent_id=task.agent_id,
        attached_by="test",
    )

    execution = ToolRunner(
        session=db_session,
        agent_id=task.agent_id,
        capability_registry=registry,
    ).execute(
        task_id=task.id,
        tool_name="high_risk_packaged_tool",
        input_json={"command": "whoami"},
        roles=["admin"],
    )

    assert execution.allowed is False
    assert execution.tool_call.status == "DENIED"
    assert execution.tool_call.requires_sandbox is True
    assert execution.tool_call.error_message == "sandbox is required for tool"
    assert execution.tool_call.capability_version_id == package.capability_version_id


def test_package_capability_identifiers_fit_postgresql_string_bounds(
    db_session: Session,
) -> None:
    agent_id = "long-package-agent"
    create_task(db_session, agent_id=agent_id, tools=[])
    registry = CapabilityRegistry(db_session, "dev-org")
    long_name = "extremely-long-capability-package-name-" + ("segment-" * 40)
    package = registry.stage_private_package(
        manifest={
            "name": long_name,
            "version": "1.0.0",
            "description": "Package with a name longer than PostgreSQL key columns",
            "package_type": "tool_definition",
            "risk_level": "low",
            "permissions": [],
            "secret_refs": [],
            "tool_metadata": {
                "name": "long_packaged_tool",
                "description": "Long packaged tool",
                "category": "package",
                "source": "builtin",
                "risk_level": "low",
                "requires_sandbox": False,
                "network_policy": "none",
                "timeout_seconds": 10,
                "allowed_roles": ["admin", "engineer"],
                "audit_level": "standard",
                "idempotent": True,
                "input_schema": {"type": "object"},
            },
        },
        content={},
        created_by="test",
    )

    registry.approve_package(package_id=package.id, approved_by="test")
    capability = db_session.get(Capability, package.capability_id)
    version = db_session.get(CapabilityVersion, package.capability_version_id)

    assert len(package.package_key) <= 128
    assert capability is not None
    assert len(capability.capability_key) <= 128
    assert version is not None
    assert len(version.id) <= 64
