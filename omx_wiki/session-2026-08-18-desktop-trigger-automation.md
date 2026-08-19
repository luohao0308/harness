# Desktop Trigger 与后台自动化

日期：2026-08-18
任务：`DESK-004`
状态：completed

## 结果

Desktop 自动化现支持 Webhook、定时、文件变化和 Git 提交四类 Trigger。所有来源先创建持久化 invocation，再绑定同一个可审计 Run；重复事件、后台重试和用户恢复不会复制 Run。Agent Studio 与 Desktop 操作入口可创建、启停、软删除并查看最近调用，Webhook secret 仅在创建后显示一次。

## 可靠性与安全边界

- `trigger_invocations` 保存配置/来源摘要、状态、attempt、Run 绑定、租约、fencing generation 和错误摘要；`(trigger_id, idempotency_key)` 保证稳定重放。
- SQLite local profile 使用 runtime jobs，server profile 使用 durable outbox/Dramatiq；租约、过期回收、重试和终态同步保持在各自运行边界内。
- 全局 kill switch、Trigger 禁用和软删除在每个执行步骤前检查；审批、取消和恢复继续复用 Run/Event/Policy/Approval。
- file/git 只接受可信 Desktop 选择器返回并持久化到 invocation 的 workspace；server profile、无 workspace、目录逃逸、Shell/Git/sandbox/subagent 旁路均 fail closed。
- Agent Run 的 execute/resume/approval continuation 重新进入 invocation service；step-selective resume 和三类 orchestration 入口拒绝 Trigger-owned Run，避免绕过租约与安全门。
- API 响应不暴露 runtime state 或绝对路径，Webhook payload 只保存有界摘要；goal/title、扫描文件数、字节数、observation 和 hash 缓存均有上限。

## 验证

- 后端：全量 `1614 passed, 3 warnings`；Ruff `app tests` 全绿。Trigger 定向回归 `147 passed`，新增 orchestration/resume 旁路测试通过。
- 数据库：Trigger migration `5 passed`；SQLite upgrade 到 `20260817_0051`、downgrade 到 `20260807_0050`、再 upgrade 到 head 通过；Alembic 单头为 `20260817_0051`。
- Console：自动化 `4 files / 9 tests`，lint 和 production build 通过；创建 schedule/file/git 的真实请求体有断言。
- Desktop：`40 files / 337 tests` 与 `npm run type-check` 通过；preload workspace 选择契约有覆盖。
- 部署与契约：Docker Compose config 通过；OpenAPI reference、主 JSON/YAML 和官网 JSON/YAML 包含 Trigger invocation 列表/详情且副本一致。
- 浏览器：宽屏与 390px 窄屏无 document 级横向溢出；Webhook 创建、一次性密钥、暂停/历史入口和 schedule/file/git 表单可见，浏览器错误日志为空。
- 文档：Feature Catalog 生成/校验、`validate-docs.py` 和 `git diff --check` 通过。

## 最终独立复审修复

独立复审未发现实际 Trigger-owned Run 绕过，但指出 execute、step-selective resume 和审批 continuation 缺少直接端点回归。收尾补充了三项测试，并保留原 busy-lease 事务回滚测试：Trigger-owned `/runs/{id}/execute` 只调用 invocation executor；`/steps/resume` 返回 409；审批续跑成功调用 invocation executor，busy lease 时 approval/tool/task 状态保持原值且不调用裸 Executor。

原 busy-lease 测试最初会先被缺少 workspace 的安全门拒绝，独立复审识别出该假阳性。修复后测试使用真实临时 workspace、file Trigger 和 local profile，断言 `ToolRunner` 已执行、409 原因为 `already executing`，并验证 task、approval、tool call 与 lease owner 全部回滚。`tests/test_triggers.py` 与 `tests/test_tool_approvals.py` 完整重跑为 `32 passed, 3 warnings`，Ruff、Compose config、docs validation 和 `git diff --check` 通过；最终独立复审结论为 PASS。

## 回退与剩余风险

运行问题优先关闭 `TRIGGER_AUTOMATION_ENABLED`，配置、invocation 和 Run 历史保留。Schema downgrade 只应在确认没有新类型或 invocation 数据后执行。正式签名 macOS/Windows/Linux 包内 Electron smoke 仍由 `REL-001` 跟踪；没有本地证据被当作三平台 Release 证据。

路线已推进到 `DESK-005` 项目知识自动索引，`REL-001` 继续暂停/阻塞。
