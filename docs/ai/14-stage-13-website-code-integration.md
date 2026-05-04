# 14 阶段 13：Website Code Integration

本阶段补齐官网代码接入。官网前端代码由用户提供，AI 不从零生成官网视觉稿，不重写用户提供的页面结构。阶段 13 的固定目标是把用户提供的官网代码纳入 `apps/web-site`，接入后端、文档、OpenAPI 和控制台入口，并完成构建、部署和验收。

## Required Context

```text
docs/ai/00-master-prompt.md
docs/ai/00-execution-protocol.md
docs/ai/task-progress.yaml
docs/human/02-product-positioning.md
docs/human/03-system-architecture.md
docs/human/05-frontend-product.md
docs/human/10-task-progress.md
docs/human/11-website-usage-flow.md
docs/design/figma-production-brief.md
docs/design/page-inventory.md
docs/ai/reference/frontend-spec.md
docs/api/openapi-contract.md
docs/api/openapi.yaml
docs/api/openapi.json
apps/web-site
apps/agent-console
deploy/docker-compose/docker-compose.yml
deploy/nginx/agent-harness.conf
```

## AI 执行提示词

```text
你是本项目的官网代码接入 Agent。现在执行阶段 13：Website Code Integration。

固定分支：stage/stage-13-website-code-integration
固定 base：develop
固定目标：接收用户提供的官网前端代码，保留其视觉与页面结构，完成 Next.js 工程化、后端接入、控制台导流、文档入口、OpenAPI 入口和部署接入。

开始前必须执行：
1. git status --short
2. git branch --show-current
3. git fetch origin
4. git checkout develop
5. git pull --ff-only origin develop
6. git checkout -b stage/stage-13-website-code-integration
7. 读取 docs/ai/task-progress.yaml
8. 读取 docs/human/10-task-progress.md
9. 确认用户已提供官网前端代码
10. 将 stage-13-website-code-integration 状态标记为 in_progress

完成后必须执行：
1. cd apps/web-site && npm run lint
2. cd apps/web-site && npm run build
3. docker compose -f deploy/docker-compose/docker-compose.yml config
4. python3 scripts/validate-docs.py
5. 更新 docs/ai/task-progress.yaml
6. 更新 docs/human/10-task-progress.md
7. git status --short
8. git add .
9. git commit -m "feat(stage-13): integrate website code"
10. git push -u origin stage/stage-13-website-code-integration
11. gh pr create --base develop --head stage/stage-13-website-code-integration --title "feat(stage-13): integrate website code" --body "Integrates the supplied website code with backend, console, docs, OpenAPI, and deployment entry points."

禁止事项：
- 禁止重写用户提供的官网视觉结构。
- 禁止把 Gemini/H5 产物直接作为生产代码。
- 禁止在官网中实现控制台任务执行逻辑。
- 禁止把未实现功能写成已上线能力。
- 禁止改变控制台 React + Vite 技术栈。
```

## 接入范围

### 官网工程

```text
apps/web-site/package.json
apps/web-site/next.config.*
apps/web-site/tsconfig.json
apps/web-site/app/**
apps/web-site/components/**
apps/web-site/lib/**
apps/web-site/styles/**
```

### 官网页面

```text
/
/product
/architecture
/solutions
/security
/deployment
/docs
/contact
```

### 后端与控制台联动

```text
API health 链接
OpenAPI JSON 链接
OpenAPI YAML 链接
控制台 /tasks 链接
控制台 /tasks/new 链接
控制台 /observability 链接
部署文档链接
使用流程文档链接
```

### 页面内容边界

```text
官网负责介绍产品、架构、能力、部署、文档入口。
控制台负责创建任务、启动任务、查看事件、查看结果、Replay、Settings、Observability。
后端负责 API、事件、任务状态、模型调用、工具调用、沙箱和审计。
```

## 验收

- 用户提供的官网代码已进入 `apps/web-site`。
- 官网保持用户提供的视觉结构。
- 官网使用 Next.js + TypeScript + Tailwind CSS。
- 官网首页展示 `生产级企业 AI Agent Harness 平台`。
- 官网展示 `Model + Harness = Agent`。
- 官网展示 Planner、Executor、Subagent、Event Sourcing、Docker Sandbox、WarmPool。
- 官网提供控制台、OpenAPI、部署文档、使用流程入口。
- 官网 Docker Compose 接入完成。
- 官网 Nginx 路由接入完成。
- 官网构建通过。

## Verification Commands

```bash
cd apps/web-site && npm run lint
cd apps/web-site && npm run build
docker compose -f deploy/docker-compose/docker-compose.yml config
python3 scripts/validate-docs.py
```

## Progress Update Rule

阶段 13 执行期间固定更新：

```text
开始实现前：docs/ai/task-progress.yaml status=in_progress
开始实现前：docs/human/10-task-progress.md 当前状态=in_progress
验证通过后：docs/ai/task-progress.yaml verification_result=passed
验证通过后：docs/human/10-task-progress.md 验证结果=passed
提交后：docs/ai/task-progress.yaml commit_sha 写入实现提交
创建 PR 后：docs/ai/task-progress.yaml pr_url 写入 PR 地址
创建 PR 后：docs/human/10-task-progress.md status=ready_for_review
```
