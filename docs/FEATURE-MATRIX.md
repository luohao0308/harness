<!-- AUTO-GENERATED from docs/development/ai/feature-catalog.json — do not hand-edit -->
<!-- Regenerate: python3 scripts/feature_catalog.py --generate -->

# Harness 功能矩阵

目录版本：`1` · 更新：`2026-08-19` · 领域：`8` · 能力：`14` · 具体功能：`46`

实现统计：已验证 `45` · 进行中 `1` · 其他 `0`

> 实现状态和生产成熟度是两个维度：`verified` 不等于 `production_ready`，本目录不使用人工百分比。

## 领域概览

| 领域 | 能力数 | 具体功能数 | 已验证 | 进行中 | 主要成熟度 | 开放缺口 |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| `agent-runtime` Agent Runtime | 2 | 7 | 7 | 0 | production_candidate | 真实 provider 验证依赖受控凭据和外部服务状态。 |
| `capabilities` Tools、MCP 与 Sandbox | 2 | 6 | 6 | 0 | production_candidate | Docker socket和生产运行时权限仍需按部署环境审查。; 真实外部 MCP 联调依赖对应 provider 凭据和端点。 |
| `desktop-and-mobile` Desktop、Terminal 与 Mobile | 2 | 9 | 9 | 0 | production_candidate | operation_id + phase 的并发幂等使用应用层查重，尚无数据库唯一约束。; 正式签名 macOS/Windows/Linux 包内的 Electron smoke 仍由 REL-001 跟踪；本地无签名 package 证据不替代该发布门。; 正式签名三平台 Electron smoke 仍由 REL-001 跟踪。; 正式签名三平台包内的 Electron smoke 仍随 REL-001 的 Release runner 环境补证。 |
| `enterprise-security` Enterprise Security 与 Deployment | 2 | 6 | 5 | 1 | beta, production_candidate | 正式 macOS/Windows/Linux Release runner 证据尚未完成；本地冷缓存 P95 曾超预算。 |
| `knowledge-context` Knowledge 与 Context | 2 | 6 | 6 | 0 | production_candidate | 真实 Tavily 联调依赖受控第三方凭据。 |
| `quality-trace` Events、Eval 与 Observability | 2 | 5 | 5 | 0 | production_candidate | OPS-001 的 Tempo + Loki 端到端关联证据仍待环境具备。 |
| `teams` Team Orchestration | 1 | 3 | 3 | 0 | production_candidate | — |
| `workspace-console` Workspace 与控制台 | 1 | 4 | 4 | 0 | production_candidate | — |

## 具体功能

