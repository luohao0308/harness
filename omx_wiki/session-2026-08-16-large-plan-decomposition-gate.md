# 大型计划自动拆分与用户确认门

Category: `session-log`

Tags: `workflow`, `ai`, `plan`, `decomposition`, `approval`, `drift-control`

## 目标

防止 AI 在大型、跨模块或高风险长任务中直接进入实现并逐渐偏离目标。大型计划必须先自动拆成有限数量的可验证切片，向用户展示并等待一次确认；确认后按顺序自动推进，只有范围或风险发生实质变化时才重新确认。

## 生效规则

- 用户明确提出大规划、roadmap、多阶段计划，或任务触及高风险契约、迁移、安全、发布边界时，直接触发大型计划门。
- 其他任务若同时具备跨两个以上模块、三个以上顺序阶段、多个独立验收结果、无法在一个专注开发会话内完成等至少两个信号，也触发该门。
- AI 只读核对证据后，把任务拆成 `2-6` 个有序切片，并列出目标结果、修改范围、依赖、验收和回退点。
- 展示后的状态为 `awaiting_user_confirmation`。用户可以批准原拆分，或要求合并、继续拆分、重排、增删范围；确认前不得实现产品代码、修改契约、创建交付 PR 或执行外部变更。
- 确认后计划写入 `docs/plans/` 并标记为 `approved`；同一时间最多一个切片为 `in_progress`，当前切片通过验收并记录证据后自动进入下一切片。
- 新事实只有在实质改变已确认范围、顺序、接口、迁移或风险时才触发重新确认；切片内部的一般实现细节调整不增加确认轮次。

## 轻量交付边界

切片不是微任务清单。每个切片应在一次专注开发会话内交付一个可观察、可验证的结果。默认整个计划仍使用一个短分支和一个 PR，切片映射为可验证提交或检查点；只有独立发布或风险隔离需要时才拆成多个 PR。

## 权威入口

- `AGENTS.md`：Harness 项目级强制规则，明确该门优先于大型任务的自动继续。
- `docs/development/ai/00-execution-protocol.md`：规模判定、展示格式、确认状态和重新确认边界。
- `docs/plans/README.md` 与 `docs/plans/TEMPLATE.md`：计划落盘、切片状态和偏移控制。
- `docs/development/git-github-workflow.md` 与 `CONTRIBUTING.md`：切片到 branch、commit 和 PR 的轻量映射。
- `docs/development/ai/context-index.json`：`large-plan-decomposition` 自动上下文路由。
- `scripts/validate-docs.py`：锁定关键状态词、计划入口和路由，防止流程回归。

## 验证证据

- `python3 scripts/validate-docs.py` 通过，包含大型计划门契约和 brief fixture。
- `python3 scripts/agent-context-brief.py --task "large plan decomposition approval gate"` 只命中 `large-plan-decomposition`，并返回执行协议、计划 README 与模板。
- `python3 -m py_compile scripts/validate-docs.py scripts/agent-context-brief.py` 通过。
- `python3 scripts/check-markdown-links.py` 通过。
- `python3 scripts/test-commit-message-policy.py` 通过 5/5。
- `git diff --check` 通过。

## 结果

后续大型计划不再直接进入长实现。AI 会先给出有限、可审阅的开发切片并等待用户确认；确认后的计划只保持一个活动切片，同时保留自动连续执行，避免把单人 OPC 流程变成逐步审批系统。
