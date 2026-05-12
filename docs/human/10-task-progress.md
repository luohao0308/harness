# 10 任务进度看板

本文件是人读进度看板。机器事实源是 [task-progress.yaml](../ai/task-progress.yaml)。

## 当前状态

```text
当前产品：AI Harness Platform
核心公式：Model + Harness = Agent
当前阶段：06-warmpool-infra
当前状态：completed
执行模式：Spec-first development + stage-gated implementation + vertical slice demo
官网策略：保留为 public shell，不作为控制台核心
关键模块：Agent Studio / Agent Workspace / Harness Management / Observability / Eval Harness / Infra
```

## 阶段进度

| 阶段 | 名称 | 状态 | 文档 | Demo 闭环 | 验证结果 |
|---|---|---|---|---|---|
| 01 | Agent Workspace 控制台 | completed | `docs/ai/stages/01-agent-workspace-console.md` | Agent Workspace -> Agent Run -> Plan DAG -> Event Stream -> Tool/Model Calls | passed |
| 02 | Agent Studio 配置闭环 | completed | `docs/ai/stages/02-agent-studio-config.md` | Studio -> Model settings -> DeepSeek presets -> Workspace config | passed |
| 03 | Harness 管理与 Tool/MCP | completed | `docs/ai/stages/03-harness-tool-mcp.md` | Tool Registry -> Policy -> Sandbox -> Trace | passed |
| 04 | Event Sourcing + Replay UI | completed | `docs/ai/stages/04-event-sourcing-replay-ui.md` | Run -> Events -> Replay sequence -> State reconstruction | passed |
| 05 | Eval + Regression | completed | `docs/ai/stages/05-eval-regression.md` | Run -> Eval Case -> Dataset Eval -> Metrics | passed |
| 06 | WarmPool + Infra 展示 | completed | `docs/ai/stages/06-warmpool-infra.md` | WarmPool -> Benchmark -> Sandbox lifecycle -> Infra status | passed |

## 本轮完成记录

- 核心 Spec 收敛为 Agent Studio、Agent Workspace、Harness 管理、Observability、Eval & Testing、Infra。
- 删除旧九阶段执行路径，建立新六阶段执行规格。
- 产品语义从 Task 主流程改为 Agent Run 主流程。
- `/tasks/new` 从控制台路由移除，`/tasks` 仅作为 `/runs` 兼容跳转。
- 新增 Agent Run 创建和 Workspace 聚合 API。
- 新建 `/runs` 和 `/runs/:runId` 页面。
- 重写 `/agents/:agentId/workspace` 为 Agent Workspace Pro 控制台。
- DeepSeek 作为默认模型配置路径保留并通过测试。
- Executor 接入 WarmPool-backed sandbox acquire/release。
- Agent Studio 增加 Model、Tools/MCP、Prompt、RAG、Templates、Orchestration 六个能力入口。
- DeepSeek 默认上下文窗口元数据统一为 1000000 tokens。
- DeepSeek 内置预置增加规范化，旧数据库中的历史内置供应商设置会按 DeepSeek 默认值读出。
- `/tools` 增加 Registry、Policy、Sandbox、MCP、Trigger 禁用态五个 Harness 管理区块。
- Tool/MCP/approval/agent 编排相关测试通过。
- Run Detail 增加指定 sequence Replay 输入，展示 state summary、diagnosis 和 failure point。
- Observability 修复 Run 事件与 Subagent 深链，指向具体 Run。
- Eval 页面增加 Regression Gate、Trace Grader、A/B 禁用态和人工复核禁用态。
- WarmPool 默认容量调整为 min_ready=2、max_ready=5。
- Sandboxes 页面增加 Tenant Isolation、WarmPool、API Gateway 禁用态和 Version Rollout 禁用态。
- OpenAPI JSON/YAML 已重新导出到 docs 和官网 public assets。
- 旧 `/api/tasks/*` OpenAPI 文案已降级为 deprecated Agent Run 兼容层。
- 最终全量回归通过。
- 本轮还关闭了 Workspace Pro gap register 里的产品缺口：`tool_call_result`、Continue 语义、Artifact 抽取、成本不可用态、分支 sibling 导航都已实现并验证。
- 前端测试基础设施继续显式延期，没有伪造 `test` 脚本。

## 验证记录

```text
services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_agents.py services/api-server/tests/test_tool_approvals.py -> 22 passed
services/api-server/.venv/bin/python -m ruff check services/api-server/app services/api-server/tests -> passed
cd apps/agent-console && npm run build -> passed
python3 scripts/validate-docs.py -> passed
services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_agents.py services/api-server/tests/test_settings.py services/api-server/tests/test_model_gateway.py -> 29 passed
cd apps/agent-console && npm run build -> passed
services/api-server/.venv/bin/python -m pytest services/api-server/tests -> 122 passed
services/api-server/.venv/bin/python -m ruff check services/api-server/app services/api-server/tests -> passed
python3 scripts/validate-docs.py -> passed
python3 scripts/smoke-test-docker.py -> passed
services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_settings.py services/api-server/tests/test_model_gateway.py -> 15 passed
services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_tool_registry.py services/api-server/tests/test_tool_runner.py services/api-server/tests/test_tool_approvals.py services/api-server/tests/test_agents.py -> 24 passed
services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_event_store.py services/api-server/tests/test_events_stream.py services/api-server/tests/test_observability.py -> 28 passed
services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_evals.py -> 2 passed
services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_warm_pool.py services/api-server/tests/test_sandbox.py -> 11 passed
services/api-server/.venv/bin/python -m pytest services/api-server/tests -> 122 passed
services/api-server/.venv/bin/python -m ruff check services/api-server/app services/api-server/tests -> passed
cd apps/agent-console && npm run build -> passed
python3 scripts/validate-docs.py -> passed
python3 scripts/smoke-test-docker.py -> passed
git diff --check -> passed
Docker runtime verification -> DeepSeek healthy/probe and context 1000000
```

## 未完成项

- 本轮 AI Harness Platform 六阶段聚焦重构的 vertical slice 已完成。
- Workspace Pro 产品缺口已在本轮闭环。
- 前端 component/e2e 测试基础设施保持显式延期。

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