| ID | 功能 | 实现状态 | 成熟度 | 支持端 | 验收标准 | 证据 | 已知缺口 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `agent-definition` | Agent Runtime / Agent 生命周期 / Agent 创建与配置 | `verified` | `production_candidate` | `api, web` | 配置保存后可在 Workspace 创建 Run。；无效配置被拒绝并显示可诊断错误。 | `integration:passed` | — |
| `agent-run-creation` | Agent Runtime / Agent 生命周期 / Agent Run 创建 | `verified` | `production_candidate` | `api, web, desktop` | 创建成功后可沿 run、task、trace 关联查看执行证据。 | `smoke:passed` | — |
| `model-gateway-routing` | Agent Runtime / Agent 生命周期 / 模型网关与平台模型路由 | `verified` | `production_candidate` | `api, web, desktop, deploy` | 模型身份、provider 和 allowlist 在服务端校验。；凭据不进入浏览器或日志。 | `integration:passed` | 真实 provider 验证依赖受控凭据和外部服务状态。 |
| `executor` | Agent Runtime / 计划与执行 / Executor 任务执行 | `verified` | `production_candidate` | `api, web` | 成功、失败、取消和暂停终态不会被迟到结果覆盖。 | `integration:passed` | — |
| `pause-resume-cancel` | Agent Runtime / 计划与执行 / 暂停、恢复与取消 | `verified` | `production_candidate` | `api, web, desktop` | 重复停止不会产生重复事件。；流中止后终态和 replay 保持一致。 | `integration:passed` | — |
| `planner` | Agent Runtime / 计划与执行 / Planner 计划生成 | `verified` | `production_candidate` | `api, web` | 计划输出可被 Executor 消费，并在 Run Detail 中可见。 | `integration:passed` | — |
| `subagent-orchestration` | Agent Runtime / 计划与执行 / Subagent 异步编排 | `verified` | `production_candidate` | `api, web` | 父 Run、Assignment、Subagent Run 和结果可关联查询。 | `integration:passed` | — |
| `docker-sandbox` | Tools、MCP 与 Sandbox / Policy Sandbox 与 WarmPool / Docker Sandbox 隔离 | `verified` | `production_candidate` | `api, deploy` | 沙箱生命周期、资源边界和失败清理可验证。 | `integration:passed` | Docker socket和生产运行时权限仍需按部署环境审查。 |
| `policy-approvals` | Tools、MCP 与 Sandbox / Policy Sandbox 与 WarmPool / Policy 与审批 | `verified` | `production_candidate` | `api, web` | 拒绝、审批和恢复决策都可审计，敏感参数不会泄漏。 | `integration:passed` | — |
| `warmpool` | Tools、MCP 与 Sandbox / Policy Sandbox 与 WarmPool / WarmPool 生命周期 | `verified` | `production_candidate` | `api, deploy` | 默认 min_ready=2、max_ready=5，异常实例可回收。 | `integration:passed` | — |
| `capability-registry` | Tools、MCP 与 Sandbox / Tools、MCP 与 Skills / Capability Registry 与版本 | `verified` | `production_candidate` | `api, web` | 新运行只从启用 attachment 解析能力，不运行时回填 legacy tools_json。 | `integration:passed` | — |
| `mcp-runtime-config` | Tools、MCP 与 Sandbox / Tools、MCP 与 Skills / MCP 与 Skill 运行配置 | `verified` | `production_candidate` | `api, web` | 页面不回显原始 API key，配置保存为 immutable CapabilityVersion。 | `e2e:passed` | 真实外部 MCP 联调依赖对应 provider 凭据和端点。 |
| `tool-runner-audit` | Tools、MCP 与 Sandbox / Tools、MCP 与 Skills / ToolRunner 审计执行 | `verified` | `production_candidate` | `api, web` | 没有 Agent capability attachment 时 fail closed。；执行结果与 Run/ModelCall 可关联。 | `integration:passed` | — |
| `desktop-attention-center` | Desktop、Terminal 与 Mobile / Desktop 工作区与本地能力 / Desktop 统一待处理中心 | `verified` | `production_candidate` | `api, web, desktop` | 服务器项目按组织隔离并稳定排序，审批项不会与等待审批的 Run 重复。；管理员可直接批准或拒绝，非管理员只看到打开入口。；Desktop 合并本地同步与 Runtime 状态，浏览器环境可无 preload 降级。 | `integration:passed` | — |
| `desktop-change-review` | Desktop、Terminal 与 Mobile / Desktop 工作区与本地能力 / Desktop 原生变更审查 | `verified` | `production_candidate` | `api, web, desktop` | Git 命令使用固定参数数组且不经过 shell，目录逃逸和 symlink 被拒绝。；普通、未跟踪、二进制、冲突、非仓库和 Git 故障状态有明确结果。；写操作要求未过期且内容一致的预览令牌、显式确认和 Admin/Engineer 审计；审计完成失败时回滚 Git mutation。 | `integration:passed` | 正式签名三平台包内的 Electron smoke 仍随 REL-001 的 Release runner 环境补证。；operation_id + phase 的并发幂等使用应用层查重，尚无数据库唯一约束。 |
| `desktop-files-ipc` | Desktop、Terminal 与 Mobile / Desktop 工作区与本地能力 / Desktop 文件与 IPC | `verified` | `production_candidate` | `desktop` | IPC 边界受信、文件操作可测试且不绕过权限边界。 | `integration:passed` | — |
| `desktop-local-runtime` | Desktop、Terminal 与 Mobile / Desktop 工作区与本地能力 / Electron 本地 Runtime | `verified` | `production_candidate` | `desktop` | 同一 profile 重启后恢复运行记录、模型设置和本地工作区。 | `integration:passed` | — |
| `desktop-offline-agent` | Desktop、Terminal 与 Mobile / Desktop 工作区与本地能力 / Desktop 完整离线 Agent | `verified` | `production_candidate` | `api, web, desktop` | 断网时使用本地模型或确定性降级完成 Run，并持久化 Run、Event、ModelCall、ToolCall 和 ToolApproval。；只允许结构化白名单工具请求；读取工具直接执行，工作区写入必须获得明确审批，模型输出永不解释为工具调用。；取消、崩溃、Profile 切换和恢复保持合法状态转换；终态快照重连后幂等导入既有服务端证据图，重复 UUID 不产生重复记录。 | `integration:passed` | 正式签名 macOS/Windows/Linux 包内的 Electron smoke 仍由 REL-001 跟踪；本地无签名 package 证据不替代该发布门。 |
| `desktop-project-knowledge-index` | Desktop、Terminal 与 Mobile / Desktop 工作区与本地能力 / Desktop 项目知识自动索引 | `verified` | `production_candidate` | `api, web, desktop` | 新增、修改、删除、忽略和重启恢复使用幂等完整 snapshot，截断扫描不能产生删除。；workspace root、symlink、文件预算和 Desktop profile 边界 fail closed。；RAG citation 显示项目相对路径、内容 hash 和文档版本，不暴露绝对路径。 | `integration:passed` | 正式签名三平台 Electron smoke 仍由 REL-001 跟踪。 |
| `desktop-trigger-automation` | Desktop、Terminal 与 Mobile / Desktop 工作区与本地能力 / Desktop Trigger 与后台自动化 | `verified` | `production_candidate` | `api, web, desktop, deploy` | 重复来源事件复用同一 invocation 和 Run，禁用与全局 kill switch 在执行前生效。；file/git 只在 local profile 访问受控 workspace，server profile 和无 workspace 场景 fail closed。；Desktop 可创建、启停、软删除并查看调用历史；Webhook secret 仅创建时显示。 | `integration:passed` | 正式签名三平台包内的 Electron smoke 仍随 REL-001 的 Release runner 环境补证。 |
| `terminal-sessions` | Desktop、Terminal 与 Mobile / Desktop 工作区与本地能力 / 认证 Terminal Session | `verified` | `production_candidate` | `api, web, desktop` | token 一次性消费、主体绑定、租约续期和并发上限有效。 | `integration:passed` | — |
| `mobile-offline-task-sync` | Desktop、Terminal 与 Mobile / Mobile 离线同步 / Mobile 离线任务同步 | `verified` | `production_candidate` | `mobile, api` | 离线操作可排队，重连后按冲突策略同步并保留状态。 | `integration:passed` | — |
| `migration-restore` | Enterprise Security 与 Deployment / Migration、Private Deploy 与 Release / 迁移与备份恢复 | `verified` | `production_candidate` | `api, deploy` | 迁移保持单头，已有数据和组织隔离在恢复后保持。 | `smoke:passed` | — |
| `private-deployment` | Enterprise Security 与 Deployment / Migration、Private Deploy 与 Release / 私有部署链路 | `verified` | `production_candidate` | `deploy, api, web` | 从私有部署配置可以完成 Agent Run 全链路并输出关联证据。 | `smoke:passed` | — |
| `release-startup-evidence` | Enterprise Security 与 Deployment / Migration、Private Deploy 与 Release / Desktop Release 启动证据 | `in_progress` | `beta` | `desktop, deploy` | macOS、Windows、Linux x64 各自生成并校验一个五样本通过报告。；聚合 P95 字段由 CI 重新计算。 | `release:blocked` | 正式 macOS/Windows/Linux Release runner 证据尚未完成；本地冷缓存 P95 曾超预算。 |
| `auth-sessions` | Enterprise Security 与 Deployment / Identity 与 Secret Boundary / Auth 与 Session | `verified` | `production_candidate` | `api, web, desktop` | 失效凭据拒绝访问，能力 token 一次性消费并绑定主体。 | `integration:passed` | — |
| `org-rbac-api-keys` | Enterprise Security 与 Deployment / Identity 与 Secret Boundary / 组织隔离、RBAC 与 API Keys | `verified` | `production_candidate` | `api, web` | 跨组织资源不可见，角色权限在 API 边界执行。 | `integration:passed` | — |
| `secrets-redaction` | Enterprise Security 与 Deployment / Identity 与 Secret Boundary / 密钥存储与脱敏 | `verified` | `production_candidate` | `api, web, desktop, deploy` | 密钥不进入浏览器存储、URL、响应、日志或错误消息。 | `integration:passed` | — |
| `knowledge-source-lifecycle` | Knowledge 与 Context / Knowledge 检索与来源 / 知识源生命周期 | `verified` | `production_candidate` | `api, web` | 当前版本检索，旧版本可识别，跨组织源不可见。 | `integration:passed` | — |
| `rag-grounding-citations` | Knowledge 与 Context / Knowledge 检索与来源 / RAG Grounding 与引用 | `verified` | `production_candidate` | `api, web` | 回答只宣称有来源绑定的结论。；证据不足、策略拒绝和 fallback 都保留可诊断元数据。 | `integration:passed` | — |
| `web-research-policy` | Knowledge 与 Context / Knowledge 检索与来源 / 策略门控 Web Research | `verified` | `production_candidate` | `api, web, deploy` | 外部结果必须带 source-bound 和策略审计证据。；禁止后端对 provider URL 做无界二次抓取。 | `integration:passed` | 真实 Tavily 联调依赖受控第三方凭据。 |
| `context-optimizer` | Knowledge 与 Context / Memory 与 Context Assembly / Context Token Optimizer | `verified` | `production_candidate` | `api, web` | 保护系统/开发者权威和用户目标，记录省略和缓存命中证据。 | `integration:passed` | — |
| `context-router` | Knowledge 与 Context / Memory 与 Context Assembly / Context Router V2 | `verified` | `production_candidate` | `api, web` | 上下文 manifest 可重建，预算和省略原因可审计。；策略拒绝的内容不会进入 prompt。 | `integration:passed` | — |
| `long-term-memory` | Knowledge 与 Context / Memory 与 Context Assembly / 长期记忆记录 | `verified` | `production_candidate` | `api, web` | 记忆资格受范围、生命周期、过期和策略过滤。 | `integration:passed` | — |
| `eval-regression` | Events、Eval 与 Observability / Eval 与 Grounding 质量 / Eval Dataset 与回归门 | `verified` | `production_candidate` | `api, web` | Eval Run 指标、历史和 Regression Gate 可从 API 读取。 | `integration:passed` | — |
| `groundedness-eval` | Events、Eval 与 Observability / Eval 与 Grounding 质量 / Groundedness Eval | `verified` | `production_candidate` | `api, web` | 评测只读取规范化证据输入，不扫描原始模型请求/响应寻找泄漏。 | `integration:passed` | — |
| `cost-token-observability` | Events、Eval 与 Observability / 事件与运行观测 / 成本与 Token 观测 | `verified` | `production_candidate` | `api, web` | 估算值与实际调用统计分开显示，省略原因可追溯。 | `integration:passed` | — |
| `event-store-replay` | Events、Eval 与 Observability / 事件与运行观测 / Event Store 与 Replay | `verified` | `production_candidate` | `api, web` | 事件追加不可变，指定序列 replay 可得到稳定状态摘要。 | `integration:passed` | — |
| `observability-tracing` | Events、Eval 与 Observability / 事件与运行观测 / Tracing 与运行观测 | `verified` | `production_candidate` | `api, web, deploy` | Run、模型调用和工具调用可以按关联 ID 查询。；敏感数据不进入观测输出。 | `integration:passed` | OPS-001 的 Tempo + Loki 端到端关联证据仍待环境具备。 |
| `specialist-marketplace` | Team Orchestration / Team 协作与专家路由 / Subagent Specialist 专家库 | `verified` | `production_candidate` | `api, web` | 专家详情路由优先于动态子代理 ID，分派结果可追踪。 | `integration:passed` | — |
| `task-graph` | Team Orchestration / Team 协作与专家路由 / Team 任务图与依赖 | `verified` | `production_candidate` | `web, desktop` | 强连通循环被压缩为稳定行，不出现反向边或布局抖动。 | `e2e:passed` | — |
| `team-coordination` | Team Orchestration / Team 协作与专家路由 / Team 协调与消息 | `verified` | `production_candidate` | `api, web, desktop` | Team Runtime 选择正确模型和成员，消息与目标状态可恢复。 | `integration:passed` | — |
| `event-stream-ui` | Workspace 与控制台 / Workspace 运行界面 / 事件流实时可见性 | `verified` | `production_candidate` | `api, web, desktop` | 事件顺序稳定，断线和终态不会破坏时间线。 | `integration:passed` | — |
| `run-detail` | Workspace 与控制台 / Workspace 运行界面 / Run Detail 诊断 | `verified` | `production_candidate` | `web, desktop` | 选定序列后可重放并显示状态摘要和失败点。；调用链证据能绑定到具体 Run。 | `integration:passed` | — |
| `team-workspace` | Workspace 与控制台 / Workspace 运行界面 / Team 协作工作区 | `verified` | `production_candidate` | `web, desktop` | 协作、任务图和多列模式保持独立语义。；窄屏无文档级横向溢出。 | `e2e:passed` | — |
| `workspace-chat` | Workspace 与控制台 / Workspace 运行界面 / Agent Workspace 对话与运行 | `verified` | `production_candidate` | `web, desktop` | 消息、运行状态和工具结果在同一工作上下文中可见。 | `e2e:passed` | — |

## 字段解释

- `implementation_status`：`not_started`、`in_progress`、`implemented`、`verified`。
- `maturity`：`prototype`、`beta`、`production_candidate`、`production_ready`、`production_proven`。
- `production_ready` 和 `production_proven` 需要对应的发布/真实环境证据；当前目录保持保守标注。

## 机器入口

- 校验：`python3 scripts/feature_catalog.py --validate`
- 生成：`python3 scripts/feature_catalog.py --generate`
- 漂移检查：`python3 scripts/feature_catalog.py --check`
- 查询：`python3 scripts/feature_catalog.py --query "RAG retrieval"`
