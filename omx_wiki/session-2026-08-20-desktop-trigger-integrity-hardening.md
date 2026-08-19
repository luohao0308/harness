# Desktop / Trigger 完整性加固

日期：2026-08-20

任务：`HARD-001`

## 结果

HARD-001 的 S1-S5 已完成。Desktop、Trigger、Project Knowledge、离线同步、离线 Agent 和 Change Review 的边界问题已落到服务端归属校验、单调 generation、operation 级冲突、审批写入保护和审计幂等上；不满足可证明安全条件的路径保持 fail closed。

## 关键修复

- 新文件审批使用 no-replace hard-link，外部抢先创建目标时失败；已有文件无法证明跨平台 CAS 时拒绝覆盖，并保留审批等待状态。
- `DESKTOP_CHANGE_REVIEW_AUDITED` 使用数据库条件唯一索引，应用层捕获并发 `IntegrityError` 后返回既有 receipt。
- Project Knowledge snapshot 增加 generation，服务端按 generation 单调应用；旧客户端仍走兼容的时间逻辑。
- Offline queue 使用 `operation_id` 标记冲突，旧 operation 失败不会污染同 entity 的新 revision。

## 验证证据

- Backend 全量：`1647 passed`；返工聚焦审计/Project Knowledge/迁移：`27 passed`；Ruff 通过。
- Desktop：`42 files / 360 tests passed`，`npm run type-check` 和 `npm run build:main` 通过。
- Console：稳定复跑 `108 files / 812 tests passed`；Project Knowledge 聚焦 `3 files / 13 tests passed`；`npm run lint` 和 `npm run build` 通过，构建转换 `2419` modules。
- Feature Catalog、OpenAPI 生成、Docs validation、`git diff --check` 均通过。
- 本地 macOS x64 directory package 完成；`apps/desktop-app/dist/startup-budget-report-darwin-x64.json` 的五样本全部通过，总启动 P95 `3846ms`，预算 `6000ms`。

## 审查与边界

架构审查识别的四个问题均有实现和回归证据：文件写入 TOCTOU、Change Review 并发查重、Project Knowledge 墙钟排序和离线队列 entity 粗粒度冲突。独立 `code-reviewer` 两次因服务端 `429` 不可用，因此这里不宣称独立 APPROVE。

本地包未签名、未公证，且仅为 macOS x64。它是本地构建/启动证据，不满足 `REL-001` 的正式 macOS/Windows/Linux Release runner 验收；REL-001 仍处于暂停/外部阻塞状态。

## 关联

- [[project-handoff-current-state]]
- [[session-2026-08-19-desktop-offline-agent]]
- [实施计划](../docs/plans/desktop-trigger-integrity-hardening-2026-08-19.md)
