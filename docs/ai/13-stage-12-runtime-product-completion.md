# 13 阶段 12：Runtime Product Completion

本阶段补齐原始运行时与控制台产品契约中尚未落地的接口、数据表、事件、工具治理和页面。阶段 12 必须在阶段 11 PR 合并后执行，固定目标是让后端 OpenAPI、数据库 schema、运行时事件、工具审计和控制台页面与最初产品文档一致。

## Required Context

```text
docs/ai/00-master-prompt.md
docs/ai/00-execution-protocol.md
docs/ai/task-progress.yaml
docs/human/05-frontend-product.md
docs/human/06-backend-runtime.md
docs/human/10-task-progress.md
docs/ai/reference/data-events-api.md
docs/ai/reference/database-schema.yaml
docs/ai/reference/database-erd-migrations.md
docs/ai/reference/frontend-spec.md
docs/ai/reference/runtime-agent-prompts.md
docs/ai/reference/tool-registry-spec.md
docs/ai/reference/tool-registry.yaml
docs/ai/reference/prompt-contracts.yaml
docs/ai/reference/security-policy-matrix.md
docs/api/openapi-contract.md
docs/api/openapi.yaml
apps/agent-console/src/app/routes.tsx
apps/agent-console/src/features/tasks/api.ts
services/api-server/app/main.py
services/api-server/app/api/tasks.py
services/api-server/app/api/events.py
services/api-server/app/api/schemas.py
services/api-server/app/db/models.py
services/api-server/app/events/event_store.py
services/api-server/app/events/event_types.py
services/api-server/app/tools/registry.py
services/api-server/app/sandbox/policies.py
```

## AI 执行提示词

```text
你是本项目的运行时产品补齐 Agent。现在执行阶段 12：Runtime Product Completion。

固定分支：stage/stage-12-runtime-product-completion
固定 base：develop
固定目标：补齐原始文档中定义但当前 OpenAPI、后端实现和控制台页面尚未覆盖的运行时产品能力。

开始前必须执行：
1. git status --short
2. git branch --show-current
3. git fetch origin
4. git checkout develop
5. git pull --ff-only origin develop
6. git checkout -b stage/stage-12-runtime-product-completion
7. 读取 docs/ai/task-progress.yaml
8. 读取 docs/human/10-task-progress.md
9. 将 stage-12-runtime-product-completion 状态标记为 in_progress

完成后必须执行：
1. cd services/api-server && .venv/bin/python -m pytest
2. cd services/api-server && .venv/bin/python -m ruff check app tests
3. cd services/api-server && DATABASE_URL=sqlite+pysqlite:////tmp/harness_stage12.db .venv/bin/alembic upgrade head
4. cd apps/agent-console && npm run lint
5. cd apps/agent-console && npm run build
6. docker compose -f deploy/docker-compose/docker-compose.yml config
7. python3 scripts/validate-docs.py
8. 更新 docs/api/openapi.yaml
9. 更新 docs/api/openapi.json
10. 更新 docs/ai/task-progress.yaml
11. 更新 docs/human/10-task-progress.md
12. git status --short
13. git add .
14. git commit -m "feat(stage-12): complete runtime product surface"
15. git push -u origin stage/stage-12-runtime-product-completion
16. gh pr create --base develop --head stage/stage-12-runtime-product-completion --title "feat(stage-12): complete runtime product surface" --body "Completes task lifecycle, replay, result, model/tool audit, settings, and console product pages."

禁止事项：
- 禁止删除既有 Event Store 事件。
- 禁止降低认证与租户隔离要求。
- 禁止把技术字段翻译成非原始值。
- 禁止跳过 OpenAPI 与前端 client 同步。
- 禁止绕过 Docker Sandbox 执行高风险工具。
```

## 缺口清单

### 当前后端已公开接口

```text
GET    /health
POST   /api/tasks
GET    /api/tasks
GET    /api/tasks/{task_id}
POST   /api/tasks/{task_id}/start
GET    /api/tasks/{task_id}/events
GET    /api/tasks/{task_id}/events/stream
GET    /api/tasks/{task_id}/subagents
GET    /api/subagents/{subagent_id}
POST   /api/subagents/{subagent_id}/cancel
GET    /api/sandboxes
GET    /api/sandboxes/warm-pool
GET    /api/sandboxes/{sandbox_id}
POST   /api/sandboxes/{sandbox_id}/terminate
```

