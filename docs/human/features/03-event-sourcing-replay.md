# 03 Event Sourcing 与 Replay Spec

## 目标

Event Sourcing 把任务状态变化记录为 append-only 事件流。Replay 通过事件序号重建现场，用于审计、恢复和故障定位。

## 用户可见能力

| 能力 | 入口 | 用户结果 |
|---|---|---|
| 查看事件 | `/tasks/:taskId` | 按 sequence 查看任务事件 |
| 实时事件 | `/tasks/:taskId` | 断线重连后继续读取 |
| 重放现场 | Replay 面板 | 选择 sequence 并重建状态 |
| 定位失败点 | Replay 面板 | 查看失败步骤、工具和错误摘要 |
| 恢复 Worker | Subagent 面板 | 基于 Replay 状态恢复超时或卡住的子 Agent |

## 后端契约

```text
GET  /api/tasks/{task_id}/events
GET  /api/tasks/{task_id}/events/stream
POST /api/tasks/{task_id}/replay
POST /api/tasks/{task_id}/subagents/recover
```

## 前端入口

| 页面 | 数据来源 | 交互 |
|---|---|---|
| `/tasks/:taskId` | Events API、SSE、Replay API | 时间线、Replay 摘要、失败点 |
| `/tasks/:taskId` Subagent 面板 | Subagent Recovery API | 恢复卡住的子 Agent |
| `/tasks/:taskId/events` | Events API、SSE | 事件流查看 |

## 数据模型

| 数据 | 作用 |
|---|---|
| `agent_events` | append-only 事件事实源 |
| `task_snapshots` | 重放加速入口 |
| `agent_events.sequence` | 当前任务最后事件序号 |

## 事件模型

```text
所有 TASK_*、PLAN_*、STEP_*、MODEL_*、TOOL_*、POLICY_*、SANDBOX_*、SUBAGENT_* 事件
```

## 权限模型

| 能力 | 角色 |
|---|---|
| 查看事件 | admin、engineer、operator |
| Replay | admin、engineer、operator |
| Resume | admin、engineer |

## 状态流转

```text
事件写入 -> sequence 递增 -> snapshot 生成 -> replay 重建 -> resume 恢复
```

事件规则：

```text
同一 task_id 内 sequence 单调递增。
事件禁止 update。
事件禁止 delete。
SSE 支持 after_sequence。
SSE 支持 Last-Event-ID。
Replay 本身不写历史事件。
Resume 写入 TASK_RESUMED。
每 100 个事件自动生成 task_snapshots。
Resume 会根据 Replay state 跳过已完成 step。
Subagent recovery 会根据 Replay state 标记超时或重置卡住的 worker。
```

## 外部服务契约

不涉及。

## 观测指标

```text
agent_events_total
agent_task_resume_total
agent_tasks_failed_total
agent_subagent_recovery_total
agent_subagent_recovery_sweeps_total
agent_subagent_recovery_last_recovered
```

## 当前实现状态

| 能力 | 状态 | 证据 |
|---|---|---|
| append-only 事件 | 已落地 | `agent_events` |
| task 内 sequence 单调递增 | 已落地 | Event Store |
| SSE after_sequence | 已落地 | Events stream |
| Last-Event-ID | 已落地 | Events stream |
| 每 100 个事件生成 snapshot | 已落地 | Replay service |
| Replay 从 snapshot 续扫 | 已落地 | Replay service |
| 失败点定位 | 已落地 | Replay response |
| 步骤级恢复执行 | 已落地 | Resume flow |
| Worker 级恢复 | 已落地 | `POST /api/tasks/{task_id}/subagents/recover` |
| Worker 自动巡检 | 基础落地 | `subagent_recovery_worker.recover_stalled_subagents` |
| Worker 跨节点恢复锁 | 基础落地 | PostgreSQL advisory lock 控制同一时间只有一个恢复巡检执行 |
| Worker 恢复指标 | 已落地 | `subagent-recovery:9102/metrics` 输出恢复动作、巡检次数和最近恢复数量 |
| Worker 恢复告警 | 已落地 | `deploy/monitoring/alert-rules.yml` |

## 缺口

| 缺口 | 影响 | 目标 |
|---|---|---|
| Worker 级恢复编排 | 当前已支持恢复锁、超时标记、卡住 worker 重置、巡检函数、Compose 服务、Prometheus 指标和告警规则 | 增强恢复批次详情和控制台展示 |

## 实现顺序

```text
1. 保持事件枚举与 OpenAPI 同步
2. 保持 snapshot 规则与 Replay service 同步
3. 前端展示 sequence、payload 摘要和 failure point
4. 增强恢复批次详情和控制台展示
5. 补并发和断线重连测试
```

## 验收标准

- 并发写入 sequence 不冲突。
- 断线重连不丢事件。
- Replay 指定 sequence 返回状态摘要。
- 失败任务返回 failure point。
- 第 100 个事件生成 task snapshot。
- Resume 后已完成步骤写入 `STEP_SKIPPED`。
- Resume 后只执行未完成步骤和失败步骤。
- Worker 恢复能标记超时 Subagent。
- Worker 恢复能把卡住的 RUNNING Subagent 重置为 `PENDING`。
- Worker 巡检能扫描多个任务的卡住 Subagent。
- Worker 自动巡检必须先获得恢复租约，未获得租约时本轮不修改 Subagent。
- Worker 恢复指标必须出现在 `/metrics`。
- Prometheus 必须加载 `HarnessSubagentRecoveryServiceDown`、`HarnessSubagentRecoverySweepMissing`、`HarnessSubagentRecoveryMarkedTimeout` 和 `HarnessSubagentRecoveryRepeatedReset`。
- 事件流满足审计追踪要求。
