# 10 Observability 与本地化 Spec

## 目标

本文件定义观测运营、本地化和外部观测服务的正式规格。用途是把 Prometheus、Grafana、Loki、OpenTelemetry 和控制台 i18n 从部署配置收敛为可实现、可验收的产品能力。

## 用户可见能力

| 能力 | 用户入口 | 用户结果 |
|---|---|---|
| 运行摘要 | `/observability` | 查看任务、事件、模型、工具、沙箱和 WarmPool 汇总 |
| 指标查看 | `/observability`、`/metrics` | 查看 Prometheus 指标 |
| 仪表盘查看 | `/observability`、Grafana | 查看任务吞吐、失败率、资源和模型工具指标 |
| 日志查看 | `/observability/logs` | 按任务、trace、服务筛选日志 |
| Trace 查看 | `/observability/traces` | 按 trace_id 查看请求链路 |
| 本地化 | 控制台顶栏语言切换 | 中文默认，English 可切换，技术值保留原值并显示说明 |

## 后端契约

已落地：

```text
GET /api/observability/summary
GET /metrics
```

待落地：

```text
GET /api/observability/grafana/dashboards
GET /api/observability/logs
GET /api/observability/traces/{trace_id}
GET /api/observability/services/health
```

## 前端入口

| 页面 | 数据来源 | 交互 |
|---|---|---|
| `/observability` | `GET /api/observability/summary`、`GET /metrics` | 运行摘要和指标 |
| `/observability/logs` | `GET /api/observability/logs` | 日志筛选和详情 |
| `/observability/traces` | `GET /api/observability/traces/{trace_id}` | Trace 查询和 span 列表 |
| `/settings/models` | Settings API | 模型设置 |
| `/settings/policies` | Settings API | 策略设置 |
| 控制台 Shell | i18n 字典 | 中文与 English 切换 |

## 数据模型

| 数据源 | 内容 |
|---|---|
| `tasks` | 任务状态、创建时间、完成时间 |
| `agent_events` | 事件流、sequence、trace_id |
| `model_calls` | 模型供应商、模型名、token、耗时、失败 |
| `tool_calls` | 工具名、输入、输出、耗时、策略结果 |
| `sandbox_instances` | 沙箱状态、资源、网络、WarmPool 复用 |
| Loki stream | JSON 日志、service、trace_id、task_id、agent_run_id |
| Prometheus TSDB | 指标时序 |
| OTel traces | 请求 span、trace_id、span 属性 |

## 事件模型

```text
TASK_CREATED
TASK_STARTED
TASK_FAILED
TASK_COMPLETED
MODEL_CALLED
MODEL_RESPONSE_RECEIVED
MODEL_CALL_FAILED
MODEL_FALLBACK_USED
TOOL_CALLED
TOOL_RESULT_RECEIVED
TOOL_FAILED
TOOL_TIMEOUT
POLICY_CHECKED
POLICY_DENIED
SANDBOX_ALLOCATED
SANDBOX_COMMAND_STARTED
SANDBOX_COMMAND_COMPLETED
SANDBOX_COMMAND_FAILED
```

## 权限模型

| 能力 | 角色 |
|---|---|
| 运行摘要 | admin、engineer、operator |
| 指标查看 | admin、operator |
| 日志查看 | admin、operator |
| Trace 查看 | admin、operator |
| 设置读 | admin、engineer |
| 设置写 | admin |

## 状态流转

```text
运行时事件 -> agent_events / audit tables -> summary API -> 控制台
运行时指标 -> Prometheus -> /metrics -> 控制台摘要
JSON 日志 -> Loki -> logs API -> 控制台日志页
Trace span -> OTel Collector -> traces API -> 控制台 Trace 页
语言选择 -> i18n store -> 字典渲染 -> 页面文案切换
```

## 外部服务契约

| 服务 | 当前入口 | 目标用途 | Harness 后端代理 |
|---|---|---|---|
| Prometheus | `http://127.0.0.1:9091` | 抓取并查询指标 | `GET /metrics` 已落地，查询代理待落地 |
| Grafana | `http://127.0.0.1:3001` | 展示仪表盘 | `GET /api/observability/grafana/dashboards` 待落地 |
| Loki | `http://127.0.0.1:3100` | 查询结构化日志 | `GET /api/observability/logs` 待落地 |
| OpenTelemetry Collector | `http://127.0.0.1:4317`、`http://127.0.0.1:4318` | 接收 trace | `GET /api/observability/traces/{trace_id}` 待落地 |

