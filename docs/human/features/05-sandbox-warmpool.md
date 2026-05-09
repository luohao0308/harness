# 05 Docker Sandbox 与 WarmPool Spec

## 目标

Docker Sandbox 承接高风险工具执行，提供容器级隔离。WarmPool 通过预热容器降低启动耗时。

## 用户可见能力

| 能力 | 入口 | 用户结果 |
|---|---|---|
| 查看沙箱 | `/sandboxes` | 查看容器实例、状态和资源 |
| 查看 WarmPool | `/sandboxes` | 查看 idle、busy、hit、miss |
| 查看 Run 沙箱 | `/runs/:runId` | 查看 Run 关联的沙箱事件 |
| 终止沙箱 | `/sandboxes` | 停止指定沙箱 |
| 查看配额用量 | `/sandboxes` | 查看当前组织 CPU、内存、网络和工作区配额 |
| 查看配额历史 | `/sandboxes` | 查看沙箱规格、生命周期和 WarmPool 复用审计 |

## 后端契约

```text
GET  /api/sandboxes
GET  /api/sandboxes/quota/usage
GET  /api/sandboxes/quota/history
GET  /api/sandboxes/warm-pool
GET  /api/sandboxes/{sandbox_id}
POST /api/sandboxes/{sandbox_id}/terminate
```

## 前端入口

| 页面 | 数据来源 | 交互 |
|---|---|---|
| `/sandboxes` | Sandbox API、WarmPool API、Quota API | 列表、详情、终止、配额摘要和历史审计 |
| `/runs/:runId` | Events API、Tool Audit | 查看 Run 沙箱事件 |

## 数据模型

| 数据 | 作用 |
|---|---|
| `sandbox_instances` | 沙箱实例、状态、资源、网络、WarmPool 复用 |
| `tool_calls` | 沙箱工具执行审计 |
| `agent_events` | 沙箱分配、命令和失败事件 |
| `system_settings` | 沙箱默认网络、超时、资源规格、工作区配额和网络白名单策略 |

## 事件模型

```text
SANDBOX_ALLOCATED
SANDBOX_COMMAND_STARTED
SANDBOX_COMMAND_COMPLETED
SANDBOX_COMMAND_FAILED
TOOL_TIMEOUT
POLICY_DENIED
```

## 权限模型

| 能力 | 角色 |
|---|---|
| 查看沙箱 | admin、engineer、operator |
| 终止沙箱 | admin、operator |
| 修改沙箱策略 | admin |

## 状态流转

```text
CREATED -> RUNNING -> IDLE
IDLE -> BUSY -> IDLE
RUNNING -> TERMINATED
RUNNING -> FAILED
```

## 外部服务契约

| 服务 | 用途 |
|---|---|
| Docker Engine | 创建、复用、终止容器 |
| Redis 7 | worker 队列协同 |
| Prometheus | 采集 Sandbox 与 WarmPool 指标 |

## 观测指标

```text
sandbox_containers_total
sandbox_containers_running
sandbox_command_duration_seconds
sandbox_command_timeout_total
warm_pool_idle_containers
warm_pool_busy_containers
warm_pool_hit_total
warm_pool_miss_total
sandbox_memory_limit_mb_total
sandbox_running_memory_limit_mb_total
sandbox_cpu_limit_total
sandbox_running_cpu_limit_total
sandbox_network_enabled_total
sandbox_warm_pool_reused_total
```

## 当前实现状态

| 能力 | 状态 | 证据 |
|---|---|---|
| Docker SDK 创建容器 | 已落地 | Docker manager |
| 默认网络关闭 | 已落地 | Sandbox policy |
| Settings 控制默认网络 | 已落地 | `settings.policies.sandbox.default_network` |
| Settings 控制默认命令超时 | 已落地 | `settings.policies.sandbox.default_timeout_seconds` |
| Settings 控制资源规格 | 已落地 | `settings.policies.sandbox.memory_mb`、`cpus`、`workspace_quota_mb` |
| Settings 控制网络白名单 | 已落地 | `settings.policies.sandbox.network_allowlist` |
| Docker 动态资源下发 | 已落地 | Docker `mem_limit`、`nano_cpus` 和 sandbox 事件载荷 |
| 网络请求白名单拦截 | 已落地 | `network_request` 执行前按组织策略校验 host |
| WarmPool 预热 | 已落地 | WarmPool API |
| 非默认网络绕过 WarmPool | 已落地 | Sandbox Manager |
| 非默认资源绕过 WarmPool | 已落地 | 自定义 memory、cpu、workspace quota 或 allowlist 时创建专用沙箱 |
| 配额用量统计 | 已落地 | `GET /api/sandboxes/quota/usage` 返回策略配置、总沙箱数、运行中用量、CPU、内存、网络和 WarmPool 复用 |
| 配额历史审计 | 已落地 | `GET /api/sandboxes/quota/history` 返回最近沙箱规格、生命周期和销毁时间 |
| 配额指标 | 已落地 | `/metrics` 输出 sandbox quota gauge，Grafana Dashboard 展示 Sandbox Quota 面板 |

## 缺口

| 缺口 | 影响 | 目标 |
|---|---|---|
| 资源配额留存审计 | 已落地，配额摘要、历史审计、指标和控制台页面均已接入 | 保持配额查询与页面验收 |

## 实现顺序

```text
1. 固化 Sandbox API 与 WarmPool API
2. 固化配额用量统计
3. 固化资源历史审计
4. 控制台展示资源和策略说明
```

## 验收标准

- 高风险工具不在宿主机执行。
- 文件写入限制在 task workspace。
- 网络默认关闭。
- 策略打开网络后创建网络沙箱。
- 命令超时后终止。
- 命令默认超时来自 Settings。
- 容器 memory 和 cpu 来自 Settings。
- 沙箱事件记录 `workspace_quota_mb` 和 `network_allowlist`。
- `network_request` 目标 host 不在 allowlist 时返回策略拒绝。
- 自定义资源规格不得复用默认 WarmPool 容器。
- WarmPool 状态在 API 进程重启后不丢失。
- WarmPool benchmark 覆盖获取耗时。
- `/api/sandboxes/quota/usage` 必须返回策略配置和运行中资源用量。
- `/api/sandboxes/quota/history` 必须返回沙箱规格与生命周期。
- Grafana 必须展示 Sandbox Quota 面板。
