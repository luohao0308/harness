# 实施计划导航

_状态：当前计划索引 | 更新：2026-08-20_

`docs/plans/` 保存多步骤、高风险或跨模块变更的当前实施计划。它不是任务状态板；任务状态仍以 `docs/TASKS.md` 为准。

## 何时需要计划

- 跨多个模块、仓库或团队；
- 涉及公共契约、数据迁移、权限、安全或部署；
- 存在明显方案取舍、兼容窗口或回滚要求；
- 预计需要多个独立验证阶段或交接。

小型、局部、低风险且可一次验证的改动可以直接实施，但仍需满足项目验证标准。

## 大型计划确认门

用户明确提出大规划、roadmap 或多阶段交付，或者任务涉及高风险契约/迁移/安全/发布边界时，直接按大型计划处理。其他任务若同时出现跨两个以上模块、三个以上顺序阶段、多个独立验收结果、无法在一个专注开发会话内完成等至少两个信号，也按大型计划处理。

大型计划的固定流程：

1. AI 只读核对现状，自动拆成 `2-6` 个有序、可独立验证的开发切片。
2. 在对话中列出每个切片的目标结果、范围、依赖、验收和回退点，状态为 `awaiting_user_confirmation`。
3. 用户批准原拆分，或要求合并、继续拆分、重排、增删范围；确认前不开始实现或创建交付 PR。
4. 确认后使用 [TEMPLATE.md](TEMPLATE.md) 落盘，状态改为 `approved`，每次只允许一个切片为 `in_progress`。
5. 当前切片完成验证并记录证据后自动进入下一切片；只有范围、顺序、接口、迁移或风险发生实质变化时才重新确认。

切片不是微任务清单。每个切片应交付一个可观察结果，能在一次专注开发会话内完成并验证；默认整个计划仍使用一个交付分支和一个 PR，只有切片可以独立发布或需要风险隔离时才拆成多个 PR。

## 计划索引

| 计划 | 状态 | 关联任务/设计 | 当前阶段 | 更新时间 |
|---|---|---|---|---|
| [desktop-trigger-integrity-hardening-2026-08-19.md](desktop-trigger-integrity-hardening-2026-08-19.md) | completed | `HARD-001`、[DESIGN.md](../../DESIGN.md) | S1-S5 已完成；本地包通过，正式三平台证据仍归 `REL-001` | 2026-08-20 |
| [desktop-next-capabilities-roadmap-2026-08-17.md](desktop-next-capabilities-roadmap-2026-08-17.md) | approved | `REL-001`、`DESK-002`–`DESK-006` | `DESK-002`–`DESK-006` 已完成；`REL-001` 外部阻塞 | 2026-08-20 |
| [feature-catalog-pilot-2026-08-17.md](feature-catalog-pilot-2026-08-17.md) | completed | `FCAT-001` | 四个切片已完成；目录、矩阵、brief 和 Docs 门禁均通过 | 2026-08-17 |
| [desktop-reliability-closeout-2026-08-16.md](desktop-reliability-closeout-2026-08-16.md) | completed | `APP-001`、`APP-002`、`DESK-001`、`REL-001` | 已完成；REL-001 等待正式 Release runner | 2026-08-17 |
| [desktop-local-session-renewal-2026-08-11.md](desktop-local-session-renewal-2026-08-11.md) | active | Desktop 本地会话续期 | 实施与验证 | 2026-08-11 |
| [documentation-reorganization-2026-08-10.md](documentation-reorganization-2026-08-10.md) | completed | `DW-002`、[Task Board](../TASKS.md) | 已完成并验证 | 2026-08-10 |
| [roadmap.md](roadmap.md) | active | 生产就绪路线 | 持续维护 | 2026-08-10 |
| [roadmap-acceptance.md](roadmap-acceptance.md) | reference | 阶段交付与验收 | 历史/参考 | 2026-08-10 |
| [workspace-pro-gap-register.md](workspace-pro-gap-register.md) | verified register | Workspace Pro | 已关闭项核验 | 2026-08-10 |
| [desktop-team-overview-focus-2026-08-13.md](desktop-team-overview-focus-2026-08-13.md) | completed | Desktop Team 概览 / 专注融合 | 阶段 1-3 已实现 | 2026-08-13 |
| [desktop-startup-p95-optimization-2026-08-17.md](desktop-startup-p95-optimization-2026-08-17.md) | completed_with_cold-run-residual | `REL-001` | 模板、启动诊断、桌面首屏预加载已交付；正式 runner 复核待完成 | 2026-08-17 |

## 维护规则

- 计划必须有范围、非范围、证据基线、步骤、验收、风险、迁移/回滚和完成定义。
- 大型计划必须记录用户确认状态和确认后的切片版本；`awaiting_user_confirmation` 不得进入实现。
- 每次只允许一个切片为 `in_progress`，不得在结束时一次性把多个未记录过程的切片全部标为完成。
- 实施中发现事实变化时更新计划，不保留已经失真的步骤作为当前指令。
- 完成后把稳定事实同步到架构/摘要，把可重复经验同步到 `project-memory/`。
- 旧计划标记为 superseded 或归档，不与当前计划并行充当权威源。

新计划从 [TEMPLATE.md](TEMPLATE.md) 复制。
