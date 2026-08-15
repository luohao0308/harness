# 开发与交付入口

_状态：active | 更新：2026-08-10_

本页把项目真实可执行的开发命令、Git 策略、服务边界和变更影响集中到一个入口。命令必须来自仓库脚本、配置或 CI，不凭经验猜测。

## 文档地图

| 路径 | 内容 |
|---|---|
| [ai/](ai/) | AI 启动协议、上下文路由、阶段规格和机器进度 |
| [CONTRIBUTING.md](CONTRIBUTING.md)、[git-github-workflow.md](git-github-workflow.md) | 贡献、分支、提交和 PR 规则 |
| [GIT-WORKTREE-WORKFLOW.md](GIT-WORKTREE-WORKFLOW.md) | 多任务 worktree 隔离流程 |
| [development-flow.md](development-flow.md)、[technology-operation-flows.md](technology-operation-flows.md) | 研发阶段与技术落地入口 |
| [cli/](cli/)、[sdk/](sdk/) | CLI 与 SDK 使用说明 |
| [desktop/README.md](desktop/README.md) | Desktop 本地启动、验证与发布边界 |

## 仓库与工作区

| 仓库/路径 | 默认集成分支 | 包管理/运行环境 | 所有权 | 备注 |
|---|---|---|---|---|
| `/Users/luohao/Desktop/agent_workspace/harness` | `main` / 当前任务分支 | Git + Python 3.11 + Node 20 + Docker | 全仓库 | 共享工作区；任务必须尊重已有改动 |

## 命令矩阵

| 目的 | 命令 | 工作目录 | 适用条件 |
|---|---|---|---|
| 安装依赖 | `pip install -e ".[dev]"`；`npm ci` | API/Console/Desktop 目录 | 各自 lockfile/venv；Node 20+ |
| 本地启动 | `docker compose -f compose.production.yml up -d --build`；`npm run dev` | 根/Console | 依赖 PostgreSQL/Redis；运行前读取 local-development Runbook |
| 定向测试 | `pytest tests/<target>.py`；`npm test -- <pattern>` | API/Console | 优先覆盖改变的模块 |
| 全量测试 | `pytest tests`；`npm test`；Desktop `npm test` | API/Console/Desktop | 跨模块、发布或高风险变更 |
| lint/format | `ruff check app tests`；Console `npm run lint -- --pretty false` | API/Console | CI 同步执行 |
| 类型/静态检查 | Console `npm run lint`；Desktop `npm run type-check`；`python3 -m py_compile <script>` | 客户端/脚本 | 变更入口对应执行 |
| 构建/打包 | Console `npm run build`；Desktop `npm run build`；Website `npm run build` | 各前端目录 | 产物身份使用 commit/tag |
| 数据迁移 | `alembic upgrade head`、`scripts/check-migration-ids.py` | API | 先备份/恢复演练，见 `docs/project-memory/runbooks/migrations.md` |
| CI | `.github/workflows/pr-check.yml`、`backend.yml`、`frontend.yml`、`docs.yml`、`docker.yml`、`main-build.yml` | 根目录 | 以目标 workflow 的 required gates 为准 |

## Git 与隔离策略

- Worktree 模式：recommended；当前工作树已有大量用户改动，任务必须先记录并隔离所有权。
- 分支命名：日常使用短生命周期 `feat/*`、`fix/*`、`docs/*`、`chore/*`；Agent 临时 worktree 可以使用 `codex/` 前缀，但交付 PR 仍按产品范围命名。
- 提交格式：遵循 [CONTRIBUTING.md](../../CONTRIBUTING.md) 的 Conventional Commit policy，commit 与 PR title 共用同一规则。
- 集成策略：按仓库维护者要求使用 PR/受控合并；不执行强制 reset/checkout。
- 自动允许：本地可逆的读、编辑、测试、构建和文档审计。
- 需要确认：push/merge、生产发布、真实第三方凭据、签名/公证和不可逆迁移。

若 Worktree 模式为 `required` 或 `recommended`，按 [GIT-WORKTREE-WORKFLOW.md](GIT-WORKTREE-WORKFLOW.md) 执行。

## 本地服务登记

| 服务 | 启动入口 | 健康/冒烟入口 | 端口策略 | 安全停止方式 |
|---|---|---|---|---|
| API server | Compose `api-server` 或 `.venv/bin/uvicorn app.main:app --reload` | `/api/health/readiness` | Compose-defined | 以 Compose project/container 检查并用 `docker compose down` 停止 |
| Agent Console | `npm run dev` | Vite local page | `127.0.0.1` + configured port | 由当前终端/Compose project 管理 |
| Desktop | `npm run start` | Native bridge/readiness tests | local profile | 退出 Electron；不杀不属于当前任务的进程 |
| Full stack | `docker compose -f compose.production.yml up -d --build` | readiness + Agent Run smoke | Compose-defined | `docker compose ... down`，不删除卷除非明确授权 |

## 变更影响矩阵

| 变更类型 | 最低验证 | 需要同步的文档/产物 |
|---|---|---|
| 新增或改变模块边界 | 定向测试 + 静态检查 | `PROJECT-SUMMARY.md`、`architecture/` |
| API/事件/Schema 变化 | 契约测试 + 消费方回归 | `contracts/`、生成物、迁移说明 |
| 数据模型/迁移 | 迁移演练 + 数据断言 | 迁移模板、备份/恢复入口、架构数据说明 |
| 运行时代码/配置/依赖 | 定向测试 + 重启 + 冒烟 | 本页命令、Runbook、配置说明 |
| 部署/基础设施 | 配置校验 + Preflight + 回滚演练 | `operations/`、Runbook、观测入口 |
| 重复性故障经验 | 修复回归测试 | `project-memory/` |
| 纯文档 | 链接、格式、事实来源检查 | 对应索引 |

## 完成定义

- 变更范围清晰且没有夹带无关修改。
- 适用检查通过，或未运行项有原因与替代证据。
- 运行时变更完成任务自有服务重启和冒烟。
- 契约、迁移、架构、任务和长期知识已按影响同步。
- 交付摘要包含文件、命令、结果、风险和后续动作。
