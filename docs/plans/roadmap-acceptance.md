# 08 交付路线与验收

## 版本路线

```text
阶段 0：文档、原型、架构图
阶段 1：任务执行闭环
阶段 2：Subagent 异步编排
阶段 3：Docker Sandbox + WarmPool
阶段 4：监控、部署、安全加固
阶段 5：企业化能力
```

## 阶段 1：任务执行闭环

功能：

- 创建任务
- Planner 生成任务计划
- Executor 执行计划
- Event Store 持久化事件
- 查询任务状态
- 查询任务事件
- 控制台展示执行轨迹

验收：

- 用户创建任务成功。
- 系统生成计划。
- 系统执行至少 2 个步骤。
- 每个关键动作都有事件记录。
- 页面实时展示事件流。
- 任务最终进入 COMPLETED 或 FAILED。

## 阶段 2：Subagent

功能：

- 创建 Subagent
- 异步执行子任务
- 并发控制，固定上限 5
- 状态追踪
- 超时处理
- 子任务结果回传主任务

验收：

- 主任务派生 Subagent。
- Subagent 状态从 PENDING 到 RUNNING 到 SUCCESS/FAILED/TIMEOUT。
- 超过并发限制的 Subagent 进入 PENDING。
- 超时任务进入 TIMEOUT。
- 所有状态变化写入 Event Store。

## 阶段 3：Docker Sandbox + WarmPool

功能：

- Docker 容器执行命令
- workspace 挂载
- CPU/内存限制
- 网络关闭
- stdout/stderr 捕获
- 容器销毁
- WarmPool 预热容器
- WarmPool 命中统计

验收：

- 高风险工具在沙箱执行。
- Agent 命令不在宿主机执行。
- 沙箱命令超时后被终止。
- WarmPool 命中获取耗时小于 50ms。
- 沙箱生命周期事件完整记录。

## 阶段 4：部署、监控、安全

功能：

- Docker Compose 部署
- systemd 服务托管
- Nginx HTTPS
- Prometheus 指标
- Grafana 看板
- Loki 日志
- 基础认证
- RBAC
- 模型密钥配置
- 工具权限策略

验收：

- Docker Compose 启动测试环境。
- 服务异常退出后自动恢复。
- Grafana 展示任务、队列、沙箱和模型指标。
- 管理员查看审计日志。
- 普通用户无法调用未授权工具。

## 阶段 5：企业化

功能：

- 多组织
- 多用户
- 项目空间
- API Key 管理
- 完整 RBAC
- 审计导出
- 模型供应商管理
- 私有模型接入
- 任务模板
- 工具插件系统
- Webhook
- 成本统计
- 备份与恢复

验收：

- 多团队数据隔离。
- 管理员控制模型、工具和资源。
- 审计日志导出。
- 平台在客户环境部署。
- 安装、升级、回滚、排障文档齐全。

## 六周交付计划

第 1 周：

- 文档与架构定稿
- Figma 核心稿
- 后端项目骨架

第 2 周：

- Task 表
- Event 表
- create task API
- mock Planner

第 3 周：

- Executor
- Tool Registry
- 基础 ReAct 循环
- 任务详情页

第 4 周：

- Dramatiq Subagent
- 并发控制
- 超时与失败处理

第 5 周：

- Docker Sandbox
- 命令执行
- 资源限制
- 沙箱事件

第 6 周：

- WarmPool
- Prometheus 指标
- Grafana 看板
- Docker Compose 演示环境
