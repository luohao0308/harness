from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import observability as observability_api
from app.db.models import (
    AdminAuditEvent,
    Agent,
    AgentEvent,
    AgentRun,
    DataExport,
    EvalCase,
    EvalDataset,
    EvalResult,
    EvalRun,
    KnowledgeSource,
    ModelCall,
    ModelPricing,
    OtelSpan,
    SubagentOutput,
    SubagentSpecialist,
    Task,
    ToolCall,
    utc_now,
)
from app.main import app
from tests.conftest import AUTH_HEADERS

ADMIN_HEADERS = {"Authorization": "Bearer dev-admin-token"}


def test_enterprise_harness_chain_projects_across_all_sidebar_surfaces(
    db_session: Session,
) -> None:
    observability_api._cost_rollup_last_seen.clear()
    task_id = "enterprise-chain-task"
    subagent_id = "enterprise-chain-subagent"
    specialist_id = "enterprise-chain-specialist"
    trace_id = "enterprise-chain-trace"
    now = utc_now()

    db_session.add_all(
        [
            Agent(
                id="default",
                organization_id=None,
                name="Default Agent",
                description="Enterprise chain agent",
                role="engineer",
                status="ACTIVE",
                model_provider="deepseek-flash",
                model_name="deepseek-v4-flash",
                system_prompt="Operate with evidence.",
                tools_json=["read_file"],
                routing_tags=["enterprise"],
                max_parallel_assignments=2,
                created_at=now,
                updated_at=now,
            ),
            Task(
                id=task_id,
                organization_id="dev-org",
                agent_id="default",
                created_by="dev-engineer",
                title="Enterprise harness chain",
                goal="Prove sidebar feature linkage",
                status="COMPLETED",
                model_provider="deepseek-flash",
                model_name="deepseek-v4-flash",
                max_runtime_seconds=1800,
                max_subagents=5,
                enable_sandbox=True,
                enable_network=False,
                created_at=now,
                updated_at=now,
                completed_at=now,
            ),
            SubagentSpecialist(
                id=specialist_id,
                organization_id="dev-org",
                slug="code-reviewer",
                display_name="代码审查专家",
                description="Review enterprise delivery",
                role="reviewer",
                system_prompt="review",
                capability_slugs_json=[],
                output_schema_json={"type": "object"},
                budget_json={},
                trigger_keywords_json=["review"],
                visibility="org",
                status="ACTIVE",
                created_by="dev-engineer",
                created_at=now,
                updated_at=now,
            ),
            AgentRun(
                id=subagent_id,
                task_id=task_id,
                parent_agent_id=None,
                agent_type="subagent",
                status="SUCCESS",
                specialist_id=specialist_id,
                context_json={
                    "source": "enterprise_harness_chain",
                    "team_id": "enterprise-team",
                    "team_agent_slot_id": "reviewer",
                    "step_key": "review-release-chain",
                    "fanout_batch_id": "enterprise-fanout",
                    "fanout_index": 0,
                    "fanout_total": 2,
                    "result": {
                        "summary": "Team bridge output",
                        "tool_results": [
                            {
                                "tool_call_id": "enterprise-tool-call",
                                "tool_name": "read_file",
                                "status": "SUCCESS",
                                "allowed": True,
                                "duration_ms": 10,
                                "input_json": {"path": "README.md"},
                                "output": {"content": "Harness", "size_bytes": 7},
                                "error_message": None,
                            }
                        ],
                        "context_summary": {
                            "total_tool_results": 1,
                            "retained_tool_results": 1,
                            "omitted_tool_results": 0,
                        },
                    },
                },
                started_at=now,
                completed_at=now,
            ),
            SubagentOutput(
                agent_run_id=subagent_id,
                task_id=task_id,
                specialist_id=specialist_id,
                output_json={"result": "passed", "summary": "Team bridge output"},
                output_schema_sha256="a" * 64,
                budget_consumed_json={
                    "cost_usd": "0.000280",
                    "prompt_tokens": 1000,
                    "completion_tokens": 500,
                },
                budget_exceeded_json=[],
                written_at=now,
            ),
            ModelPricing(
                id="enterprise-price-deepseek-flash",
                organization_id="dev-org",
                provider="deepseek-flash",
                model="deepseek-v4-flash",
                prompt_per_1k_usd="0.00014",
                completion_per_1k_usd="0.00028",
                cache_prompt_per_1k_usd="0.0000028",
                currency="USD",
                active=True,
                source="official",
                created_at=now,
                updated_at=now,
            ),
            ModelCall(
                id="enterprise-model-call",
                task_id=task_id,
                agent_run_id=subagent_id,
                model_provider="deepseek-flash",
                model_name="deepseek-v4-flash",
                status="SUCCESS",
                prompt_tokens=1000,
                completion_tokens=500,
                duration_ms=120,
                request_json={},
                response_json={"content": "enterprise complete"},
                created_at=now,
            ),
            ToolCall(
                id="enterprise-tool-call",
                task_id=task_id,
                agent_run_id=subagent_id,
                tool_name="read_file",
                status="SUCCESS",
                risk_level="low",
                capability_snapshot_json={"adapter": {"slug": "filesystem"}},
                requires_sandbox=False,
                duration_ms=10,
                input_json={"path": "README.md"},
                output_json={"content": "Harness"},
                created_at=now,
            ),
            KnowledgeSource(
                id="enterprise-knowledge-source",
                organization_id="dev-org",
                agent_id="default",
                name="Enterprise Knowledge",
                description="Grounds the enterprise chain",
                source_type="document",
                status="ACTIVE",
                health_status="HEALTHY",
                settings_json={},
                metadata_json={"scope": "enterprise"},
                created_by="dev-engineer",
                created_at=now,
                updated_at=now,
            ),
            AgentEvent(
                task_id=task_id,
                agent_run_id=subagent_id,
                sequence=1,
                event_type="SUBAGENT_SPAWNED",
                payload_json={"subagent_id": subagent_id, "source": "enterprise_harness_chain"},
                actor_type="system",
                actor_id=None,
                trace_id=trace_id,
                created_at=now,
            ),
            OtelSpan(
                organization_id="dev-org",
                trace_id=trace_id,
                span_id="span-enterprise",
                parent_span_id=None,
                name="team.subagent.project",
                kind="internal",
                start_time=now,
                end_time=now + timedelta(milliseconds=30),
                duration_ms=30,
                attributes_json={"subagent_id": subagent_id, "team_id": "enterprise-team"},
                status="OK",
                task_id=task_id,
                agent_run_id=subagent_id,
                created_at=now,
            ),
            AdminAuditEvent(
                id="enterprise-audit",
                organization_id="dev-org",
                actor_id="dev-engineer",
                event_type="ADMIN_ACTION",
                resource_type="team",
                resource_id="enterprise-team",
                action="team.subagent.projected",
                payload_json={"subagent_id": subagent_id, "task_id": task_id},
                created_at=now,
            ),
            DataExport(
                id="enterprise-export",
                organization_id="dev-org",
                requested_by="dev-engineer",
                status="completed",
                requested_at=now,
                completed_at=now,
                file_path="/tmp/enterprise-export.json",
                file_sha256="b" * 64,
                size_bytes=2048,
                expires_at=now + timedelta(days=7),
            ),
            EvalDataset(
                id="enterprise-dataset",
                organization_id="dev-org",
                name="Enterprise Cost Gate",
                description="Cost and chain evidence",
                status="ACTIVE",
                created_by="dev-engineer",
                created_at=now,
                updated_at=now,
            ),
            EvalCase(
                id="enterprise-case",
                dataset_id="enterprise-dataset",
                source_task_id=task_id,
                input_json={"task_id": task_id},
                expected_json={"status": "COMPLETED"},
                tags_json=["enterprise"],
                created_at=now,
            ),
            EvalRun(
                id="enterprise-eval-run",
                dataset_id="enterprise-dataset",
                organization_id="dev-org",
                agent_id="default",
                status="COMPLETED",
                metrics_json={
                    "cost_contract_pass_rate": 1,
                    "pricing_blocking_statuses": [],
                    "case_total": 1,
                },
                created_by="dev-engineer",
                started_at=now,
                completed_at=now,
                created_at=now,
            ),
            EvalResult(
                id="enterprise-eval-result",
                eval_run_id="enterprise-eval-run",
                eval_case_id="enterprise-case",
                task_id=task_id,
                status="PASSED",
                scores_json={"task_success": 1},
                grader_trace_json={"cost_contract": {"passed": True, "pricing_status": "verified"}},
                latency_ms=120,
                cost_usd="0.00028",
                created_at=now,
            ),
        ]
    )
    db_session.commit()

    client = TestClient(app)

    workspace = client.get(f"/api/agents/runs/{task_id}/workspace", headers=AUTH_HEADERS)
    assert workspace.status_code == 200, workspace.text
    workspace_payload = workspace.json()
    assert workspace_payload["run"]["id"] == task_id
    assert workspace_payload["model_calls"][0]["id"] == "enterprise-model-call"
    assert workspace_payload["tool_calls"][0]["id"] == "enterprise-tool-call"
    assert workspace_payload["subagents"][0]["id"] == subagent_id

    task_result = client.get(f"/api/tasks/{task_id}/result", headers=AUTH_HEADERS)
    assert task_result.status_code == 200, task_result.text
    result_payload = task_result.json()
    assert result_payload["subagent_results"][0]["id"] == subagent_id
    assert result_payload["subagent_results"][0]["specialist_output"]["result"] == "passed"

    subagents = client.get("/api/subagents", headers=AUTH_HEADERS)
    assert subagents.status_code == 200, subagents.text
    assert any(item["id"] == subagent_id for item in subagents.json()["items"])
    subagent_detail = client.get(f"/api/subagents/{subagent_id}", headers=AUTH_HEADERS)
    assert subagent_detail.status_code == 200, subagent_detail.text
    assert subagent_detail.json()["output"]["output_json"]["summary"] == "Team bridge output"

    specialist_stats = client.get(
        f"/api/subagent-specialists/{specialist_id}/stats",
        headers=AUTH_HEADERS,
    )
    assert specialist_stats.status_code == 200, specialist_stats.text
    assert specialist_stats.json()["success_count"] == 1

    knowledge = client.get("/api/agents/default/knowledge/sources", headers=AUTH_HEADERS)
    assert knowledge.status_code == 200, knowledge.text
    assert knowledge.json()["items"][0]["name"] == "Enterprise Knowledge"

    cost = client.get(
        "/api/observability/cost-rollup?window=7d&group_by=provider",
        headers=AUTH_HEADERS,
    )
    assert cost.status_code == 200, cost.text
    cost_payload = cost.json()
    assert cost_payload["breakdown"][0]["key"] == "deepseek-flash/deepseek-v4-flash"
    assert cost_payload["breakdown"][0]["pricing_status"] == "verified"

    traces = client.get("/api/observability/traces", headers=AUTH_HEADERS)
    assert traces.status_code == 200, traces.text
    assert traces.json()["items"][0]["trace_id"] == trace_id
    trace_detail = client.get(f"/api/observability/traces/{trace_id}", headers=AUTH_HEADERS)
    assert trace_detail.status_code == 200, trace_detail.text
    assert trace_detail.json()["spans"][0]["attributes"]["subagent_id"] == subagent_id

    eval_detail = client.get("/api/evals/runs/enterprise-eval-run", headers=AUTH_HEADERS)
    assert eval_detail.status_code == 200, eval_detail.text
    assert eval_detail.json()["metrics_json"]["cost_contract_pass_rate"] == 1
    assert eval_detail.json()["results"][0]["grader_trace_json"]["cost_contract"]["passed"] is True

    audit = client.get("/api/audit?resource_type=team", headers=ADMIN_HEADERS)
    assert audit.status_code == 200, audit.text
    assert audit.json()["items"][0]["payload_json"]["subagent_id"] == subagent_id

    exports = client.get("/api/organizations/dev-org/exports", headers=ADMIN_HEADERS)
    assert exports.status_code == 200, exports.text
    assert exports.json()["items"][0]["id"] == "enterprise-export"
