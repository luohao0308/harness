# Local Dev TestClient SQLite StaticPool

Category: `session-log`

Tags: `local-dev`, `backend-tests`, `sqlite`, `testclient`, `staticpool`

## Summary

The backend TestClient `no such table: agents` / `no such table: system_settings` failures are fixed. The test database fixture now uses a per-test in-memory SQLite database backed by `StaticPool`, so `Base.metadata.create_all()` and TestClient request handling share the same SQLite connection across pytest and worker threads.

This removes the previous blocker where direct endpoint tests passed but older TestClient-backed combinations failed because each SQLite `:memory:` connection had its own empty schema.

## Root Cause

`tests/conftest.py` created an engine with `sqlite+pysqlite:///:memory:` and the default pool. `Base.metadata.create_all()` ran on one connection, while TestClient request handling opened another connection through the same engine. With SQLite in-memory databases, that second connection sees a different empty database, so endpoint code failed on first query against tables such as `agents` or `system_settings`.

## Changes

- `services/api-server/tests/conftest.py` now uses `sqlite+pysqlite://` plus `poolclass=StaticPool` for the per-test engine.
- `services/api-server/app/api/agents/agent_chat/streaming.py` now buffers model chunks when the text shows post-processing signals such as XML function calls, implicit search text, or citation-like keys, preventing raw pre-tool/pre-citation text from leaking before correction.
- `services/api-server/app/agents/model_gateway.py` now keeps a compatibility call path for older tests/extensions that monkeypatch `model_gateway_for_provider(provider, timeout_seconds=...)` without the newer `session`, `organization_id`, and `user_id` keyword arguments.

## Validation

```text
cd services/api-server && .venv/bin/python -m pytest tests/test_agents.py::test_agent_orchestration_execute_continues_after_terminal_failed_assignment tests/test_agents.py::test_agent_orchestration_execute_runs_assignments_and_reduces -q
2 passed

cd services/api-server && .venv/bin/python -m pytest tests/test_model_gateway.py::test_provider_api_key_reuses_deepseek_secret_across_model_providers tests/test_settings.py::test_deepseek_model_settings_store_one_secret_for_multiple_models tests/test_settings.py::test_model_settings_health_endpoint_probes_real_provider -q
3 passed

cd services/api-server && .venv/bin/python -m pytest tests/test_agents.py::test_agent_orchestration_execute_continues_after_terminal_failed_assignment tests/test_agents.py::test_agent_orchestration_execute_runs_assignments_and_reduces tests/test_model_gateway.py::test_provider_api_key_reuses_deepseek_secret_across_model_providers tests/test_settings.py::test_deepseek_model_settings_store_one_secret_for_multiple_models tests/test_settings.py::test_model_settings_health_endpoint_probes_real_provider -q
5 passed

cd services/api-server && .venv/bin/python -m pytest tests/test_agents.py::test_agent_workspace_chat_stream_rewrites_unbound_citation_keys tests/test_agents.py::test_agent_workspace_chat_executes_xml_function_call_for_installed_mcp tests/test_agents.py::test_agent_workspace_chat_infers_installed_mcp_from_pending_search_text tests/test_agents.py::test_agent_plan_mode_surfaces_model_gateway_failure_without_fallback tests/test_agents.py::test_agent_run_create_surfaces_model_gateway_failure_without_fallback tests/test_agents.py::test_agent_run_create_uses_deterministic_plan_when_model_output_is_unparseable tests/test_agents.py::test_agent_run_create_records_repair_failure_before_deterministic_plan -q
7 passed

cd services/api-server && .venv/bin/python -m pytest tests/test_settings.py tests/test_model_gateway.py -q
32 passed

cd services/api-server && .venv/bin/python -m pytest tests/test_agents.py -q
68 passed

cd services/api-server && .venv/bin/python -m ruff check tests/conftest.py app/agents/model_gateway.py app/api/agents/agent_chat/streaming.py
passed

python3 -m py_compile services/api-server/tests/conftest.py services/api-server/app/agents/model_gateway.py services/api-server/app/api/agents/agent_chat/streaming.py
passed
```
