from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SandboxInstance, SystemSetting, Task, ToolCall, utc_now
from app.events.event_store import EventStore
from app.sandbox.docker_manager import SandboxCommandResult
from app.tools.runner import ToolRunner


def create_task(db_session: Session) -> Task:
    task = Task(
        organization_id="dev-org",
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
    return task


def test_tool_runner_executes_read_file_and_writes_audit(
    db_session: Session,
    tmp_path: Path,
) -> None:
    task = create_task(db_session)
    target = tmp_path / "result.md"
    target.write_text("hello", encoding="utf-8")

    execution = ToolRunner(session=db_session, workspace_root=tmp_path).execute(
        task_id=task.id,
        tool_name="read_file",
        input_json={"path": "result.md"},
        roles=["engineer"],
    )

    assert execution.allowed is True
    assert execution.tool_call.status == "SUCCESS"
    assert execution.output["content"] == "hello"
    events = EventStore(db_session).list_by_task(task_id=task.id)
    assert [event.event_type for event in events] == [
        "POLICY_CHECKED",
        "TOOL_CALLED",
        "TOOL_RESULT_RECEIVED",
    ]


def test_tool_runner_denies_sandbox_tool_without_sandbox(db_session: Session) -> None:
    task = create_task(db_session)

    execution = ToolRunner(session=db_session).execute(
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


def test_tool_runner_denies_network_request_for_engineer(db_session: Session) -> None:
    task = create_task(db_session)

    execution = ToolRunner(session=db_session).execute(
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

    execution = ToolRunner(session=db_session).execute(
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

    execution = ToolRunner(session=db_session).execute(
        task_id=task.id,
        tool_name="read_file",
        input_json={"path": "pyproject.toml"},
        roles=["engineer"],
    )

    assert execution.allowed is False
    assert execution.tool_call.status == "DENIED"
    assert execution.tool_call.error_message == "tool requires admin approval"


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
    runner = ToolRunner(session=db_session, shell_tool=FakeShellTool())

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
