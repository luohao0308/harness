# Task Board

_last-updated: 2026-08-16_

> **唯一用途**：记录当前进行中、明确待办、阻塞和技术债。稳定事实写入架构/设计文档，详细验证过程写入工作日志（如项目启用）。
>
> 状态：`[~]` 进行中或阻塞 | `[ ]` 已批准但尚未开始 | `[x]` 仅出现在“已完成”章节。
>
> 当前任务的临时目标、决策、交接提示和验证摘要写入 [WORKING-CONTEXT.md](WORKING-CONTEXT.md)，不要复制到本文件。
> 完整机器进度与历史验证记录以 `docs/development/ai/task-progress.yaml` 为准。

---

## 进行中 (In Progress)

| ID | 任务 | 范围/仓库 | 上下文 | 阻塞 |
|---|---|---|---|---|
| DESK-002 | [~] 将 Desktop 模型目录改为检测后持久化的动态 allowlist | Desktop IPC/profile、local runtime、设置页 | [实施计划](plans/desktop-dynamic-model-catalog-2026-08-16.md) | 无 |
| REL-001 | [~] 在正式 Release CI 获得 macOS/Windows/Linux 真实打包 Desktop 启动五样本 P95 证据 | Desktop packaging、release workflow | [启动性能记录](../omx_wiki/session-2026-07-31-desktop-startup-performance-budget.md) | 本地 native ABI/审批服务不能替代正式 Release CI 证据 |

## 待办 (Todo)

- [ ] APP-001：修复 `/settings/data` 路由、loader 与 API 契约；当前截图审计记录为 404。证据见 [Desktop 功能截图审计](../omx_wiki/session-2026-08-07-desktop-functional-screenshot-audit.md)。
- [ ] APP-002：修复 `/subagents/specialists` 路由解析或 ID/权限处理；当前审计记录为终态加载失败。证据见 [Desktop 功能截图审计](../omx_wiki/session-2026-08-07-desktop-functional-screenshot-audit.md)。
- [ ] OPS-001：环境具备时运行 Tempo + Loki 全基础设施验证配置，并记录 trace/log 关联证据；该项不是常规 release-gate hygiene 的前置条件。历史边界见 [归档进度说明](工作日志/archive/task-progress-human.md)。

## 未授权或未立项 (Do Not Start)

<!-- 记录明确禁止自动执行或尚未立项的事项，不使用任务复选框。 -->

- 生产发布、真实第三方凭据、签名/公证、破坏性迁移和强制 Git 操作：需要显式授权并按对应 Runbook 执行。

## 已完成 (Done)

<!-- 只保留简短结果和指向验证证据的链接；不要复制完整日志。 -->

- [x] DW-001：安装 `dev-workflow v0.2.0` 全部流程包，完成项目画像、文档映射和接入审计；证据见 [WORKFLOW-ADOPTION.md](WORKFLOW-ADOPTION.md)。
- [x] DW-002：按 dev-workflow 完成全仓文档分类、权威源去重、历史归档、任务审计和全量链接门禁；证据见 [实施计划](plans/documentation-reorganization-2026-08-10.md) 与 [Wiki 会话记录](../omx_wiki/session-2026-08-10-dev-workflow-install-and-docs.md)。
- [x] DW-003：将统一文档与 Markdown 链接门禁接入 Docs CI，并由 `validate-docs.py` 锁定 CI 调用契约；证据见 [接入记录](WORKFLOW-ADOPTION.md)。
- [x] GIT-001：以严格保留历史作者/提交者时间和文件树的方式重排线上功能分支，并建立轻量单维护者 OPC 提交流程；PR #34 已在 14 项检查通过后合并，原功能分支通过精确租约更新到已验证历史，独立归档仍保留原始 tip，证据见 [Git 历史与 OPC 交付记录](../omx_wiki/session-2026-08-16-git-history-opc-delivery.md)。
- [x] WF-001：建立大型计划自动拆分与用户确认门；AI 在实现前列出 `2-6` 个可验证切片并等待一次确认，确认后单切片连续执行，范围或风险实质变化时重新确认，证据见 [大型计划拆分门记录](../omx_wiki/session-2026-08-16-large-plan-decomposition-gate.md)。

## 技术债 (Technical Debt)

| 项目 | 风险 | 说明 |
|---|---|---|
| DESK-001 | 中 | `cd apps/desktop-app && npm run type-check` 当前会把主进程、浏览器和 Vitest 测试放在同一 TypeScript 环境中检查，暴露 DOM lib 缺失和测试 mock/fixture 类型债；生产 `build:main` 与 `38` 个测试文件、`324` 个测试均通过。需要拆分或校正 Desktop 类型检查配置。证据见 [dev-workflow 接入记录](../omx_wiki/session-2026-08-10-dev-workflow-install-and-docs.md)。 |

---

_维护方式：任务完成后从“进行中/待办”移动到“已完成”，再更新顶部日期。短期上下文完成或过期后清理；长期经验迁移到 `project-memory/`；历史证据迁移到工作日志。_
