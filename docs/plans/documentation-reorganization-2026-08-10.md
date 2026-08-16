# 文档体系重组计划

_状态：completed | 更新：2026-08-10 | 范围：仓库文档源文件与任务状态，不包含业务代码重构_

## 目标

将 `docs/` 下的源文档按 dev-workflow 的职责边界归类，保留单一权威来源，减少重复进度/规格/Runbook，物理归档历史材料，并把仍未完成的事项同步到 `docs/TASKS.md`。

## 保留边界

- `.omx/`：OMX 运行状态、spec、plan 和报告，属于执行引擎输入，不迁移。
- `omx_wiki/`：跨会话历史知识库，保留原位，只更新链接。
- `apps/**/public/help`、各应用/服务 README：随子项目部署或构建的产品/包文档，保留原位并在总索引登记。
- `docs/ai` 的全部内容会移动到 `docs/development/ai`；启动协议、上下文索引和 CI 路径同步更新，不保留完整重复副本。
- 重复或过时材料先移动到 `docs/工作日志/archive/`，不直接删除；截图、GIF、DOCX 等证据只移动其说明文档/历史目录，不改写二进制内容。

## 目标路由

| 当前来源 | 目标目录 | 处理原则 |
|---|---|---|
| `docs/ai/` | `docs/development/ai/` | AI 启动、阶段、参考规格和机器进度的唯一来源 |
| `docs/adr/` | `docs/architecture/adr/` | ADR 原文归入架构；索引保留一份 |
| `docs/00-10-*.md` | `docs/design/`、`docs/architecture/`、`docs/contracts/`、`docs/testing/` | 按产品、架构、契约、评测职责拆分并更新索引 |
| `docs/contracts/api/`、`docs/contracts/api-reference/` | `docs/contracts/api/`、`docs/contracts/api-reference/` | OpenAPI 源/生成物同属契约，生成脚本改用新路径 |
| `docs/human/` | 各领域目录 | 按开发、设计、架构、运维、计划、任务职责拆分；不保留第二套权威源 |
| `docs/project-memory/runbooks/` | `docs/project-memory/runbooks/` | 可重复操作与排障保留为长期 Runbook |
| `docs/工作日志/reports/` | `docs/工作日志/reports/` | 历史评审、验证报告和 DOCX 归档 |
| `docs/design/media/demo/`、`docs/design/media/gifs/`、`docs/design/media/screenshots/` | `docs/design/media/` | 演示说明和视觉证据按设计/媒体归档 |
| `docs/testing/evals/`、`docs/testing/qa/`、`docs/testing/benchmark-spec.md` | `docs/testing/` | 测试策略、Eval、Benchmark 统一入口 |
| `docs/plans/roadmap.md`、`docs/plans/workspace-pro-gap-register.md` | `docs/plans/` | 当前计划/差距登记；已关闭项转历史说明 |
| `docs/development/cli/`、`docs/development/sdk/`、`docs/development/CONTRIBUTING.md` | `docs/development/` | 开发、CLI、SDK 与贡献流程 |
| `docs/architecture/terminal-architecture.md`、`docs/architecture/websocket-architecture.md`、`docs/project-memory/runbooks/troubleshooting-overview.md` | `docs/architecture/` 或 `docs/project-memory/runbooks/` | 依据架构/操作职责合并重复内容 |

## 任务板核验结果

当前真实待办只保留：`/settings/data` 404、`/subagents/specialists` 路由/权限失败、Desktop 真实打包启动 P95 证据缺口、可选 Tempo/Loki 全基础设施验证。`.kiro` 多步骤清单和旧前端测试缺口与当前实现冲突，归档为历史计划，不机械复制。

## 分批执行

1. [x] 移动 AI 协议、ADR、规格、API、Runbook 和历史材料，建立目录索引。
2. [x] 全局更新相对链接、硬编码路径、生成脚本、CI 和上下文路由。
3. [x] 归并重复任务/进度/规格，更新 `docs/TASKS.md` 和 `docs/PROJECT-SUMMARY.md`。
4. [x] 添加全量 Markdown 本地链接检查，运行现有 docs、dev-workflow、生成物和 diff 门禁。

## 完成结果

- 当前文档按 `architecture/`、`design/`、`plans/`、`contracts/`、`development/`、`testing/`、`operations/`、`project-memory/` 和 `工作日志/` 分类；旧目录由校验器禁止重新出现。
- 重复产品规格与进度权威源已合并或归档，历史材料保留在 `工作日志/archive/`，不再参与当前状态判断。
- 任务审计只保留 `APP-001`、`APP-002`、`REL-001`、`OPS-001` 四个有证据的未完成事项，`DW-002` 已移入 Done。
- API reference、14 模块索引、docs 校验、全仓 Markdown 本地链接检查、上下文 brief 夹具、Python 编译、严格 dev-workflow 审计和 diff 检查全部通过；会话证据见 [Wiki 记录](../../omx_wiki/session-2026-08-10-dev-workflow-install-and-docs.md)。

## 回滚与安全

- 每批迁移前记录 `git status` 和文件清单；只使用 `git mv`，不覆盖现有文件。
- 归档文件可从 `docs/工作日志/archive/` 恢复；本次不使用递归删除。
- 发现外部链接、生成物或启动契约无法同步时暂停该批次，保留原文件并记录阻塞。
