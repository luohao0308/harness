# 功能文档目录

本目录按功能拆分平台 Spec。每个功能文档必须使用统一结构，独立说明目标、用户能力、后端契约、前端入口、数据模型、事件模型、权限模型、状态流转、外部服务、观测指标、当前实现、缺口、实现顺序和验收标准。

全局入口：

- [Harness 正式规格总入口](../product-spec.md)
- [Spec 功能索引](../../contracts/SPEC-INDEX.md)
- [Spec 模板](../../contracts/SPEC-TEMPLATE.md)

## 阅读顺序

1. [任务生命周期](./01-task-lifecycle.md)
2. [Planner 与 Executor](./02-planner-executor.md)
3. [Event Sourcing 与 Replay](./03-event-sourcing-replay.md)
4. [Subagent 编排](./04-subagent-orchestration.md)
5. [Docker Sandbox 与 WarmPool](./05-sandbox-warmpool.md)
6. [模型与工具审计](./06-model-tool-audit.md)
7. [Settings 与 Observability](./07-settings-observability.md)
8. [官网、控制台与 OpenAPI 入口](./08-website-console-openapi.md)
9. [实现覆盖与缺口](./09-implementation-coverage.md)
10. [Observability 与本地化规格](./10-observability-localization-spec.md)

## 标准结构

```text
目标
用户可见能力
后端契约
前端入口
数据模型
事件模型
权限模型
状态流转
外部服务契约
观测指标
当前实现状态
缺口
实现顺序
验收标准
```

## 总联动

```text
官网 -> 控制台 -> 任务 -> Planner -> Executor -> Sandbox / Subagent / Model Gateway -> Event Store -> Result / Replay -> Observability / Settings
```

## 当前覆盖

| 能力 | 后端状态 | 前端状态 |
|---|---|---|
| 任务生命周期 | 接口已落地 | 页面已接入 |
| 计划与执行 | Planner、Executor、同步步骤、异步派生和 Worker 接管已落地 | 计划面板已接入 |
| 事件流 | REST 与 SSE 已落地 | 时间线已接入 |
| Replay | Snapshot、Replay、步骤恢复和 Worker 恢复已落地 | 摘要面板已接入 |
| Subagent | 查询、创建、取消、恢复和结果聚合已落地 | 列表页、任务页与详情页已接入 |
| 沙箱治理 | Sandbox 与 WarmPool 接口已落地 | 沙箱页已接入 |
| 模型与工具审计 | 审计表与查询已落地 | 面板已接入 |
| Settings | 持久化读写已落地 | 设置页已接入 |
| Observability | Prometheus 指标、深度观测接口、导出留存和队列摘要已落地 | 运营页已接入 |
| Loki / Grafana / OTel | 日志、Dashboard、Trace、服务健康接口和 provisioning 已落地 | 观测页已接入 |
| 控制台本地化 | 默认中文与 English 切换已落地 | Shell、主要页面与子 Agent 详情页已接入 |
