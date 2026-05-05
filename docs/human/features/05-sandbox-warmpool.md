# 05 Docker Sandbox 与 WarmPool Spec

## 目标

Docker Sandbox 承接高风险工具执行，提供容器级隔离。WarmPool 通过预热容器降低启动耗时。

## 用户可见能力

| 能力 | 入口 | 用户结果 |
|---|---|---|
| 查看沙箱 | `/sandboxes` | 查看容器实例、状态和资源 |
| 查看 WarmPool | `/sandboxes` | 查看 idle、busy、hit、miss |
| 查看任务沙箱 | `/tasks/:taskId` | 查看任务关联的沙箱事件 |
| 终止沙箱 | `/sandboxes` | 停止指定沙箱 |

## 后端契约

```text
GET  /api/sandboxes
GET  /api/sandboxes/warm-pool
GET  /api/sandboxes/{sandbox_id}
POST /api/sandboxes/{sandbox_id}/terminate
```

## 前端入口

| 页面 | 数据来源 | 交互 |
|---|---|---|
| `/sandboxes` | Sandbox API、WarmPool API | 列表、详情、终止 |
| `/tasks/:taskId` | Events API、Tool Audit | 查看任务沙箱事件 |

## 数据模型

| 数据 | 作用 |
|---|---|
| `sandbox_instances` | 沙箱实例、状态、资源、网络、WarmPool 复用 |
| `tool_calls` | 沙箱工具执行审计 |
| `agent_events` | 沙箱分配、命令和失败事件 |
| `system_settings` | 沙箱默认网络和超时策略 |

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
```

## 当前实现状态

| 能力 | 状态 | 证据 |
|---|---|---|
| Docker SDK 创建容器 | 已落地 | Docker manager |
| 默认网络关闭 | 已落地 | Sandbox policy |
| Settings 控制默认网络 | 已落地 | `settings.policies.sandbox.default_network` |
| Settings 控制默认命令超时 | 已落地 | `settings.policies.sandbox.default_timeout_seconds` |
| WarmPool 预热 | 已落地 | WarmPool API |
| 非默认网络绕过 WarmPool | 已落地 | Sandbox Manager |

## 缺口

| 缺口 | 影响 | 目标 |
|---|---|---|
| 容器资源规格动态配置 | 企业租户资源治理仍需增强 | Settings 下发 memory、cpu、workspace quota |
| 网络 allowlist | 网络访问策略仍需增强 | 按组织配置域名和地址白名单 |

## 实现顺序

```text
1. 固化 Sandbox API 与 WarmPool API
2. 扩展 Settings 沙箱资源字段
3. 增加网络 allowlist 策略
4. 补沙箱资源与网络测试
5. 控制台展示资源和策略说明
```

## 验收标准

- 高风险工具不在宿主机执行。
- 文件写入限制在 task workspace。
- 网络默认关闭。
- 策略打开网络后创建网络沙箱。
- 命令超时后终止。
- 命令默认超时来自 Settings。
- WarmPool 状态在 API 进程重启后不丢失。
- WarmPool benchmark 覆盖获取耗时。
