# LangGraph/LangChain Compatibility Harness V1

Category: `session-log`

Tags: `langgraph`, `langchain`, `capability-registry`, `eval`, `session-log`, `runtime-evidence`

## Summary

LangGraph/LangChain Compatibility Harness V1 adds compatibility without moving runtime authority out of Harness. LangGraph workflows are imported as immutable capability packages and can be attached to agents, but they are not ToolRunner capabilities. LangChain tools are adapted only through MCP-shaped metadata, and LangChain retriever output is persisted as Harness grounding evidence.

## Scope

- PRD: `.omx/plans/prd-langgraph-langchain-compatibility-harness-v1.md`
- Test spec: `.omx/plans/test-spec-langgraph-langchain-compatibility-harness-v1.md`
- Backend capability/runtime/eval implementation under `services/api-server/app`
- Regression tests under `services/api-server/tests`
- Migration: `services/api-server/alembic/versions/20260607_0034_create_langgraph_eval_experiments.py`

## Evidence

```text
cd services/api-server && .venv/bin/python -m pytest tests/test_tool_registry.py tests/test_planner_executor.py tests/test_executor_multistep.py tests/test_observability.py::test_runtime_architecture_counts_langgraph_steps tests/test_dag_scheduler.py tests/test_langgraph_langchain_compat.py tests/test_eval_experiments.py -q -> 122 passed
cd services/api-server && .venv/bin/python -m pytest tests/test_langgraph_langchain_compat.py tests/test_eval_experiments.py -q -> 37 passed
cd services/api-server && .venv/bin/python -m ruff check app tests -> passed
cd services/api-server && rm -f /tmp/harness-langgraph-audit.sqlite && DATABASE_URL=sqlite:////tmp/harness-langgraph-audit.sqlite .venv/bin/alembic upgrade head -> passed through 20260607_0034
cd apps/agent-console && npm test -- ToolRegistryPage.marketplace.test.tsx KnowledgePage.test.tsx RunDetailPage.optimizer.test.tsx ObservabilityV1Pages.test.tsx EvalHarnessPage.langgraph.test.tsx -> 5 files / 14 tests passed
cd apps/agent-console && npm run lint -- --pretty false -> passed
cd apps/agent-console && npm run build -> passed
cd apps/agent-console && HARNESS_PLAYWRIGHT_EXTERNAL_SERVER=1 npm run e2e:smoke -> 21 passed
API restarted in tmux session harness-api-langgraph; GET http://127.0.0.1:8000/health -> {"status":"ok","service":"api-server"}
Agent Console restarted in tmux session harness-console-langgraph; HEAD http://127.0.0.1:5173/ -> HTTP 200
Temporary Playwright Vite session harness-console-playwright; HEAD http://127.0.0.1:5177/ -> HTTP 200
git diff --check -> passed
```

Visual summary:

```text
docs/reports/langgraph-langchain-visual-summary-2026-06-03.html
```

Subagent gate:

```text
Architect review -> PASS
Frontend/design review -> PASS after Tool Registry LangChain invoke payload and Eval arm truncation fixes
Code review -> PASS after env path, Eval arm status, duplicate graph id, and Windows absolute-path fixes
Test engineering review -> PASS after adding import, isolation, sandbox, retriever, Eval status, snapshot, and Windows path coverage
Final verifier -> PASS after latest 37-test compatibility/eval subset, 122-test affected backend suite, Ruff, service smoke, and frontend evidence
```

## Decisions

- `langgraph_workflow` is allowed as a capability package type but remains outside `EXECUTABLE_CAPABILITY_TYPES`, ToolRunner resolution, agent tool registry snapshots, MCP discovery, Workspace implicit tool inference, and `/test-invoke`.
- LangGraph import stores `langgraph.json` in package/version `content_json`, validates graph ids, graph paths, env refs, dependencies, public-source hashes, and performs no remote code execution during staging.
- LangGraph path validation rejects POSIX absolute/tilde/parent escapes and Windows drive-letter absolute paths such as `C:\...` and `C:/...` for graph specs, env string/list entries, and dependencies.
- `langgraph_node` is first-class plan execution metadata across planner normalization, persisted `TaskStep.execution_mode`, DAG execution, task plan traces, replay, EventStore, and observability counts.
- `LangGraphRunnerAdapter` defaults to fail-closed execution-disabled evidence. Enabled execution requires `langgraph_workflow_execution_enabled`, optional `langgraph`, an approved attached immutable workflow, and a configured Harness sandbox bridge.
- LangChain tools use the existing `ToolAdapter` protocol and expose `ToolMetadata(source="mcp")`; no `source="langchain"` runtime authority exists.
- LangChain retriever grounding writes `RetrievalHit`, `CitationRecord`, and `PromptAssemblyManifest` with `source_kind="langchain_connector"`.
- Eval contrast experiments are projection APIs over existing `EvalRun`/`EvalResult` rows; `RegressionDelta` remains the baseline/current authority.
- The Agent Console exposes LangGraph and LangChain in product surfaces, not as hidden backend-only switches: Tool Registry has workflow import and adapter dialogs, Knowledge has a LangChain Retriever connector, Eval Harness has LangGraph-vs-native experiments, Run Detail renders LangGraph event evidence, and Observability counts `langgraph_node` steps.
- The one-page HTML visual summary captures these additions as diagrams for quick stakeholder review.

## Remaining Boundaries

- Production execution remains disabled by default.
- Live LangGraph package execution requires a configured Harness sandbox bridge; this slice proves the bridge-gated runtime path with a fake compiled graph and keeps the default no-bridge path fail-closed.
- Zip/archive upload, arbitrary pip install, unsigned remote execution, LangSmith hosted platform behavior, and LangGraph checkpoint/store authority remain out of scope for v1.
