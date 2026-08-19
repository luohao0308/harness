# Desktop Trigger 契约盘点与修订确认门

日期：2026-08-17
任务：`DESK-004`
状态：awaiting_user_confirmation

## 盘点结果

现有 Trigger 是 Webhook-only 的窄实现：可按 Agent 创建、列表、启停和删除，secret 只在创建时返回。公共 Webhook 调用会同步创建一个带 `TASK_CREATED`、`TRIGGER_INVOKED`、`PLAN_REQUESTED`、`PLAN_GENERATED` 事件的 Run，但 Run 停在 `PLANNED`，重复请求会重复创建 Run。

现有本地 `RuntimeJobCoordinator` 已具备 SQLite active dedupe、租约、heartbeat、fencing、重试、取消和过期恢复；server profile 通过 Dramatiq/Redis 执行后台任务。当前两者都没有用户可配置的定时、文件或 Git Trigger，也没有 Trigger invocation/history。

## 修订边界

完整 `DESK-004` 需要扩展 `triggers`，并新增 `trigger_invocations` 作为配置快照、幂等键、状态和 Run 关联的权威资源。现有公开 Trigger API 需要保持 Webhook 兼容并 additive 扩展其他类型、幂等 header 和 invocation 查询。数据库迁移与对外 API 均属于已批准路线明确要求重新确认的变化，因此实现暂停在确认门，尚未修改产品代码或 Schema。

修订后的顺序为：持久化契约；可靠调用与同 Run 重试；local profile 的定时、受控文件和 Git 来源；Agent Studio/Desktop 管理与历史。全局 kill switch 停止新调用和调度但保留配置、invocation 与 Run；文件/Git 在 server profile fail closed；受控工具仍走既有 Policy/Approval，不由 Trigger 自动批准。

## 下一步

用户确认迁移与 API 扩展后恢复 `DESK-004` 为 `in_progress`，从 Alembic 双数据库 upgrade/downgrade 与现有 Webhook 回填测试开始，随后按修订链自动推进。
