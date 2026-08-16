---
status: inactive
updated: 2026-08-11
expires: 2026-08-11
scope: current-task
task_id: DW-003
---

# 当前任务上下文

> 这是当前主任务的共享短期记忆。只记录本次任务的目标、进展、临时决策、阻塞、下一步和验证摘要，不混入长期事实、多个并行任务或敏感信息。
>
> 任务完成或超过 `expires` 后清理内容；需要长期复用的已验证经验写入 [`project-memory/`](project-memory/)，完整过程证据写入工作日志（如项目启用）。

## 当前目标

补齐 `dev-workflow v0.2.0` 的仓库交付闭环：让 Docs CI 强制执行统一文档与全仓 Markdown 链接门禁，并锁定该 CI 契约。

## 范围与非目标

范围包括 Docs CI、文档校验器、dev-workflow manifest、任务/进度状态和相关 Wiki 证据；不修改业务运行时代码，不执行生产发布。

## 计划与当前阶段

任务已完成，本文件仅保留关闭摘要，不再作为活动上下文。

## 已完成

1. Docs CI 改为运行 `bash scripts/check-docs.sh`，统一执行结构校验和全仓 Markdown 本地链接检查。
2. `validate-docs.py` 新增 CI 契约检查，防止统一门禁或 API 生成物漂移检查被移除。
3. dev-workflow manifest、接入记录、Task Board、机器进度和 Wiki 交接同步到 2026-08-11 最终审计证据。

## 当前决策

本地和 CI 使用同一个 `scripts/check-docs.sh` 入口；`validate-docs.py` 负责结构与 CI 契约，`check-markdown-links.py` 负责仓库级本地链接。

## 阻塞与风险

实现无阻塞。用户已确认既有业务改动与 dev-workflow 同批交付；可再生成的 Desktop `release*` 发布目录和 `resources/runtime/<platform>/<arch>` sidecar 已从 Git 索引排除并加入忽略规则，本地文件保持不变。Desktop 通用类型检查配置债已登记为 `DESK-001`。

## 下一步

`DW-003` 已移入 Done。后续产品、运维和技术债事项继续以 `TASKS.md` 为准。

## 验证证据

最终验证通过：`bash scripts/check-docs.sh`、严格 dev-workflow 审计、后端 `1537` 项全量回归与 Ruff、Agent Console lint/build、Desktop `324` 项测试、主进程构建、启动预算测试、暂存差异检查和敏感信息模式扫描。Desktop 非生产 `type-check` 的既有配置债已显式登记为 `DESK-001`。详细结果见 [Wiki 会话记录](../omx_wiki/session-2026-08-10-dev-workflow-install-and-docs.md)。

## 生命周期规则

- 只保留一个当前主任务的上下文；并行任务使用 delivery 包提供的任务专属上下文目录。
- 每次有实质进展或交接时更新 `updated`，并按需调整 `expires`。
- 任务完成后清空本文件正文或删除本文件；长期知识迁移到 `project-memory/`，历史证据迁移到工作日志。
- 不保存密码、Token、Cookie、私钥、完整签名 URL 或其他敏感凭据。
