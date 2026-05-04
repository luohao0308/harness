# 12 阶段 11：Review P1 Production Hardening

本阶段修复代码审查确认的 P1 生产级阻断问题。阶段 11 是阶段 10 之后的正式修复阶段，所有变更必须在 `stage/stage-11-review-p1-hardening` 分支完成，验证通过后提交、推送并创建 PR，由用户合并到 `develop`。

## Required Context

```text
docs/ai/00-master-prompt.md
docs/ai/00-execution-protocol.md
docs/ai/task-progress.yaml
docs/human/10-task-progress.md
docs/ai/11-stage-10-observability-deployment.md
docs/ai/reference/architecture-and-decisions.md
docs/ai/reference/data-events-api.md
docs/ai/reference/runtime-deployment-spec.md
docs/api/openapi.yaml
deploy/docker-compose/docker-compose.yml
deploy/nginx/agent-harness.conf
services/api-server/app/main.py
services/api-server/app/api/tasks.py
services/api-server/app/api/events.py
services/api-server/app/api/subagents.py
services/api-server/app/api/sandboxes.py
services/api-server/app/events/event_store.py
services/api-server/app/sandbox/warm_pool.py
apps/agent-console/src/features/tasks/api.ts
apps/agent-console/src/features/events/useTaskEventStream.ts
```

## AI 执行提示词

```text
你是本项目的生产级修复 Agent。现在执行阶段 11：Review P1 Production Hardening。

固定分支：stage/stage-11-review-p1-hardening
固定 base：develop
固定目标：关闭 P1 Review findings，确保认证、迁移、事件并发、SSE、WarmPool 进入可联调状态。

开始前必须执行：
1. git status --short
2. git branch --show-current
3. git pull --ff-only origin develop
4. git switch -c stage/stage-11-review-p1-hardening
5. 读取 docs/ai/task-progress.yaml
6. 读取 docs/human/10-task-progress.md
7. 将 stage-11-review-p1-hardening 状态标记为 in_progress

完成后必须执行：
1. cd services/api-server && .venv/bin/python -m pytest
2. cd services/api-server && .venv/bin/python -m ruff check app tests
3. cd services/api-server && DATABASE_URL=sqlite+pysqlite:////tmp/harness_stage11.db .venv/bin/alembic upgrade head
4. cd apps/agent-console && npm run lint
5. cd apps/agent-console && npm run build
6. docker compose -f deploy/docker-compose/docker-compose.yml config
7. python3 scripts/validate-docs.py
8. 更新 docs/ai/task-progress.yaml
9. 更新 docs/human/10-task-progress.md
10. git status --short
11. git add .
12. git commit -m "fix(stage-11-review-p1-hardening): close production review findings"
13. git push -u origin stage/stage-11-review-p1-hardening
14. gh pr create --base develop --head stage/stage-11-review-p1-hardening --title "fix(stage-11): close P1 production review findings" --body "Closes P1 review findings for auth, migrations, event store concurrency, SSE, and WarmPool sharing."

禁止事项：
- 禁止跳过验证命令。
- 禁止在 develop 上直接提交修复。
- 禁止将未完成的 P1 标记为 completed。
- 禁止删除既有阶段 01-10 的历史记录。
- 禁止把 P2/P3 重构混入本阶段，除非该改动是关闭 P1 的必要前置。
```

## 修复范围

本阶段固定关闭 5 个 P1：

1. API 未执行认证与租户隔离。
2. Docker 部署不执行数据库迁移。
3. EventStore 并发写 `sequence` 会冲突。
4. SSE 前后端协议不匹配。
5. WarmPool 不是可共享的生产池。

## 任务 1：API 认证与租户隔离

### 目标

所有 `/api/**` 路由必须执行 Bearer Token 认证。任务、事件、Subagent、Sandbox 访问必须绑定 `organization_id`。

### 固定实现

1. 创建 `services/api-server/app/security/auth.py`。
2. 定义 `AuthenticatedPrincipal`：
   - `user_id: str`
   - `organization_id: str`
   - `roles: list[str]`
3. 使用 FastAPI `HTTPBearer` 读取 `Authorization: Bearer <token>`。
4. 开发与测试环境固定支持以下测试 token：
   - `dev-admin-token`
   - `dev-engineer-token`
5. `dev-admin-token` 解析为：
   - `user_id=dev-admin`
   - `organization_id=dev-org`
   - `roles=["admin", "engineer"]`
6. `dev-engineer-token` 解析为：
   - `user_id=dev-engineer`
   - `organization_id=dev-org`
   - `roles=["engineer"]`
7. 缺少 token 返回 `401`。
8. token 无效返回 `401`。
9. 角色不足返回 `403`。
10. `create_task` 写入 `organization_id` 和 `created_by`。
11. `list_tasks` 只返回当前 `organization_id` 的任务。
12. `get_task`、`start_task`、`list_task_events`、`stream_task_events` 必须校验任务属于当前 `organization_id`。
13. `list_task_subagents` 先校验 task 归属。
14. `get_subagent`、`cancel_subagent` 通过关联 task 校验组织归属。
15. `list_sandboxes` 只返回当前组织任务下的 sandbox。
16. `get_sandbox`、`terminate_sandbox` 通过关联 task 校验组织归属。
17. 更新 OpenAPI，保留 bearerAuth，与实现一致。
18. 更新前端 API client，默认读取 `VITE_DEV_BEARER_TOKEN` 并写入 Authorization header。

