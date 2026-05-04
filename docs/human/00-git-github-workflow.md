# 00 GitHub 与 Git 工作流

本文件定义代码仓库、分支、提交、PR、Review、Release 和 GitHub Actions 的固定流程。

## 1. 仓库初始化

本项目使用单仓库管理文档、前端、后端、部署和脚本。

初始化命令：

```bash
cd /Users/luohao/Desktop/agent_workspace/harness
git init
git branch -M main
git add README.md docs
git commit -m "docs: add agent harness platform specification"
```

创建远程仓库后绑定 remote：

```bash
git remote add origin git@github.com:<org>/agent-harness.git
git push -u origin main
```

远程地址使用 SSH。组织名和仓库名固定为：

```text
<org>/agent-harness
```

## 2. .gitignore

根目录必须包含 `.gitignore`，覆盖 Python、Node、Docker、本地环境和密钥文件。

内容范围：

```text
.venv/
__pycache__/
.pytest_cache/
.mypy_cache/
node_modules/
dist/
build/
.next/
.env
.env.*
!.env.example
coverage/
.DS_Store
*.log
```

`.env.example` 必须提交。真实 `.env` 禁止提交。

## 3. 分支模型

固定分支：

```text
main：稳定分支，可部署
develop：集成分支
feat/*：功能分支
fix/*：缺陷修复
docs/*：文档修改
chore/*：工程配置
release/*：发布准备
```

创建功能分支：

```bash
git fetch origin
git checkout develop
git pull --ff-only origin develop
git checkout -b feat/task-event-store
```

## 4. 提交规范

提交信息使用 Conventional Commits。

格式：

```text
<type>(<scope>): <summary>
```

类型：

```text
feat：新功能
fix：修复
docs：文档
refactor：重构
test：测试
chore：工程配置
ci：CI/CD
build：构建系统
perf：性能优化
```

示例：

```bash
git commit -m "feat(events): add append-only event store"
git commit -m "docs(architecture): split human and ai documents"
git commit -m "ci(api): add backend test workflow"
```

## 5. 日常开发流程

每次开发前：

```bash
git status --short
git fetch origin
git checkout develop
git pull --ff-only origin develop
git checkout -b feat/<short-name>
```

开发中：

```bash
git status --short
git diff
git add <changed-files>
git commit -m "feat(scope): summary"
```

推送：

```bash
git push -u origin feat/<short-name>
```

## 6. Pull Request 流程

PR 目标分支：

```text
feature/fix/docs/chore -> develop
release/* -> main
hotfix/* -> main
```

PR 标题格式：

```text
feat(events): add event store
```

PR 描述必须包含：

```text
## Summary
## Changes
## Tests
## Risk
## Screenshots
## Rollback
```

创建 PR：

```bash
gh pr create --base develop --head feat/task-event-store --title "feat(events): add event store" --body-file .github/pull_request_template.md
```

没有 GitHub CLI 时，在 GitHub Web 页面创建 PR，字段保持一致。

## 7. Review 规则

合并前必须满足：

- 至少 1 人 Review 通过。
- CI 全部通过。
- 没有未解决 conversation。
- 数据库迁移包含回滚说明。
- 涉及 UI 的 PR 包含截图。
- 涉及 API 的 PR 更新 AI 读文档。
- 涉及产品流程的 PR 更新人读文档。

禁止直接向 `main` 推送。禁止 force push 到 `main` 和 `develop`。

## 8. 合并策略

功能分支合并到 develop 使用 squash merge。release 分支合并到 main 使用 merge commit。

本地同步：

```bash
git checkout develop
git pull --ff-only origin develop
git branch -d feat/task-event-store
```

## 9. Release 流程

创建 release 分支：

```bash
git checkout develop
git pull --ff-only origin develop
git checkout -b release/2026.05.04
```

发布前检查：

```bash
npm run build --workspaces
pytest
docker compose -f deploy/docker-compose/docker-compose.yml config
```

打标签：

```bash
git checkout main
git pull --ff-only origin main
git tag -a v2026.05.04 -m "release: v2026.05.04"
git push origin v2026.05.04
```

Release Notes 包含：

```text
Added
Changed
Fixed
Migration
Deployment
Rollback
```

## 10. Hotfix 流程

```bash
git checkout main
git pull --ff-only origin main
git checkout -b hotfix/<issue>
```

修复后：

```bash
git add <files>
git commit -m "fix(scope): summary"
git push -u origin hotfix/<issue>
```

Hotfix PR 合并到 main 后，必须同步回 develop：

```bash
git checkout develop
git pull --ff-only origin develop
git merge origin/main
git push origin develop
```

## 11. GitHub Actions

固定工作流：

```text
.github/workflows/docs.yml
.github/workflows/frontend.yml
.github/workflows/backend.yml
.github/workflows/docker.yml
```

docs.yml：

- 检查 Markdown 链接。
- 检查文档关键词。
- 检查 AI 读文档是否包含权威技术栈。

frontend.yml：

- 安装 Node 依赖。
- 运行 lint。
- 运行 build。

backend.yml：

- 安装 Python 依赖。
- 启动 PostgreSQL 和 Redis service。
- 运行 Alembic migration。
- 运行 pytest。

docker.yml：

- 构建 API 镜像。
- 构建 worker 镜像。
- 验证 docker-compose 配置。

## 12. GitHub Secrets

必须配置：

```text
DOCKER_REGISTRY
DOCKER_USERNAME
DOCKER_PASSWORD
DEPLOY_HOST
DEPLOY_USER
DEPLOY_SSH_KEY
```

模型密钥不进入 GitHub Actions 默认环境。模型密钥只在部署环境的 secret manager 或服务器 `.env` 中配置。

## 13. Issue 管理

Issue 类型：

```text
Feature
Bug
Docs
Security
Ops
Research
```

Issue 必须包含：

```text
Background
Goal
Scope
Acceptance Criteria
Risk
Related Docs
```

## 14. 文档同步规则

代码改动和文档同步关系：

```text
API 改动 -> 更新 docs/ai/reference/data-events-api.md
事件类型改动 -> 更新 docs/ai/reference/data-events-api.md
技术栈改动 -> 更新 docs/ai/reference/architecture-and-decisions.md
页面结构改动 -> 更新 docs/human/05-frontend-product.md 和 docs/ai/reference/frontend-spec.md
部署改动 -> 更新 docs/human/07-deployment-operations.md 和 docs/ai/reference/runtime-deployment-spec.md
Git 流程改动 -> 更新 docs/human/00-git-github-workflow.md 和 docs/ai/02-stage-01-git-github.md
```
