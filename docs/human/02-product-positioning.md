# 02 产品定位

## 一句话定位

生产级企业 AI Agent Harness 平台，将大模型能力工程化为具备审计、恢复、隔离、并发编排和私有化部署能力的企业任务执行系统。

## 核心公式

```text
Model + Harness = Agent
```

Model 负责自然语言理解、推理、规划和生成。Harness 层负责工程执行系统，包括：

- Planner 任务分解
- Executor 执行引擎
- Subagent 异步编排
- Tool Registry 工具注册
- Policy Engine 策略控制
- Event Store 事件溯源
- Docker Sandbox 容器隔离
- WarmPool 预热池
- Observability 监控、日志、追踪
- Deployment 私有化部署

## 产品目标

平台面向企业内部复杂自动化任务。平台提供受控 Agent Runtime，让企业在私有化环境中运行 AI Agent，并满足工程可靠性、安全隔离、审计合规和持续运维要求。

## 核心卖点

### Harness 工程层

平台不做简单 Prompt 封装。平台构建完整 Harness 层，把模型输出转化为受控执行、可追踪状态和可恢复任务。

### Planner + Executor + Subagent

任务由 Planner 拆成结构化步骤，Executor 负责同步 ReAct 执行，Subagent 负责异步长任务和并发探索任务。

```text
User Goal
-> Planner
-> Execution Plan
-> Executor
-> Tools / Sandbox / Subagents
-> Event Stream
-> Result
```

### Event Sourcing

所有关键动作写入事件流。事件流支撑审计日志、断点恢复、时间旅行调试和问题复盘。

### Docker Sandbox

命令执行、文件处理、测试运行和高风险工具调用全部进入 Docker 容器。平台限制 CPU、内存、网络、文件系统和执行时间。

### WarmPool

平台维护预热容器池。常规沙箱冷启动目标为 100-500ms，WarmPool 获取目标为 50ms 内。

### 企业交付

平台交付形态为 Docker Compose + systemd + Nginx + Prometheus + Grafana + Loki。首个交付版不包含 Kubernetes。

## 目标用户

- 企业研发平台团队
- DevOps 团队
- SRE 团队
- AI 平台团队
- 安全与合规团队
- 需要私有化 Agent 能力的软件公司

## 典型场景

- 代码仓库分析、修复和测试
- CI/CD 失败诊断
- 运维日志分析
- 安全基线审计
- 内部知识任务执行
- 数据清洗和报告生成
- 多 Agent 长周期工程任务

## 正式官网文案

主标题：

```text
生产级企业 AI Agent Harness 平台
```

副标题：

```text
通过 Planner、Executor、Subagent、Event Sourcing、Docker Sandbox 和 WarmPool，将大模型转化为企业级任务执行系统。
```

核心能力：

```text
Planner 任务规划
ReAct Executor 执行引擎
Subagent 异步编排
Event Sourcing 审计恢复
Docker Sandbox 容器隔离
WarmPool 毫秒级启动
Prometheus/Grafana/Loki 生产监控
```

## 禁止表达

正式材料禁止使用“还原 local Agent CLI”作为主宣传语。内部技术材料使用以下表述：

```text
参考现代 Agentic Coding 产品的 Planner、Executor、Subagent、事件流和工具执行范式，构建面向企业私有化场景的 AI Agent Harness 平台。
```
