# 04 阶段 03：仓库脚手架

## 阶段目标

建立固定 Monorepo 目录、环境样例、基础脚本和项目入口。此阶段只创建结构，不实现业务逻辑。

## Required Context

- [执行协议](./00-execution-protocol.md)
- [任务进度说明](./01-task-progress.md)
- [机器可读任务进度](./task-progress.yaml)
- [架构与技术决策](./reference/architecture-and-decisions.md)

## AI 执行提示词

```text
你是本项目的工程执行 Agent。现在执行阶段 03：仓库脚手架。

必须先读取 docs/ai/00-execution-protocol.md、docs/ai/01-task-progress.md、docs/ai/task-progress.yaml 和 docs/ai/reference/architecture-and-decisions.md。
只执行阶段 03，不进入阶段 04。
阶段开始前必须创建阶段分支，验证通过后 commit、push 并创建 PR。

执行内容：
1. 创建固定目录 apps/web-site、apps/agent-console、services/api-server、services/sandbox-worker、deploy/docker-compose、deploy/systemd、deploy/nginx、deploy/monitoring、scripts。
2. 创建根目录 .env.example。
3. 创建 scripts/check-docs.sh、scripts/check-env.sh。
4. 创建 services/api-server/.env.example。
5. 创建 apps/web-site/.env.example。
6. 创建 apps/agent-console/.env.example。
7. 创建 deploy/docker-compose/.env.example。
8. 更新 README.md 的项目结构部分，确保目录与实际一致。
9. 执行验证命令。
10. 更新 docs/ai/task-progress.yaml，把 stage-03-repository-scaffold 标记为 completed。

PR 与进度要求：
- 阶段分支必须推送到 origin。
- 阶段变更必须创建 Pull Request。
- branch、commit_sha、pr_url 写入 docs/ai/task-progress.yaml。
- 人读进度 docs/human/10-task-progress.md 必须同步更新。

验收标准：
- 固定目录全部存在。
- 所有 .env.example 存在。
- scripts/check-docs.sh 可执行。
- scripts/check-env.sh 可执行。
- task-progress.yaml 已更新。
```

## Required Files

```text
.env.example
apps/web-site/.env.example
apps/agent-console/.env.example
services/api-server/.env.example
deploy/docker-compose/.env.example
scripts/check-docs.sh
scripts/check-env.sh
```

## Environment Variables

根目录 `.env.example` 必须包含：

```text
APP_ENV=development
APP_BASE_URL=http://localhost:3000
CONSOLE_BASE_URL=http://localhost:5173
API_BASE_URL=http://localhost:8000
DATABASE_URL=postgresql+psycopg://agent:agent@localhost:5432/agent_harness
REDIS_URL=redis://localhost:6379/0
MODEL_GATEWAY_BASE_URL=http://localhost:8000/mock-model
MODEL_GATEWAY_API_KEY=replace-me
DOCKER_HOST=unix:///var/run/docker.sock
```

## Verification Commands

```bash
test -d apps/web-site
test -d apps/agent-console
test -d services/api-server
test -d services/sandbox-worker
test -d deploy/docker-compose
test -d deploy/systemd
test -d deploy/nginx
test -d deploy/monitoring
test -d scripts
test -f .env.example
test -f services/api-server/.env.example
test -f apps/web-site/.env.example
test -f apps/agent-console/.env.example
test -f deploy/docker-compose/.env.example
test -x scripts/check-docs.sh
test -x scripts/check-env.sh
```

## Progress Update Rule

```yaml
stage-03-repository-scaffold:
  status: completed
  verification_result: passed
  next_stage: stage-04-backend-foundation
```

