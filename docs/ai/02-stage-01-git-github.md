# 02 阶段 01：GitHub 与 Git 初始化

## 阶段目标

建立 Git 仓库基础、GitHub 协作规范、PR/Issue 模板、提交规则和分支流程。此阶段必须在 Figma 和代码脚手架之前完成。

## Required Context

- [执行协议](./00-execution-protocol.md)
- [任务进度说明](./01-task-progress.md)
- [机器可读任务进度](./task-progress.yaml)

## AI 执行提示词

```text
你是本项目的工程执行 Agent。现在执行阶段 01：GitHub 与 Git 初始化。

必须先读取 docs/ai/00-execution-protocol.md 和 docs/ai/01-task-progress.md、docs/ai/task-progress.yaml。
只执行阶段 01，不进入阶段 02。

执行内容：
1. 检查当前目录是否是 Git 仓库。
2. 未初始化时执行 git init，并把默认分支设置为 main。
3. 创建或更新 .gitignore，覆盖 Python、Node、Docker、本地环境、密钥、日志和构建产物。
4. 创建 .github/pull_request_template.md。
5. 创建 .github/ISSUE_TEMPLATE/feature.yml、bug.yml、docs.yml。
6. 创建 .github/workflows/docs.yml、frontend.yml、backend.yml、docker.yml 的占位工作流。
7. 在 README.md 中确认 AI 文档入口、GitHub 工作流入口存在。
8. 执行 git status --short。
9. 不提交真实代码，除非用户明确要求 commit。
10. 更新 docs/ai/task-progress.yaml，把 stage-01-git-github 标记为 completed，写入变更文件、验证命令和验证结果。

验收标准：
- git status 能正常运行。
- .gitignore 存在。
- PR 模板存在。
- 三个 Issue 模板存在。
- 四个 GitHub Actions 工作流存在。
- task-progress.yaml 已更新。
```

## Implementation Steps

```bash
git status --short
git init
git branch -M main
```

创建目录：

```text
.github/
.github/ISSUE_TEMPLATE/
.github/workflows/
```

必须存在文件：

```text
.gitignore
.github/pull_request_template.md
.github/ISSUE_TEMPLATE/feature.yml
.github/ISSUE_TEMPLATE/bug.yml
.github/ISSUE_TEMPLATE/docs.yml
.github/workflows/docs.yml
.github/workflows/frontend.yml
.github/workflows/backend.yml
.github/workflows/docker.yml
```

## GitHub Actions 内容要求

`docs.yml`：

```text
checkout
检查 docs/ai/README.md 存在
检查 docs/ai/01-task-progress.md、docs/ai/task-progress.yaml 存在
检查文档中没有松动表达
检查文档中使用阶段术语
```

`frontend.yml`：

```text
checkout
setup-node
apps/web-site 存在时运行 npm ci、npm run lint、npm run build
apps/agent-console 存在时运行 npm ci、npm run lint、npm run build
```

`backend.yml`：

```text
checkout
setup-python
启动 PostgreSQL service
启动 Redis service
安装 services/api-server 依赖
运行 Alembic migration
运行 pytest
```

`docker.yml`：

```text
checkout
setup docker buildx
验证 deploy/docker-compose/docker-compose.yml
构建 api-server 镜像
构建 worker 镜像
```

## Verification Commands

```bash
git status --short
test -f .gitignore
test -f .github/pull_request_template.md
test -f .github/ISSUE_TEMPLATE/feature.yml
test -f .github/ISSUE_TEMPLATE/bug.yml
test -f .github/ISSUE_TEMPLATE/docs.yml
test -f .github/workflows/docs.yml
test -f .github/workflows/frontend.yml
test -f .github/workflows/backend.yml
test -f .github/workflows/docker.yml
```

## Progress Update Rule

完成后更新 [机器可读任务进度](./task-progress.yaml)：

```yaml
stage-01-git-github:
  status: completed
  verification_result: passed
  next_stage: stage-02-figma-design
```

