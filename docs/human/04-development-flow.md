# 04 研发流程

## 阶段 1：产品与设计定稿

产出：

- 产品定位
- 官网首页文案
- 控制台页面结构
- 核心架构图
- Figma 五个核心页面

Figma 页面固定为：

```text
官网首页
架构说明页
控制台任务列表
控制台任务详情
事件流与 Subagent 面板
```

Gemini/H5 产物只承担视觉参考和文案参考。生产前端全部由 Next.js 与 React 组件实现。

## 阶段 2：后端骨架

建立：

```text
services/api-server
PostgreSQL 16
Redis 7
FastAPI
SQLAlchemy 2.0
Alembic
Pydantic v2
Dramatiq
```

实现：

```text
POST /api/tasks
GET  /api/tasks
GET  /api/tasks/{task_id}
GET  /api/tasks/{task_id}/events
```

验收：

- 任务写入数据库。
- TASK_CREATED 事件写入事件表。
- 事件查询按 sequence 升序返回。

## 阶段 3：Planner

Planner 输出结构化 JSON 计划。开发闭环阶段使用 mock Planner，集成演示版接入 OpenAI-compatible Model Gateway。

验收：

- 输入目标后生成 3-5 个步骤。
- PLAN_GENERATED 写入事件流。
- plan_json 写入 execution_plans 表。

## 阶段 4：Executor

Executor 实现同步 ReAct 执行循环：

```text
Load State
-> Reason
-> Act
-> Observe
-> Write Event
-> Update State
-> Continue / Finish
```

验收：

- 步骤进入 STEP_STARTED。
- 工具调用进入 TOOL_CALLED。
- 工具结果进入 TOOL_RESULT_RECEIVED。
- 成功步骤进入 STEP_COMPLETED。
- 失败步骤进入 STEP_FAILED。
- 任务进入 COMPLETED 或 FAILED。

## 阶段 5：控制台

控制台实现：

- 任务列表
- 创建任务
- 任务详情
- 执行计划
- 实时事件流
- Subagent 面板
- Sandbox 面板

验收：

- 页面创建任务。
- 页面展示计划。
- 页面通过 SSE 接收事件。
- 页面展示最终结果。

## 阶段 6：Subagent

Subagent 使用 Dramatiq worker 执行。Redis 作为 broker。最大并发固定为 5。

验收：

- 主任务派生 Subagent。
- 状态完整流转。
- 超时任务进入 TIMEOUT。
- 状态变化全部写入事件流。

## 阶段 7：Docker Sandbox

工具执行进入 Docker 容器。shell、测试、文件处理和包安装全部通过 Sandbox Manager。

验收：

- 宿主机不直接执行 Agent 命令。
- 命令 stdout/stderr 被捕获。
- CPU、内存、网络、超时被限制。
- 沙箱生命周期事件完整写入。

## 阶段 8：WarmPool

WarmPool 管理预热容器。低风险任务复用预热容器，高风险任务使用一次性容器。

验收：

- WarmPool 命中获取耗时小于 50ms。
- 归还容器完成工作区清理。
- 脏容器销毁重建。
- warm_pool_hit_total 和 warm_pool_miss_total 有指标。

## 阶段 9：部署与监控

交付：

- Dockerfile
- docker-compose.yml
- systemd service
- Nginx 配置
- Prometheus 配置
- Grafana Dashboard
- Loki 日志配置

验收：

- Docker Compose 启动完整环境。
- systemd 托管服务自动重启。
- Nginx 提供 HTTPS 反向代理。
- Grafana 展示任务、队列、沙箱和模型指标。
- Loki 查询结构化日志。
