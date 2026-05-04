# 05 Docker Sandbox 与 WarmPool

## 目标

Docker Sandbox 承接高风险工具执行，提供容器级隔离。WarmPool 通过预热容器降低启动耗时。

## 使用入口

| 入口 | 动作 |
|---|---|
| `/sandboxes` | 查看沙箱实例和 WarmPool |
| `/tasks/:taskId` | 查看任务相关 Sandbox |

## 后端契约

```text
GET  /api/sandboxes
GET  /api/sandboxes/warm-pool
GET  /api/sandboxes/{sandbox_id}
POST /api/sandboxes/{sandbox_id}/terminate
```

## 沙箱默认值

```text
memory=1024m
cpus=1.0
network=none
user=non-root
timeout=per-command
workspace=/workspace
```

## WarmPool

```text
WARM_POOL_ENABLED=true
WARM_POOL_MIN_SIZE=3
WARM_POOL_MAX_SIZE=10
WARM_POOL_IDLE_TTL_SECONDS=600
WARM_POOL_CONTAINER_IMAGE=agent-runtime:latest
目标获取耗时：50ms 内
```

## 联动

- Tool Registry 标记工具风险等级。
- Policy Engine 决定是否允许工具执行。
- 高风险工具进入 Docker Sandbox。
- WarmPool 提供低风险任务的预热容器。
- Sandbox 事件进入 Event Store。
- Sandbox 指标进入 Prometheus。

## 验收

- 高风险工具不在宿主机执行。
- 文件写入限制在 task workspace。
- 网络默认关闭。
- 命令超时后终止。
- WarmPool 状态在 API 进程重启后不丢失。
- WarmPool benchmark 覆盖获取耗时。
