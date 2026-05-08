# 10 任务进度看板

本文件是人读任务进度看板。机器事实源是 [task-progress.yaml](../ai/task-progress.yaml)。

## 当前状态

```text
当前阶段：09-portfolio-demo-docs
当前状态：completed
当前验证：passed
执行模式：Spec-first development + stage-gated implementation + vertical slice demo
```

## 阶段进度

| 阶段 | 名称 | 状态 | 文档 | Demo 闭环 | 验证结果 |
|---|---|---|---|---|---|
| 01 | Agent Graph Runtime | completed | `docs/ai/stages/01-agent-graph-runtime.md` | Agent 输入 -> Plan DAG -> Executor -> Subagent/Assignments -> Console 状态 | passed |
| 02 | Event Store + Recovery | completed | `docs/ai/stages/02-event-store-recovery.md` | Run -> Events -> Restart -> Recovery -> Replay | passed |
| 03 | Agent Run Console | completed | `docs/ai/stages/03-agent-run-console.md` | Chat + DAG + Trace + Tools + Guardrails + Eval + Replay | passed |
| 04 | Tool / MCP Runtime | completed | `docs/ai/stages/04-tool-mcp-runtime.md` | Tool Registry -> Policy -> Execute -> Trace | passed |
| 05 | Guardrail / Policy Engine | completed | `docs/ai/stages/05-guardrail-policy-engine.md` | Dangerous action -> Policy block or approval -> Audit | passed |
| 06 | Eval Harness | completed | `docs/ai/stages/06-eval-harness.md` | Dataset -> Case from Run -> Eval Run -> Metrics | passed |
| 07 | Memory / Context / Model Routing | completed | `docs/ai/stages/07-memory-context-router.md` | Task type -> Router -> Model choice -> Trace | passed |
| 08 | WarmPool + Benchmark | completed | `docs/ai/stages/08-warmpool-benchmark.md` | WarmPool reserve -> Benchmark -> Report | passed |
| 09 | Portfolio Demo + Docs | completed | `docs/ai/stages/09-portfolio-demo-docs.md` | GitHub Issue -> Agent -> Guardrail -> Replay -> Eval -> Benchmark | passed |

## 本轮完成记录

- 新增 `docs/00-product-spec.md` 到 `docs/10-portfolio-demo-spec.md`。
- 新增 `docs/ai/stages/` 九阶段执行规格。
- 删除旧 `docs/ai/02-stage...14-stage...` 执行历史。
- 新增 Eval Harness 后端垂直切片。
- 新增 Console `/evals` 页面。
- Runs 页面静态 KPI 改为后端 Observability 动态数据。
- Run Detail 新增指定事件序号 Replay，显示 state summary、diagnosis、failure point。
- Run Detail 新增 Eval 回归面板，支持创建 Dataset、保存当前 Run 为 Case、运行 Dataset Eval。
- Run Detail 新增 Guardrail 面板，聚合 policy/denied 事件和被拒绝工具调用。
- Guardrail 新增 Tool Approval 后端状态和 Run Detail 审批操作，支持 admin 批准或拒绝高风险工具调用。
- Tool Runtime 新增统一 Tool Registry API 和 Console `/tools` 页面，内置工具与 MCP-shaped 工具共用策略、审计和 trace。
- Memory / Context / Model Routing 新增 Run Context API，返回 working memory、long-term memory、artifact memory、RAG context、trace memory、context compression、model routing。
- Route Context API 写入 `CONTEXT_COMPRESSED` 和 `MODEL_ROUTED` 事件，Run Detail 新增 Context Router 动态面板。
- WarmPool Benchmark 新增报告 API，记录 warm avg、warm p95、cold baseline、hit rate、target status。
- Sandboxes 页面新增 Benchmark 执行动作和最新性能指标展示。
- OpenAPI JSON/YAML 已从 FastAPI app 重新导出并同步到 docs 与官网 public assets。
- 新增 Portfolio Demo Guide、Eval Report、Benchmark Report、SDK Example、AI Harness Engineer Capability Map。
- README 已更新当前状态、运行时接口和最终交付链接。

## 验证记录

```text
cd services/api-server && .venv/bin/python -m pytest tests/test_context_router.py -> 2 passed
cd services/api-server && .venv/bin/python -m ruff check app/agents/context_router.py app/api/tasks.py app/api/schemas.py tests/test_context_router.py -> passed
cd services/api-server && .venv/bin/python -m pytest tests/test_context_router.py tests/test_model_gateway.py tests/test_tasks.py -> 24 passed
cd services/api-server && .venv/bin/python -m pytest -> 118 passed
cd services/api-server && .venv/bin/python -m ruff check app tests -> passed
cd services/api-server && .venv/bin/python -m pytest tests/test_warm_pool.py tests/test_sandbox.py -> 11 passed
cd services/api-server && .venv/bin/python -m ruff check app/sandbox/benchmark.py app/api/sandboxes.py app/api/schemas.py app/db/models.py tests/test_warm_pool.py -> passed
OpenAPI export from FastAPI app -> passed
cd services/api-server && .venv/bin/python -m pytest tests/test_evals.py tests/test_agents.py tests/test_observability.py tests/test_event_store.py -> 38 passed
cd services/api-server && .venv/bin/python -m ruff check app tests/test_evals.py tests/test_agents.py tests/test_observability.py tests/test_event_store.py -> passed
cd apps/agent-console && npm run build -> passed
python3 scripts/validate-docs.py -> passed
docker compose -f deploy/docker-compose/docker-compose.yml config -> passed
git diff --check -> passed
```

## 阶段完成定义

```text
1. 本阶段 vertical slice 能运行。
2. 后端测试通过。
3. 前端 build 通过。
4. 文档验证通过。
5. task-progress.yaml 已更新。
6. 本看板已更新。
7. 验收记录写入本文件。
```
