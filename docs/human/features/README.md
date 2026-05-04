# 功能文档目录

本目录按功能拆分平台说明。每个功能文档独立说明目标、入口、后端契约、前端页面、事件数据、联动关系和验收口径。

## 阅读顺序

1. [任务生命周期](./01-task-lifecycle.md)
2. [Planner 与 Executor](./02-planner-executor.md)
3. [Event Sourcing 与 Replay](./03-event-sourcing-replay.md)
4. [Subagent 编排](./04-subagent-orchestration.md)
5. [Docker Sandbox 与 WarmPool](./05-sandbox-warmpool.md)
6. [模型与工具审计](./06-model-tool-audit.md)
7. [Settings 与 Observability](./07-settings-observability.md)
8. [官网、控制台与 OpenAPI 入口](./08-website-console-openapi.md)

## 总联动

```text
官网 -> 控制台 -> 任务 -> Planner -> Executor -> Sandbox / Subagent / Model Gateway -> Event Store -> Result / Replay -> Observability / Settings
```