### 原始后端文档缺失接口

```text
POST   /api/tasks/{task_id}/cancel
POST   /api/tasks/{task_id}/resume
GET    /api/tasks/{task_id}/result
POST   /api/tasks/{task_id}/replay
```

### 原始目录与数据缺失项

```text
services/api-server/app/api/settings.py
services/api-server/app/events/replay.py
services/api-server/app/tools/filesystem.py
services/api-server/app/tools/http.py
services/api-server/app/workers/sandbox_worker.py
model_calls table
tool_calls table
```

### 当前前端缺失页面与组件

```text
/settings/models 真实页面
/settings/policies 真实页面
ModelCallPanel
ResourceUsageChart
PolicyBadge
Task result API 驱动视图
Replay 定位与调试视图
完整 Observability 视图
中文默认与中英文切换
```

## 任务 1：Task Lifecycle API

### 目标

任务生命周期必须覆盖 start、cancel、resume、result。所有接口必须执行 Bearer Token 认证和组织隔离。

### 固定实现

1. `POST /api/tasks/{task_id}/cancel`
   - 支持状态：CREATED、PLANNING、RUNNING、WAITING_SUBAGENTS、FAILED。
   - 写入事件：TASK_CANCELLED。
   - 更新任务状态为 CANCELLED。
2. `POST /api/tasks/{task_id}/resume`
   - 支持状态：FAILED、CANCELLED。
   - 写入事件：TASK_RESUMED。
   - 恢复后进入 RUNNING 或 COMPLETED，由 Executor 结果决定。
3. `GET /api/tasks/{task_id}/result`
   - 返回任务状态、最终摘要、执行计划、产物列表、最后事件序号。
   - 未完成任务返回 pending result 结构。
4. OpenAPI 同步中文 summary、description、字段说明。
5. 前端 client 同步新增方法。

### 验收

- 未认证请求返回 401。
- 不同组织 token 读取返回 404。
- cancel 后事件流包含 TASK_CANCELLED。
- resume 后事件流包含 TASK_RESUMED。
- result 返回 task_id、status、summary、artifacts、last_sequence。

## 任务 2：Replay 与 Recovery API

### 目标

Event Store 必须支持任务状态重放、指定 sequence 定位和调试摘要。

### 固定实现

1. 创建 `services/api-server/app/events/replay.py`。
2. 实现从 `agent_events` 重放任务状态。
3. 支持读取 `task_snapshots` 作为加速入口。
4. `POST /api/tasks/{task_id}/replay` 返回：
   - `task_id`
   - `sequence`
   - `state_summary`
   - `failure_point`
   - `diagnosis`
   - `requires_manual_review`
5. Replay 不写入历史事件，除非执行 resume。
6. 前端 Event Timeline 支持 sequence 定位与 replay 摘要面板。

### 验收

- replay 指定 sequence 返回该点状态。
- replay 完成任务返回 completed 摘要。
- replay 失败任务返回 failure_point。
- Event Timeline 能显示 replay 结果。

## 任务 3：Model 与 Tool Audit

### 目标

模型调用和工具调用必须有数据库事实源、事件审计和控制台展示。

### 固定实现

1. 新增 `model_calls` 表。
2. 新增 `tool_calls` 表。
3. Model Gateway 写入：
   - MODEL_CALLED
   - MODEL_RESPONSE_RECEIVED
   - MODEL_CALL_FAILED
   - MODEL_FALLBACK_USED
4. Tool Registry 与工具执行写入：
   - POLICY_CHECKED
   - TOOL_CALLED
   - TOOL_RESULT_RECEIVED
   - TOOL_FAILED
   - TOOL_TIMEOUT
   - TOOL_DENIED_BY_POLICY
5. 所有高风险工具必须通过 Docker Sandbox。
6. 新增查询接口：
   - `GET /api/tasks/{task_id}/model-calls`
   - `GET /api/tasks/{task_id}/tool-calls`

### 验收

