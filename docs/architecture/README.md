# 架构文档导航

_状态：active | 权威范围：稳定架构与代码组织 | 更新：2026-08-10 | 读取方式：按任务选择章节_

本目录记录从代码、配置、测试和运行事实中确认的稳定架构。实时任务状态看 `docs/TASKS.md`，当前方案看 `docs/design/`，操作步骤看 `docs/project-memory/` 或 `docs/operations/`。

## 文档地图

| 文档 | 内容 | 何时更新 |
|---|---|---|
| [SYSTEM.md](SYSTEM.md) | 系统上下文、仓库/运行拓扑、关键数据流和信任边界 | 系统边界、部署形态或核心流变化时 |
| [MODULES.md](MODULES.md) | 模块职责、依赖方向、入口和所有权 | 新增模块或模块边界变化时 |
| [MODULE-INDEX.md](MODULE-INDEX.md) | 代码模块到权威规格的生成索引 | `module-map.json` 变化后重新生成 |
| [DECISIONS.md](DECISIONS.md) | 重要架构决策及其状态 | 作出或替代长期技术决策时 |
| [adr/](adr/) | ADR 原文与历史决策序列 | 新增或替代长期技术决策时 |
| [system-architecture-spec.md](system-architecture-spec.md) | Agent 平台运行链、服务、状态机和数据规则 | 核心系统行为变化时 |
| [agent-runtime-spec.md](agent-runtime-spec.md) | Planner、Executor、Subagent 和多 Agent 编排 | Agent 执行语义变化时 |
| [backend-runtime.md](backend-runtime.md) | 后端服务、数据、API 和运行时说明 | 后端技术栈或服务职责变化时 |
| [terminal-architecture.md](terminal-architecture.md)、[websocket-architecture.md](websocket-architecture.md) | Terminal 与 WebSocket 边界 | 实时通信或本地终端变化时 |
| [security/threat-model.md](security/threat-model.md) | 威胁模型和安全边界 | 认证、授权、密钥或信任边界变化时 |
| [platform-managed-ai-provider.md](platform-managed-ai-provider.md)、[team-mode-product-surface.md](team-mode-product-surface.md) | 模型 provider 与 Team 稳定架构 | 对应能力边界变化时 |
| [SUBPROJECT-AGENTS-TEMPLATE.md](SUBPROJECT-AGENTS-TEMPLATE.md) | 子项目局部 `AGENTS.md` 模板 | 子目录有独立技术栈、命令或所有权时 |

## 维护规则

- 只记录已经由代码或运行证据确认的稳定事实；推测标记为 Unknown。
- 架构图必须配套文字说明和源文件入口，不能只保留图片。
- 数量、端口、版本和拓扑等动态值注明更新时间；线上状态操作前重新验证。
- 被替代的决策保留历史状态和替代链接，不静默重写原因。
- 当前架构规格、稳定结构、依赖方向和决策均以本目录为权威；历史蓝图在 `docs/工作日志/archive/`。
