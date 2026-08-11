# 设计文档导航

_状态：当前设计导航 | 权威范围：尚未实现或仍在生效的产品/技术设计 | 更新：2026-08-10_

## 状态约定

| 状态 | 含义 |
|---|---|
| `draft` | 仍在收集证据或等待决策，不可直接视为实施授权 |
| `accepted` | 目标、边界和验收已确认，可进入计划或实施 |
| `implemented` | 已实现且验证完成，稳定事实应同步到架构/摘要 |
| `superseded` | 已被新设计替代，只用于历史追溯 |

## 当前设计索引

| 文档 | 状态 | 范围 | 关联任务/计划 | 更新时间 |
|---|---|---|---|---|
| [`../DESIGN.md`](../../DESIGN.md) | active | 产品、Console、Desktop 和交互约束 | [Figma brief](figma-production-brief.md)、[page inventory](page-inventory.md) | 2026-08-10 |
| [product-spec.md](product-spec.md) | active | 产品定位、概念、Workspace 模式和当前路由 | [功能索引](../contracts/SPEC-INDEX.md) | 2026-08-10 |
| [console-ui-spec.md](console-ui-spec.md) | active | Console/Workspace UI 行为契约 | [页面清单](page-inventory.md) | 2026-08-10 |
| [features/](features/) | active | 按功能拆分的产品 Spec | [Spec 模板](../contracts/SPEC-TEMPLATE.md) | 2026-08-10 |
| [`figma-production-brief.md`](figma-production-brief.md) | implemented/reference | 生产级页面视觉和交互方向 | `DESIGN.md`、Console styles | 2026-07-04 |
| [`page-inventory.md`](page-inventory.md) | implemented/reference | 页面/路由/截图覆盖 | `docs/contracts/SPEC-INDEX.md`、E2E | 2026-08-07 |
| [desktop/apple-style-guidelines.md](desktop/apple-style-guidelines.md)、[desktop/team-mode-workspace.md](desktop/team-mode-workspace.md) | implemented | Desktop 体验与 Team 工作区 | Desktop tests、Team wiki | 2026-07-28 |
| [product-positioning.md](product-positioning.md)、[frontend-product.md](frontend-product.md)、[website-usage-flow.md](website-usage-flow.md) | reference | 产品文案、前端和网站用户流程 | Product/Console specs | 2026-08-10 |
| [media/](media/) | evidence | Demo、GIF、截图与录制说明 | 页面清单、工作日志 | 2026-08-10 |
| [`../architecture/platform-managed-ai-provider.md`](../architecture/platform-managed-ai-provider.md) | implemented | 平台模型 provider、allowlist 和密钥边界 | backend/frontend/deploy tests | 2026-08-04 |

## 维护规则

- 设计文档必须写明证据、目标、非目标、选择、约束、验收和开放问题。
- 重要取舍同步到架构 ADR；实现完成后的稳定结构同步到 `architecture/` 和 `PROJECT-SUMMARY.md`。
- 设计与运行中契约冲突时，以已验证代码/契约为证据，显式修正文档。
- 被替代设计进入归档，不能继续作为当前实施入口。

新建设计从 [TEMPLATE.md](TEMPLATE.md) 复制。