## 观测指标

```text
agent_tasks_total
agent_tasks_running
agent_tasks_failed_total
agent_task_duration_seconds
agent_task_resume_total
agent_subagents_running
agent_subagents_queued
agent_subagents_failed_total
agent_subagent_duration_seconds
sandbox_containers_total
sandbox_containers_running
sandbox_command_duration_seconds
sandbox_command_timeout_total
warm_pool_idle_containers
warm_pool_busy_containers
warm_pool_hit_total
warm_pool_miss_total
model_calls_total
model_call_duration_seconds
model_call_errors_total
model_tokens_input_total
model_tokens_output_total
```

日志字段：

```text
timestamp
level
service
message
trace_id
task_id
agent_run_id
event_type
request_id
```

禁止写入日志的字段：

```text
secret_value
raw_api_key
full_prompt
raw_sensitive_file_content
authorization_header
cookie
```

本地化规则：

| 项 | 规格 |
|---|---|
| 默认语言 | `zh-CN` |
| 可选语言 | `zh-CN`、`en-US` |
| 切换入口 | 控制台顶栏 |
| 技术值 | 保留原值 |
| 技术值说明 | 相邻显示中文或英文说明 |
| 状态文案 | 使用字典映射，不直接散落在页面 |
| 空状态 | 必须双语 |
| 错误状态 | 必须双语 |
| 表头和按钮 | 必须双语 |

## 当前实现状态

| 能力 | 状态 | 证据 |
|---|---|---|
| 运行摘要 API | 已落地 | `services/api-server/app/api/observability.py` |
| Prometheus 指标 | 已落地 | `services/api-server/app/api/metrics.py` |
| Grafana 容器 | 已落地 | `deploy/docker-compose/docker-compose.yml` |
| Loki 容器 | 已落地 | `deploy/docker-compose/docker-compose.yml` |
| OTel Collector 容器 | 已落地 | `deploy/docker-compose/docker-compose.yml` |
| trace_id 响应头 | 基础落地 | `services/api-server/app/core/tracing.py` |
| Loki 日志采集链路 | 待落地 | 缺日志采集器和 push 链路 |
| Grafana 后端代理 | 待落地 | 缺 `GET /api/observability/grafana/dashboards` |
| Trace 查询 API | 待落地 | 缺 `GET /api/observability/traces/{trace_id}` |
| 全量控制台 i18n | 待落地 | 当前只覆盖 Shell、导航和部分文案 |

## 缺口

| 缺口 | 影响 | 目标 |
|---|---|---|
| Loki 日志采集链路 | 控制台无法查询结构化日志 | 日志进入 Loki 并按 task_id、trace_id 查询 |
| Grafana 后端代理 | 控制台无法读取 dashboard 列表 | 后端返回 dashboard 元数据和深链 |
| OTel Trace 查询 | 控制台无法按 trace_id 看链路 | 后端返回 trace span 列表 |
| 控制台全量 i18n | 部分旧页面仍是英文 | 默认中文，顶栏切换 English |

## 实现顺序

```text
1. 补 Loki 日志采集链路
2. 补 /api/observability/logs 查询接口
3. 补 Grafana dashboard provisioning 与 dashboard 列表接口
4. 补 OTel exporter wiring 与 trace 查询接口
5. 拆分控制台 i18n 字典
6. 覆盖任务、详情、Subagent、沙箱、观测、设置页面双语
7. 更新 OpenAPI、控制台页面和验收测试
```

## 验收标准

- `GET /api/observability/summary` 返回任务、模型、工具、沙箱和 WarmPool 汇总。
- `GET /metrics` 暴露 Prometheus 指标。
- Prometheus targets 中 `api-server` 为 up。
- Grafana health 返回 ok。
- Loki ready 返回 ready。
- Loki labels 查询返回 success。
- API JSON 日志能按 `trace_id` 查询。
- 事件中的 `trace_id` 与响应头 `x-trace-id` 能关联。
- 控制台切换 English 后页面表头、按钮、空状态和错误状态切换为英文。
- 技术值保留原始值，并显示当前语言说明。