- start task 后存在 model_calls 或明确 mock 调用记录。
- shell 工具调用存在 tool_calls。
- 事件流包含 POLICY_CHECKED、TOOL_CALLED、TOOL_RESULT_RECEIVED。
- 控制台展示模型调用和工具调用列表。

## 任务 4：Tools Surface

### 目标

Tool Registry YAML 中的工具必须有后端实现入口和审计边界。

### 固定实现

1. 创建 `services/api-server/app/tools/filesystem.py`。
2. 创建 `services/api-server/app/tools/http.py`。
3. `read_file`、`list_files` 只读工作区。
4. `write_file`、`run_shell`、`run_tests`、`network_request`、`git_command` 高风险工具进入 Docker Sandbox。
5. 工具输入输出必须匹配 `docs/ai/reference/tool-registry.yaml`。
6. 策略拒绝写入 POLICY_DENIED 与 TOOL_DENIED_BY_POLICY。

### 验收

- Tool Registry YAML 中每个工具都有对应实现。
- 高风险工具单测验证 requires_sandbox。
- 策略拒绝单测覆盖。

## 任务 5：Settings API

### 目标

模型设置和策略设置必须有后端接口与控制台页面。

### 固定实现

1. 创建 `services/api-server/app/api/settings.py`。
2. 新增接口：
   - `GET /api/settings/models`
   - `PUT /api/settings/models`
   - `GET /api/settings/policies`
   - `PUT /api/settings/policies`
3. 设置变更写入 ADMIN_ACTION。
4. 设置接口要求 admin 角色。
5. 控制台 `/settings/models` 展示 Model Gateway 配置、供应商、限流、健康状态。
6. 控制台 `/settings/policies` 展示工具风险等级、审批策略、沙箱策略、审计要求。

### 验收

- engineer 修改设置返回 403。
- admin 修改设置返回 200。
- 设置变更事件包含 ADMIN_ACTION。
- 两个 settings 页面不再使用 PlaceholderPage。

## 任务 6：Console Product Pages

### 目标

控制台必须覆盖文档定义的核心组件和路由。

### 固定实现

1. `/tasks` 展示任务列表、状态筛选、模型筛选、创建入口、最近事件摘要。
2. `/tasks/new` 展示目标输入、约束输入、模型选择、工具策略、提交确认。
3. `/tasks/:taskId` 展示 ExecutionPlanPanel、EventTimeline、TaskResultPanel、SubagentPanel、SandboxPanel、ModelCallPanel、ResourceUsageChart。
4. `/tasks/:taskId/events` 支持 replay 定位。
5. `/settings/models` 使用真实 settings API。
6. `/settings/policies` 使用真实 settings API。
7. `/observability` 展示任务吞吐、失败率、模型调用、工具执行、资源指标。
8. 默认中文，顶栏提供中文/English 切换。
9. 技术字段保留原值并显示中文说明。

### 验收

- PlaceholderPage 不再用于 models、policies。
- ModelCallPanel、ResourceUsageChart、PolicyBadge 存在并接真实数据。
- 中文为默认语言。
- English 切换覆盖同一组页面文案。
- 技术字段旁边有中文说明。

## 必须修改的文件

```text
docs/api/openapi.yaml
docs/api/openapi.json
docs/api/openapi-contract.md
docs/ai/reference/database-schema.yaml
docs/ai/reference/data-events-api.md
docs/ai/reference/frontend-spec.md
docs/design/figma-production-brief.md
docs/design/page-inventory.md
services/api-server/app/main.py
services/api-server/app/api/tasks.py
services/api-server/app/api/events.py
services/api-server/app/api/settings.py
services/api-server/app/api/schemas.py
services/api-server/app/db/models.py
services/api-server/app/events/replay.py
services/api-server/app/events/event_store.py
services/api-server/app/tools/filesystem.py
services/api-server/app/tools/http.py
services/api-server/app/tools/registry.py
services/api-server/app/sandbox/policies.py
services/api-server/app/workers/sandbox_worker.py
services/api-server/alembic/versions/<stage_12_revision>.py
services/api-server/tests/test_task_lifecycle.py
services/api-server/tests/test_replay.py
services/api-server/tests/test_model_tool_audit.py
services/api-server/tests/test_settings.py
services/api-server/tests/test_tools.py
apps/agent-console/src/app/routes.tsx
apps/agent-console/src/app/ConsoleShell.tsx
apps/agent-console/src/features/tasks/api.ts
apps/agent-console/src/features/tasks/pages/TaskListPage.tsx
apps/agent-console/src/features/tasks/pages/TaskCreatePage.tsx
apps/agent-console/src/features/tasks/pages/TaskDetailPage.tsx
apps/agent-console/src/features/events/components/EventTimeline.tsx
apps/agent-console/src/features/settings/pages/ModelSettingsPage.tsx
apps/agent-console/src/features/settings/pages/PolicySettingsPage.tsx
apps/agent-console/src/features/observability/pages/ObservabilityPage.tsx
apps/agent-console/src/features/tasks/components/ModelCallPanel.tsx
apps/agent-console/src/features/tasks/components/ResourceUsageChart.tsx
apps/agent-console/src/features/policies/components/PolicyBadge.tsx
docs/ai/task-progress.yaml
docs/human/10-task-progress.md
```

