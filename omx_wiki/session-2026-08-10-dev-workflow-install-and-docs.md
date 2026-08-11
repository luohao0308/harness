# dev-workflow v0.2.0 接入与文档整理

Category: `session-log`

Tags: `dev-workflow`, `documentation`, `onboarding`, `harness`

## 结果

已将 GitHub 仓库 `luohao0308/dev-workflow` 的最新稳定 Release `v0.2.0` 接入 Harness 工作区，并安装 Core 与全部五个流程包：`architecture`、`contracts`、`delivery`、`design`、`operations`。

安装器保留了既有 `AGENTS.md` 和根 `DESIGN.md`，创建 `.dev-workflow/manifest.json`，并在 `AGENTS.md` 追加稳定标记的通用核心区块。manifest 的 `workflowVersion` 为 `0.2.0`，`onboarding.status` 与 `docs/WORKFLOW-ADOPTION.md` 均为 `ready`。

## 文档整理

- `docs/README.md` 现在是统一导航，当前权威源按 `architecture/`、`design/`、`plans/`、`contracts/`、`development/`、`testing/`、`operations/`、`project-memory/` 和 `工作日志/` 分类。
- `docs/PROJECT-SUMMARY.md` 填入已验证的仓库拓扑、模块职责、运行时、命令矩阵、契约/数据/凭据边界和路径速查。
- 旧 `docs/ai`、`docs/human`、`docs/runbooks`、`docs/adr`、`docs/api` 与报告目录已迁移到对应职责目录；校验器阻止旧目录重新出现。
- 重复产品规格合并到 `docs/design/product-spec.md`；旧进度与被替代的产品/架构说明移入 `docs/工作日志/archive/`，保留追溯但不再作为当前权威。
- `docs/TASKS.md` 只保留四个有证据的未完成事项：`APP-001`、`APP-002`、`REL-001`、`OPS-001`。历史已实现清单和未批准提案不进入当前任务板。
- `docs/WORKING-CONTEXT.md` 已关闭为 inactive，实施计划标记 completed，`DW-002` 已移入 Done。
- 新增仓库级 Markdown 本地链接校验脚本，并接入 `scripts/check-docs.sh` 与 Docs CI；API reference、模块索引、上下文路由和相关 Wiki 链接已同步到新路径。
- 反向审计发现并修正活动入口中的旧权威声明：`docs/README.md`、AI 总控提示和 Git 流程现在都指向 `docs/TASKS.md`、机器进度与相关 Wiki 交接；`validate-docs.py` 会阻止这些归档进度路径回归。
- 根 `AGENTS.md` 增加 Harness 项目扩展规则，约束文档读取顺序、契约同步和发布/凭据边界。

## 验证

- `LC_ALL=C bash <dev-workflow-v0.2.0>/scripts/audit.sh --target <project> --strict` -> `result: ready`
- `python3 scripts/validate-docs.py` -> `docs validation passed`
- `bash scripts/check-docs.sh` -> docs 与仓库级 Markdown 链接门禁通过
- `python3 scripts/check-markdown-links.py` -> 检查 `620` 个 Markdown 文件、`473` 个本地链接，缺失 `0`
- `python3 scripts/generate-api-docs.py` -> `docs/contracts/api-reference/` 可重生成
- `python3 scripts/agent-context-brief.py --gen-module-index` -> `docs/architecture/MODULE-INDEX.md` 共 `14` 个模块
- 上下文 brief 夹具与 Python 编译 -> 通过
- `git diff --check` -> 通过
- manifest JSON 解析 -> `schemaVersion=2`、五个流程包、`ready` 状态

## 2026-08-11 CI 交付闭环

- Docs CI 现在直接运行 `bash scripts/check-docs.sh`，统一执行 `validate-docs.py` 与仓库级 Markdown 本地链接检查。
- `validate-docs.py` 新增 Docs CI 契约校验，要求统一门禁和 API reference 漂移检查持续存在。
- `.dev-workflow/manifest.json` 的 `updatedAt` 与 `onboarding.lastAuditAt` 更新为本轮 UTC 审计时间；Core、五个流程包和 onboarding 状态继续为 `ready`。
- `DW-003` 已关闭；产品与运维待办仍由 `docs/TASKS.md` 管理，不与 dev-workflow 接入状态混淆。

## 2026-08-11 Git 交付闭环

- 用户确认既有业务改动与 dev-workflow 同批提交到 `codex/desktop-team-ai-provider`。
- `.gitignore` 统一排除 `apps/desktop-app/release*/` 与 `apps/desktop-app/resources/runtime/<platform>/<arch>/`；从索引移除 `5205` 个可再生成文件，本地 Electron 包和 `harnessd` sidecar 保持不变。
- 最终暂存区包含 `697` 个源代码、配置、测试和文档文件，不包含发布目录或生成的 native runtime；暂存差异检查与强密钥模式/敏感文件名扫描通过。
- 后端全量回归 `1537 passed`，Ruff 通过；Agent Console lint 与 `2414` 模块生产构建通过；Desktop `38` 个文件、`324` 个测试、主进程构建与 `5` 项启动预算测试通过。
- Desktop 的通用 `npm run type-check` 仍会混合 Node 主进程、浏览器和 Vitest 测试类型环境；该项不影响已通过的生产主进程构建和运行测试，已作为 `DESK-001` 登记在 `docs/TASKS.md`，不把未通过项隐藏在完成声明中。

## 风险与边界

初始 `v0.2.0` 稳定分支的 Bash 安装器和审计器曾在 Bash `set -u` 下对空数组使用未保护展开；随后已从 `feature/bash-3-array-compat` 拉取提交 `a454fe0`，该分支统一使用 Bash 3.2 兼容展开。使用修复后的安装器重新执行正式安装和严格审计，结果为 `ready`；目标项目没有复制上游脚本，也没有修改业务代码。

本次没有使用 reset、checkout 或删除本地构建产物；所有用户确认的业务改动均保留在交付范围内。