### 验收

- 未带 token 调用 `/api/tasks` 返回 `401`。
- 带 `dev-engineer-token` 创建 task 后，数据库 task 行包含 `organization_id=dev-org`。
- 不同组织 token 不能读取该任务。
- 现有测试全部通过。

## 任务 2：Docker Compose 数据库迁移

### 目标

全新 Docker Compose 环境必须先执行 Alembic migration，再启动 API 与 worker。

### 固定实现

1. 在 `deploy/docker-compose/docker-compose.yml` 新增 `db-migrate` service。
2. `db-migrate` 使用 `agent-harness-api-server:latest` 镜像。
3. `db-migrate` command 固定为：

```text
python -m alembic upgrade head
```

4. `db-migrate` depends_on `postgres`。
5. `api-server` depends_on `db-migrate`，条件为 `service_completed_successfully`。
6. `agent-worker` depends_on `db-migrate`，条件为 `service_completed_successfully`。
7. `sandbox-worker` depends_on `db-migrate`，条件为 `service_completed_successfully`。
8. systemd 部署文档保留独立 `alembic upgrade head` 步骤。

### 验收

- `docker compose -f deploy/docker-compose/docker-compose.yml config` 通过。
- compose config 输出包含 `db-migrate`。
- API 和 worker 不直接在表缺失状态启动。

## 任务 3：EventStore 并发 sequence

### 目标

同一 task 的事件序号必须在多 worker 并发写入时保持唯一、递增、无冲突。

### 固定实现

1. `EventStore.append` 在计算 sequence 前锁定 task 行。
2. PostgreSQL 使用 `SELECT ... FOR UPDATE` 锁定 `tasks.id`。
3. SQLite 测试环境使用同一逻辑并保持测试通过。
4. 同一事务内完成：
   - 锁定 task
   - 查询 max sequence
   - insert agent_events
5. 不引入删除或更新 agent_events 的逻辑。
6. 新增并发测试：
   - 创建同一 task。
   - 并发写入至少 10 个事件。
   - 最终 sequence 为 `1..10` 或在已有创建事件后连续递增。
   - 无 `IntegrityError`。

### 验收

- 并发测试通过。
- `agent_events_task_sequence_uidx` 保留。
- Event Store append-only 规则保留。

## 任务 4：SSE 前后端协议

### 目标

事件流必须成为真实长连接。前端必须能消费后端发送的事件，不依赖一次性 snapshot。

### 固定后端实现

1. `stream_task_events` 支持 `after_sequence` query。
2. `stream_task_events` 支持 `Last-Event-ID` header。
3. 优先级固定为：
   - `after_sequence`
   - `Last-Event-ID`
   - `None`
4. SSE 使用长连接循环。
5. 每轮读取新事件。
6. 无新事件时发送 heartbeat comment：

```text
: heartbeat

```

7. 事件固定发送为默认 message 事件，不使用自定义 `event:` 字段。
8. 每条 data 是完整 `AgentEvent` JSON。
9. 客户端断开时停止循环。

### 固定前端实现

1. `useTaskEventStream` 使用 `EventSource.onmessage` 消费所有事件。
2. 解析失败时不中断页面。
3. 按 sequence 去重。
4. 进入任务详情页时先加载 REST snapshot，再接 SSE。
5. 断线时 UI 显示 `snapshot`。

### 验收

- 创建 task 后打开详情页能看到 TASK_CREATED。
- 点击 start 后事件时间线持续出现 PLAN_REQUESTED、PLAN_GENERATED、STEP_STARTED、STEP_COMPLETED、TASK_COMPLETED。
- 后端 SSE 测试覆盖 snapshot、after_sequence、Last-Event-ID、heartbeat。

## 任务 5：WarmPool 共享化

### 目标

WarmPool 预热容器必须能被 API/worker 进程共享。进程内 list/dict 不能作为生产事实源。

### 固定实现

1. 新增数据库表 `warm_pool_containers`。
2. 字段固定：
   - `id`
   - `container_id`
   - `image`
   - `status`
   - `locked_by`
   - `task_id`
   - `sandbox_id`
   - `idle_since`
   - `created_at`
   - `updated_at`
3. 状态固定：
   - `IDLE`
   - `BUSY`
   - `FAILED`
   - `DESTROYED`
4. Alembic 新增 migration。
5. `WarmPoolManager.prewarm()` 写入 `warm_pool_containers`。
6. `WarmPoolManager.acquire()` 通过数据库事务领取 `IDLE` 容器。
7. PostgreSQL 使用行锁防止多个 worker 领取同一容器。
8. `WarmPoolManager.release()` 将容器归还为 `IDLE`。
9. `WarmPoolManager.status()` 从数据库统计 idle、busy、failed。
10. 新增 `services/api-server/app/workers/warm_pool_service.py`。
11. Docker Compose 新增 `warm-pool` service。
12. systemd `agent-warm-pool.service` 启动 `app.workers.warm_pool_service`。
13. WarmPool 命中继续写入 `SANDBOX_REUSED_FROM_WARM_POOL`。