## Verification Commands

```bash
cd services/api-server && .venv/bin/python -m pytest
cd services/api-server && .venv/bin/python -m ruff check app tests
cd services/api-server && DATABASE_URL=sqlite+pysqlite:////tmp/harness_stage12.db .venv/bin/alembic upgrade head
cd apps/agent-console && npm run lint
cd apps/agent-console && npm run build
docker compose -f deploy/docker-compose/docker-compose.yml config
python3 scripts/validate-docs.py
```

## API E2E Verification

```text
POST /api/tasks/{task_id}/cancel returns TASK_CANCELLED
POST /api/tasks/{task_id}/resume returns TASK_RESUMED
GET /api/tasks/{task_id}/result returns artifact result shape
POST /api/tasks/{task_id}/replay returns replay diagnosis
GET /api/tasks/{task_id}/model-calls returns model call page
GET /api/tasks/{task_id}/tool-calls returns tool call page
GET /api/settings/models returns model settings
PUT /api/settings/models requires admin
GET /api/settings/policies returns policy settings
PUT /api/settings/policies requires admin
```

## Console E2E Verification

```text
/tasks renders Chinese task table
/tasks/new renders Chinese create form
/tasks/:taskId renders model calls, resource chart, result panel
/tasks/:taskId/events renders replay controls
/settings/models renders real settings page
/settings/policies renders real settings page
/observability renders task, model, tool, resource metrics
Language switch changes visible copy between 中文 and English
Technical values keep original value with Chinese description
```

## Git 与 PR

```bash
git status --short
git add .
git commit -m "feat(stage-12): complete runtime product surface"
git push -u origin stage/stage-12-runtime-product-completion
gh pr create --base develop --head stage/stage-12-runtime-product-completion --title "feat(stage-12): complete runtime product surface" --body "Completes task lifecycle, replay, result, model/tool audit, settings, tools, and console product pages."
```

## 完成标准

阶段 12 进入 `ready_for_review` 必须满足：

```text
OpenAPI 覆盖阶段 12 所有接口
数据库 migration 覆盖 model_calls 与 tool_calls
Task lifecycle、Replay、Settings、Model/Tool audit 测试通过
控制台 models、policies、replay、result、observability 页面接真实数据
默认中文与中英文切换通过浏览器验收
Verification Commands 全部通过
阶段分支已 push
PR 已创建
```

阶段 12 进入 `completed` 必须满足：

```text
用户已合并 PR
develop 包含阶段 12 变更
task-progress.yaml 已写入 merged_at
docs/human/10-task-progress.md 显示阶段 12 completed
```

## Progress Update Rule

阶段 12 执行期间固定更新：

```text
开始实现前：docs/ai/task-progress.yaml status=in_progress
开始实现前：docs/human/10-task-progress.md 当前状态=in_progress
验证通过后：docs/ai/task-progress.yaml verification_result=passed
验证通过后：docs/human/10-task-progress.md 验证结果=passed
提交后：docs/ai/task-progress.yaml commit_sha 写入实现提交
创建 PR 后：docs/ai/task-progress.yaml pr_url 写入 PR 地址
创建 PR 后：docs/human/10-task-progress.md status=ready_for_review
```
