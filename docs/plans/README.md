# 实施计划导航

_状态：当前计划索引 | 更新：2026-08-10_

`docs/plans/` 保存多步骤、高风险或跨模块变更的当前实施计划。它不是任务状态板；任务状态仍以 `docs/TASKS.md` 为准。

## 何时需要计划

- 跨多个模块、仓库或团队；
- 涉及公共契约、数据迁移、权限、安全或部署；
- 存在明显方案取舍、兼容窗口或回滚要求；
- 预计需要多个独立验证阶段或交接。

小型、局部、低风险且可一次验证的改动可以直接实施，但仍需满足项目验证标准。

## 计划索引

| 计划 | 状态 | 关联任务/设计 | 当前阶段 | 更新时间 |
|---|---|---|---|---|
| [desktop-local-session-renewal-2026-08-11.md](desktop-local-session-renewal-2026-08-11.md) | active | Desktop 本地会话续期 | 实施与验证 | 2026-08-11 |
| [documentation-reorganization-2026-08-10.md](documentation-reorganization-2026-08-10.md) | completed | `DW-002`、[Task Board](../TASKS.md) | 已完成并验证 | 2026-08-10 |
| [roadmap.md](roadmap.md) | active | 生产就绪路线 | 持续维护 | 2026-08-10 |
| [roadmap-acceptance.md](roadmap-acceptance.md) | reference | 阶段交付与验收 | 历史/参考 | 2026-08-10 |
| [workspace-pro-gap-register.md](workspace-pro-gap-register.md) | verified register | Workspace Pro | 已关闭项核验 | 2026-08-10 |
| [desktop-team-overview-focus-2026-08-13.md](desktop-team-overview-focus-2026-08-13.md) | completed | Desktop Team 概览 / 专注融合 | 阶段 1-3 已实现 | 2026-08-13 |

## 维护规则

- 计划必须有范围、非范围、证据基线、步骤、验收、风险、迁移/回滚和完成定义。
- 实施中发现事实变化时更新计划，不保留已经失真的步骤作为当前指令。
- 完成后把稳定事实同步到架构/摘要，把可重复经验同步到 `project-memory/`。
- 旧计划标记为 superseded 或归档，不与当前计划并行充当权威源。

新计划从 [TEMPLATE.md](TEMPLATE.md) 复制。