### 验收

- WarmPool API 显示数据库中的 idle/busy/failed。
- API 进程重启后 WarmPool 状态不丢失。
- 两个并发 acquire 不会拿到同一个 container_id。
- Docker Compose config 包含 `warm-pool` service。

## 必须修改的文件

```text
services/api-server/app/main.py
services/api-server/app/security/__init__.py
services/api-server/app/security/auth.py
services/api-server/app/api/tasks.py
services/api-server/app/api/events.py
services/api-server/app/api/subagents.py
services/api-server/app/api/sandboxes.py
services/api-server/app/api/schemas.py
services/api-server/app/db/models.py
services/api-server/app/events/event_store.py
services/api-server/app/sandbox/warm_pool.py
services/api-server/app/workers/warm_pool_service.py
services/api-server/alembic/versions/<new_stage_11_revision>.py
services/api-server/tests/test_auth.py
services/api-server/tests/test_event_store.py
services/api-server/tests/test_events_stream.py
services/api-server/tests/test_warm_pool.py
apps/agent-console/src/features/tasks/api.ts
apps/agent-console/src/features/events/useTaskEventStream.ts
deploy/docker-compose/docker-compose.yml
deploy/systemd/agent-warm-pool.service
docs/api/openapi.yaml
docs/ai/task-progress.yaml
docs/human/10-task-progress.md
```

## Verification Commands

```bash
cd services/api-server && .venv/bin/python -m pytest
cd services/api-server && .venv/bin/python -m ruff check app tests
cd services/api-server && DATABASE_URL=sqlite+pysqlite:////tmp/harness_stage11.db .venv/bin/alembic upgrade head
cd apps/agent-console && npm run lint
cd apps/agent-console && npm run build
docker compose -f deploy/docker-compose/docker-compose.yml config
python3 scripts/validate-docs.py
```

## Docker E2E Verification

```bash
docker compose -f deploy/docker-compose/docker-compose.yml up -d --build
docker compose -f deploy/docker-compose/docker-compose.yml ps
curl --noproxy '*' --fail http://127.0.0.1:8000/health
curl --noproxy '*' --fail http://127.0.0.1:8000/metrics
curl --noproxy '*' --fail http://127.0.0.1:8080/health
curl --noproxy '*' --fail http://127.0.0.1:9091/-/healthy
curl --noproxy '*' --fail http://127.0.0.1:3000/api/health
curl --noproxy '*' --fail http://127.0.0.1:5173/
```

API E2E 固定覆盖：

```text
未认证请求返回 401
无效 token 请求返回 401
dev-engineer-token 创建 task
dev-other-org-token 读取该 task 返回 404
start task 返回 COMPLETED
events 列表包含 TASK_CREATED、PLAN_REQUESTED、PLAN_GENERATED、TASK_COMPLETED
API SSE 返回 data 行
Nginx SSE 返回 data 行
WarmPool idle 大于等于 1
Prometheus targets 返回 success
Grafana api health 返回 database ok
```

## Git 与 PR

```bash
git status --short
git add .
git commit -m "fix(stage-11-review-p1-hardening): close production review findings"
git push -u origin stage/stage-11-review-p1-hardening
gh pr create --base develop --head stage/stage-11-review-p1-hardening --title "fix(stage-11): close P1 production review findings" --body "Closes P1 review findings for auth, migrations, event store concurrency, SSE, and WarmPool sharing."
```

## 完成标准

阶段 11 进入 `ready_for_review` 必须满足：

```text
5 个 P1 全部关闭
Verification Commands 全部通过
docs/ai/task-progress.yaml 已记录 changed_files、verification_commands、verification_result、branch、commit_sha、pr_url
docs/human/10-task-progress.md 已同步显示阶段 11 ready_for_review
阶段分支已 push
PR 已创建
```

阶段 11 进入 `completed` 必须满足：

```text
用户已合并 PR
develop 包含阶段 11 修复
task-progress.yaml 已写入 merged_at
docs/human/10-task-progress.md 显示阶段 11 completed
```

## Progress Update Rule

阶段 11 执行期间固定更新：

```text
开始修复前：docs/ai/task-progress.yaml status=in_progress
开始修复前：docs/human/10-task-progress.md 当前状态=in_progress
验证通过后：docs/ai/task-progress.yaml verification_result=passed
验证通过后：docs/human/10-task-progress.md 验证结果=passed
提交后：docs/ai/task-progress.yaml commit_sha 写入实现提交
创建 PR 后：docs/ai/task-progress.yaml pr_url 写入 PR 地址
创建 PR 后：docs/human/10-task-progress.md status=ready_for_review
用户合并后：docs/ai/task-progress.yaml status=completed merged_at 写入合并时间
用户合并后：docs/human/10-task-progress.md status=completed
```
