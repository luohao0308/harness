# 03 Event Sourcing 与 Replay

## 目标

Event Sourcing 把任务状态变化记录为 append-only 事件流。Replay 通过事件序号重建现场，用于审计、恢复和故障定位。

## 使用入口

| 入口 | 动作 |
|---|---|
| `/tasks/:taskId/events` | 查看事件流和 payload 摘要 |
| `/tasks/:taskId` | 查看最新任务状态 |
| Replay 面板 | 选择 sequence 并重放状态 |

## 后端契约

```text
GET  /api/tasks/{task_id}/events
GET  /api/tasks/{task_id}/events/stream
POST /api/tasks/{task_id}/replay
```

## 数据

| 数据 | 作用 |
|---|---|
| `agent_events` | append-only 事件事实源 |
| `task_snapshots` | 重放加速入口 |
| `tasks.last_sequence` | 当前任务最后事件序号 |

## 事件规则

```text
同一 task_id 内 sequence 单调递增。
事件禁止 update。
事件禁止 delete。
SSE 支持 after_sequence。
SSE 支持 Last-Event-ID。
Replay 本身不写历史事件。
Resume 才写 TASK_RESUMED。
```

## 联动

- Task Detail 使用事件流展示运行轨迹。
- Replay 使用事件流恢复指定 sequence 的现场。
- Resume 使用 Replay 结果决定恢复点。
- Observability 从事件和指标中汇总运行状态。

## 验收

- 并发写入 sequence 不冲突。
- 断线重连不丢事件。
- Replay 指定 sequence 返回状态摘要。
- 失败任务返回 failure point。
- 事件流满足审计追踪要求。
