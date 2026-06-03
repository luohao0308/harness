# Requirements Document

## Introduction

Harness 的 `/agents/:agentId/workspace` 页面（以下称 Workspace）当前以 "Agent Workspace Pro" 形式承载了 Chat、Markdown Plan、Plan-Act 三种模式，同时把 Artifacts、Tool Runtime、Approvals、Plan DAG、Metrics 等运行与评测面板直接挤在主视口内。实际使用中暴露出两个问题：一是聊天手感不符合用户预期（裸 Enter 仅换行、SSE 失败静默、缺少流式指示细节）；二是评测与运行观察过度占据工作台，反而模糊了"这里是跟 Agent 对话的主通道"的定位。

本 feature 的范围是 **Workspace 聊天体验的聚焦化重构**：

1. 将 Workspace 重塑为一个面向主流 Agent 工具 UI 的极简聊天主界面，在保持现有 Harness 视觉风格（灰白面板、slate-950 强调色、rounded-2xl 卡片、Lucide 图标）的前提下，把 Chat 设为工作台的唯一默认主通道。
2. 修正输入框的键位语义，将 Enter 作为默认发送键，Shift+Enter 换行；保留 Cmd/Ctrl+Enter 作为兼容触发。
3. 修正 SSE 流在前端的可诊断性：连接失败、HTTP 非 2xx、网络中断、鉴权失败必须在消息气泡区呈现可读错误并提供重试入口；正常情况下 `delta` / `think_delta` / `tool_call_*` / `usage` / `done` 事件按既有契约渲染。
4. 将评测、审批、Plan DAG、Artifacts 详情、Model Calls、Tool Call Runtime 等"运行与评测视图"从 Workspace 的默认主视口中撤出，迁移或链接到 `/runs/:runId`、`/observability`、`/evals`、`/tools`、`/sandboxes`、`/subagents` 等已有路由。
5. 重新界定 `chat` / `markdown_plan` / `plan` 三种 Workspace 模式在本页面中的去留：Chat 是工作台主力模式；markdown_plan、plan 通过显式入口进入专用创建 Run 流程，不再污染聊天主通道的默认视图。

本 feature **不涉及**后端 `/api/agents/:agentId/runs/chat/stream` 的契约变更，也不引入新的前端框架或图表库。现有 `AgentChatStreamEvent` 事件类型、`AgentRunWorkspace` 数据结构、Zustand 的 `workspaceStore` 形状全部保留。

## Glossary

- **Workspace**: 路由 `/agents/:agentId/workspace` 对应的页面，由 `apps/agent-console/src/features/agents/pages/AgentWorkspacePage.tsx` 渲染。
- **Workspace_Composer**: Workspace 底部的多行输入框与其操作按钮组（发送、暂停、继续、模式选择、@ 提及）。
- **Workspace_Chat_Stream**: 与后端通过 `POST /api/agents/:agentId/runs/chat/stream` 建立的 Server-Sent Events 流，事件类型由 `AgentChatStreamEvent` 定义。
- **SSE**: Server-Sent Events；此处专指 `Workspace_Chat_Stream` 使用的 `text/event-stream` 协议。
- **Agent_Run**: 一次 Agent 执行实例，由 `run_created` 事件创建，拥有 `run_id`，详细状态在 `/runs/:runId` 中展示。
- **ConversationNode**: `apps/agent-console/src/stores/workspaceStore.ts` 中的消息节点，含 `role`、`content`、`state`（`draft` | `streaming` | `paused` | `done` | `error`）、`tool_calls`、`artifacts`、`metadata`。
- **Active_Path**: 从会话根节点到当前 `activeLeafId` 的有序 `ConversationNode` 列表，即 Workspace 当前可见的对话线。
- **Workspace_Mode**: Workspace 支持的三种消息提交模式 `chat` / `markdown_plan` / `plan`，语义与 `docs/08-console-ui-spec.md#Workspace Mode Semantics` 一致。
  - **chat**: 默认模式，向模型发起普通对话式响应。
  - **markdown_plan**: 只返回 markdown 计划文本的规划模式，不执行任何操作。
  - **plan**: 显式 Plan-Act 模式，会创建可执行计划与运行产物。
- **Chat_Mode_Surface**: Workspace 在 `Workspace_Mode=chat` 时呈现的默认界面，不包含 Plan DAG / Approvals / Artifact 详情面板。
- **Run_Detail_Route**: `/runs/:runId`，`AgentRunWorkspace` 的完整投影页面，审批、Plan、Artifacts、Tool Calls、Model Calls 等以此页为权威视图。
- **Artifact**: 由 `artifact_created` 事件产生的产物，类型为 `code` | `json` | `diff` | `chart` | `text`。
- **Inspector_Drawer**: Workspace 右侧的按需抽屉，用于查看 Metadata、Artifacts、Runtime 三种次要信息，默认不展开。
- **Welcome_State**: `Active_Path` 为空时 Workspace 显示的引导卡片与示例 prompt。
- **Retry_Action**: 在 `ConversationNode.state = error` 的气泡上附带的可点击入口，用于重新发起相同 `goal` 的 `Workspace_Chat_Stream` 请求。

## Requirements

### Requirement 1: 聊天主界面布局

**User Story:** As a Harness 使用者，I want Workspace 作为一个专注的对话窗口, so that 我可以像使用 连续对话式 Agent 工具 一样与 Agent 连续对话，而不被评测和运行观察面板打断。

#### Acceptance Criteria

1. THE Workspace SHALL 以单列消息流为主视口，在 Workspace 视窗内按垂直顺序渲染「顶部元信息条（固定在 Workspace 视窗顶部，不随消息列表滚动） → 中部可滚动消息列表（占据元信息条与 Composer 之间的剩余垂直空间，内容溢出时仅在该区域内纵向滚动） → 底部 Workspace_Composer（固定在 Workspace 视窗底部，不随消息列表滚动）」。
2. THE Workspace SHALL 使用 `apps/agent-console/tailwind.config.ts` 与 `docs/design/design-tokens.json` 中已定义的灰白底色、`slate-950` 强调色、`rounded-2xl` 卡片与 Lucide 图标，不引入新字体、新色板或新图标库。
3. THE Workspace SHALL 在顶部元信息条中持续展示 `agentName`、当前模型标签（与 `AgentWorkspacePage` 现有 `modelLabel` 计算一致）、以及当前 `Workspace_Mode` 标签。
4. WHEN `ConversationNode.role = user`, THE Workspace SHALL 将该消息气泡靠右渲染，使用 `slate-950` 深色底与白色文字，且气泡最大宽度不超过消息列表内容区宽度的 75%。
5. WHEN `ConversationNode.role = assistant`, THE Workspace SHALL 将该消息气泡靠左渲染，使用 `slate-50` 浅灰底与 `slate-800` 文字，且气泡最大宽度不超过消息列表内容区宽度的 75%。
6. WHEN `ConversationNode.content` 含 Markdown 语法（围栏代码块、有序与无序列表、引用块、1 至 6 级标题、内联代码、链接）, THE Workspace SHALL 按 Markdown 渲染，其中围栏代码块使用等宽字体与语法高亮占位样式。
7. THE Workspace SHALL 不在 `Chat_Mode_Surface` 的主视口中默认渲染 Plan DAG、Approvals 完整列表、Artifact 详情列表、Model Calls 列表、Tool Call Runtime 表格中的任意一个。
8. WHEN `Active_Path` 非空且新的 `ConversationNode` 被追加且消息列表当前滚动位置距底部不超过 50 像素, THE Workspace SHALL 将消息列表自动滚动到底部。
9. WHILE `Workspace_Chat_Stream` 正在运行, THE Workspace SHALL 在顶部元信息条中展示 `Streaming` 徽标。
10. IF 新的 `ConversationNode` 被追加且消息列表当前滚动位置距底部超过 50 像素, THEN THE Workspace SHALL 保留用户当前的滚动位置且不执行自动滚动。

### Requirement 2: 输入框键位与发送语义

**User Story:** As a Harness 使用者，I want 输入框按"回车发送、Shift+Enter 换行"的约定工作, so that 我的肌肉记忆与主流对话式 Agent 工具保持一致。

#### Acceptance Criteria

1. WHEN 用户在 `Workspace_Composer` 中按下 Enter 且未同时按住 Shift 且未同时按住 Cmd/Ctrl 且 `draft.trim()` 非空 且 `activeStream` 为 null, THE Workspace SHALL 提交当前 `draft` 触发 `Workspace_Chat_Stream`。
2. WHEN 用户在 `Workspace_Composer` 中按下 Shift+Enter, THE Workspace SHALL 在光标处插入换行符而不触发提交。
3. WHEN 用户按下 Cmd+Enter 或 Ctrl+Enter, THE Workspace SHALL 与单独按 Enter 行为一致地提交 `draft`（保留兼容路径）。
4. IF `draft.trim()` 为空, THEN THE Workspace SHALL 忽略 Enter 与 Cmd/Ctrl+Enter 的提交动作，不发起 `Workspace_Chat_Stream` 请求。
5. IF `activeStream` 非 null, THEN THE Workspace SHALL 禁用发送按钮且忽略所有提交按键。
6. WHEN 一次提交成功发起后, THE Workspace SHALL 立即清空 `draft` 并保持 `Workspace_Composer` 处于聚焦状态。
7. THE Workspace SHALL 在 `Workspace_Composer` 视觉上提供一行次要提示文案说明「Enter 发送 · Shift+Enter 换行」，文案遵循现有 i18n 机制（`zh-CN` / `en-US`）。
8. THE Workspace SHALL 在 `draft.trim()` 为空 或 `activeStream` 非 null 时将主发送按钮设置为 `disabled` 状态。

### Requirement 3: SSE 流状态机与渲染

**User Story:** As a Harness 使用者，I want 每条 assistant 消息在 SSE 流期间有明确的生成状态, so that 我能分辨"正在思考"、"正在输出"、"已完成"、"被暂停"与"出错"的差别。

#### Acceptance Criteria

1. WHEN 用户提交一条消息, THE Workspace SHALL 先创建一个 `ConversationNode` 使 `role=user` 且 `state=done`，再创建一个 `ConversationNode` 使 `role=assistant` 且 `state=streaming`，并将后者设为 `Active_Path` 的末端。
2. WHILE `ConversationNode.state = streaming` 且尚未收到首个 `delta` 或 `think_delta` 事件, THE Workspace SHALL 在该气泡内展示"思考中"指示（含动画光标或跳动点）。
3. WHEN `Workspace_Chat_Stream` 推送 `delta` 事件, THE Workspace SHALL 将 `event.content` 追加到对应 `ConversationNode.content` 的可见文本部分。
4. WHEN `Workspace_Chat_Stream` 推送 `think_delta` 事件, THE Workspace SHALL 将思考片段合并到对应 `ConversationNode` 的隐藏思考段中，并在气泡内以可折叠形式展示。
5. WHEN `Workspace_Chat_Stream` 推送 `usage` 事件, THE Workspace SHALL 将 `input_tokens`、`output_tokens`、`cost_usd`、`duration_ms`、`ttfb_ms`、`model_call_id` 存入该节点的 `metadata`。
6. WHEN `Workspace_Chat_Stream` 推送 `done` 事件, THE Workspace SHALL 将该 `ConversationNode.state` 从 `streaming` 转为 `done`，保存 `run_id`，并停止思考中指示。
7. WHILE `ConversationNode.state = streaming`, THE Workspace SHALL 在气泡尾部显示一个闪烁的光标方块直到状态发生转换。
8. THE Workspace SHALL 保证每个 assistant `ConversationNode` 从 `state=streaming` 开始到本次流结束，有且仅有一次状态转换进入 `done` 或 `paused` 或 `error`（对应正确性属性 P2）。

### Requirement 4: SSE 错误可视化与重试

**User Story:** As a Harness 使用者，I want 在后端未启动、网络错误或鉴权失败时看到可读的错误提示并能一键重试, so that 我不会因为 SSE 静默失败而误以为"前端没用 SSE"。

#### Acceptance Criteria

1. IF `Workspace_Chat_Stream` 的 `fetch` 返回 HTTP 非 2xx 状态, THEN THE Workspace SHALL 将该 assistant `ConversationNode.state` 转为 `error`，并将 `content` 置为包含状态码与后端返回的 `detail` 字段（若存在）的可读文案。
2. IF `Workspace_Chat_Stream` 抛出网络错误（例如后端未启动、DNS 失败、连接被拒绝）, THEN THE Workspace SHALL 将该 assistant `ConversationNode.state` 转为 `error`，并展示包含"无法连接 Harness 后端"以及 `API_BASE_URL` 值的文案。
3. IF `Workspace_Chat_Stream` 返回的响应 `Content-Type` 不含 `text/event-stream`, THEN THE Workspace SHALL 将该节点标为 `error`，并提示用户「响应不是 SSE 流」以及前 256 字节的响应体预览。
4. IF `Workspace_Chat_Stream` 在未收到 `done` 事件前连接被远端关闭, THEN THE Workspace SHALL 将该节点 `state` 设为 `error` 并注明"SSE 流意外中断"。
5. WHEN 一个 `ConversationNode.state = error`, THE Workspace SHALL 在该气泡附带一个 `Retry_Action` 按钮。
6. WHEN 用户点击 `Retry_Action`, THE Workspace SHALL 用上一条 `role = user` 的 `ConversationNode.content` 作为 `goal` 重新发起 `Workspace_Chat_Stream`，并创建一个新的 assistant `ConversationNode`。
7. IF `AbortController.signal.aborted` 为 true 且当前节点 `state = streaming`（用户在流中点击暂停）, THEN THE Workspace SHALL 将该节点 `state` 设为 `paused` 而非 `error`。
8. IF 目标节点在用户点击暂停之前已因网络 / HTTP 错误进入 `state = error`, THEN THE Workspace SHALL 保持 `error` 状态不变，不回退为 `paused`（error 优先于 paused）。
9. THE Workspace SHALL 不得在 `Workspace_Chat_Stream` 失败时丢弃错误、关闭流静默，或仅将错误打到 `console`。

### Requirement 5: 暂停与继续控制

**User Story:** As a Harness 使用者，I want 保留暂停与继续当前流的能力, so that 我可以在长输出中中断并随后恢复生成。

#### Acceptance Criteria

1. WHILE `activeStream` 非 null, THE Workspace SHALL 在 `Workspace_Composer` 附近显示一个「暂停」按钮。
2. WHEN 用户点击暂停按钮, THE Workspace SHALL 调用 `activeStream.controller.abort()`，将当前 assistant 节点 `state` 置为 `paused` 并将 `activeStream` 置为 null。
3. WHERE `Active_Path` 中存在至少一个 `state = paused` 的 assistant 节点且该节点拥有 `run_id`, THE Workspace SHALL 在 `Workspace_Composer` 附近显示「继续」按钮。
4. WHEN 用户点击继续按钮, THE Workspace SHALL 以该 paused 节点的 `run_id`、已累积的 `content`、对应 user 节点的 `content` 作为 `goal` 重新调用 `streamAgentChatRun`，`continue_from_node_id` 设为该节点 id。
5. IF paused 节点缺少 `run_id`, THEN THE Workspace SHALL 禁用对该节点的继续操作并在气泡上提示「Run 尚未创建，无法继续」。
6. THE Workspace SHALL 将暂停与继续按钮放置在 `Workspace_Composer` 的次要操作区（而非主视口 header 的显眼位置）。

### Requirement 6: Workspace Mode 去留与聚焦

**User Story:** As a Harness 使用者，I want Workspace 明确以 Chat 模式为默认主通道, so that 我不会在"跟模型聊"时误入"创建 Plan-Act Run"。

#### Acceptance Criteria

1. WHEN 用户首次进入 Workspace, THE Workspace SHALL 将 `Workspace_Mode` 初始值设为 `chat`。
2. WHERE `Workspace_Mode = chat`, THE Workspace SHALL 始终保持 `Chat_Mode_Surface` 可见，并仅渲染 `Chat_Mode_Surface`；THE Workspace SHALL 不展示 Plan DAG、Approvals 列表、Artifact 详情与 Tool Call Runtime 面板。
3. WHERE `Workspace_Mode ∈ {markdown_plan, plan}` 被显式选择, THE Workspace SHALL 在 `Workspace_Composer` 上方插入一条明显的提示条，说明当前不是普通聊天，并提供跳转到 Run Detail 或创建 Run 表单的入口。
4. WHEN 用户切换 `Workspace_Mode`, THE Workspace SHALL 保留 `Active_Path` 中的全部已有 `ConversationNode` 不删除、不重排（对应正确性属性 P5）。
5. WHEN 用户切换 `Workspace_Mode`, THE Workspace SHALL 保留当前 `draft` 字符串不清空。
6. THE Workspace SHALL 在侧栏模式选择区域标注 `markdown_plan` 为「Plan (markdown)」、`plan` 为「Plan-Act Run」，文案与 `docs/08-console-ui-spec.md#Workspace Mode Semantics` 一致。
7. WHERE 用户偏好强化聚焦，THE Workspace SHALL 允许在 `Workspace_Composer` 主按钮旁仅保留 `chat` 模式并将 `markdown_plan`、`plan` 收纳进次级菜单（实现上允许采用分级控件，但不强制删除）。

### Requirement 7: 评测与运行观察视图迁出

**User Story:** As a Harness 产品决策者，I want Workspace 不承载评测与审批的完整工作流, so that Workspace 与 `/runs`、`/evals`、`/observability`、`/tools`、`/sandboxes`、`/subagents` 的职责边界清晰。

#### Acceptance Criteria

1. THE Workspace SHALL 不在 `Chat_Mode_Surface` 中渲染 Approvals 列表的「Approve / Reject / Modify」按钮组。
2. THE Workspace SHALL 不在 `Chat_Mode_Surface` 中渲染 Plan DAG 图形视图。
3. THE Workspace SHALL 不在 `Chat_Mode_Surface` 中渲染 Model Calls 表格与 Tool Calls 完整 Runtime 表格。
4. THE Workspace SHALL 不在 `Chat_Mode_Surface` 中渲染「保存为 Eval Case」「Eval Run」「Replay Run」任意按钮（对应正确性属性 P4）。
5. WHEN `activeRunId` 非 null 且当前流进入 `state=done`, THE Workspace SHALL 在最末 assistant 气泡下方展示一张简短的 Run 摘要卡片，包含 `run_id` 短哈希、状态徽标以及跳转 `Run_Detail_Route` 的链接按钮。
6. THE Workspace SHALL 在元信息条中提供跳转 `Run_Detail_Route` 的主入口，当 `activeRunId` 非 null 时启用。
7. WHERE 用户需要查看 Metadata、Artifacts、Runtime 三类次要信息，THE Workspace SHALL 通过 `Inspector_Drawer` 按需展开；该抽屉默认收起，不占据主视口。
8. THE Workspace SHALL 为跳转 Approvals、Plan、Evals、Observability 提供二级链接，指向已有路由：`/runs/:runId`、`/evals`、`/observability`、`/tools`、`/sandboxes`、`/subagents`，不重复实现这些页面的核心表格。

### Requirement 8: Welcome 与空状态

**User Story:** As a 首次进入 Workspace 的用户，I want 看到清晰的引导卡片与几个示例 prompt, so that 我能立即理解"这里是与 Agent 对话的地方"。

#### Acceptance Criteria

1. WHEN `Active_Path` 为空（无历史 `ConversationNode`）, THE Workspace SHALL 在消息列表区域展示 `Welcome_State`。
2. THE Welcome_State SHALL 包含当前 Agent 名称、当前模型标签、一段不超过三行的介绍文案、以及 3 到 5 条示例 prompt。
3. WHEN 用户点击任意示例 prompt, THE Workspace SHALL 将该 prompt 文本填入 `draft` 并聚焦 `Workspace_Composer`，不自动提交。
4. IF `getAgent` 请求失败, THEN THE Workspace SHALL 在顶部元信息条显示可读的降级文案（例如「无法加载 Agent 元信息，已使用 agentId 作为标题」），但 Welcome_State 与 `Workspace_Composer` 仍可用。
5. IF `getModelSettings` 请求失败, THEN THE Workspace SHALL 在顶部元信息条显示「模型设置不可用」徽标，并使用 `agent.data?.model_provider` 与 `model_name` 作为回退模型标签。
6. IF `getToolRegistry` 请求失败, THEN THE Workspace SHALL 保持主聊天功能可用，仅在侧栏 Tool Tray 区域展示空态，不阻塞发送。

### Requirement 9: 国际化与可访问性

**User Story:** As a Harness 多语言用户，I want 重构后的 Workspace 仍保留 zh-CN 与 en-US 两套文案, so that 现有 i18n 开关不会被破坏。

#### Acceptance Criteria

1. THE Workspace SHALL 通过 `apps/agent-console/src/lib/i18n.ts` 的 `useI18n().text(zh, en)` 为所有新增可见文案提供中英双语版本。
2. WHERE `locale = "zh-CN"`, THE Workspace SHALL 显示中文文案；WHERE `locale = "en-US"`, THE Workspace SHALL 显示英文文案。
3. THE Workspace SHALL 保证 `Workspace_Composer`、发送按钮、暂停按钮、继续按钮、`Retry_Action`、模式切换控件、`Inspector_Drawer` 触发按钮在键盘 Tab 顺序中可达，并在聚焦时呈现 `focus-visible` 环。
4. WHEN 用户在 `Workspace_Composer` 中按下 Esc, THE Workspace SHALL 关闭可能打开的 `MentionTray` 下拉，并保留 `draft` 文本不变。
5. THE Workspace SHALL 为所有纯图标按钮提供 `aria-label` 或附带可见文字。

### Requirement 10: 非功能性约束

**User Story:** As a Harness 维护者，I want 本次重构不引入新的前端依赖、不改动后端 SSE 契约、视觉与现有 ConsoleShell 统一, so that 我无需同步升级后端或其他页面。

#### Acceptance Criteria

1. THE Workspace SHALL 继续通过 `ConsoleShell` 渲染顶栏与侧栏，不自定义 header 搜索框或侧栏导航。
2. THE Workspace SHALL 不引入除 `apps/agent-console/package.json` 现有声明以外的新前端依赖（React 18、Vite、TypeScript、Tailwind、Lucide、Zustand、@tanstack/react-query、react-router-dom、ECharts 属于现有依赖）。
3. THE Workspace SHALL 继续使用 `streamAgentChatRun`（`POST /api/agents/:agentId/runs/chat/stream`）作为聊天入口，不变更请求方法、URL 路径、请求体字段与 `AgentChatStreamEvent` 事件集合。
4. THE Workspace SHALL 保持 `workspaceStore` 中 `ConversationNode`、`ConversationState`、`ConversationArtifact` 的类型形状向后兼容；允许新增字段但不得删除或重命名现有字段。
5. WHEN 用户在低带宽网络下使用, THE Workspace SHALL 在首屏 1 秒内渲染 `Welcome_State` 或现有 `Active_Path`，不阻塞等待 `getModelSettings` 与 `getToolRegistry` 返回。
6. THE Workspace SHALL 在本次重构后通过 `apps/agent-console` 现有的 TypeScript 严格模式编译，不新增 `any` 或 `ts-ignore`。

### Requirement 11: 正确性属性（交叉验证）

**User Story:** As a Harness 质量工程师，I want 一组可执行的不变量覆盖本次重构的关键行为, so that 我可以用属性测试或断言在 PR 中自动校验。

#### Acceptance Criteria

1. **P1 Submit invariant**: WHEN `draft.trim()` 非空 且 `activeStream` 为 null 且用户按下 Enter（未按 Shift）, THE Workspace SHALL 触发恰好一次 `Workspace_Chat_Stream` 请求。
2. **P2 State transition invariant**: THE Workspace SHALL 保证每个 assistant `ConversationNode` 从 `state = streaming` 开始，最终状态必须恰为 `done` | `paused` | `error` 中的一个，且中间不经过这三者之外的其他 state 值。
3. **P3 Error surface invariant**: IF `Workspace_Chat_Stream` 发生 HTTP 错误或网络异常, THEN 对应 `ConversationNode.state` SHALL 转为 `error` 且气泡 SHALL 展示可读错误文案与 `Retry_Action`，UI 上不存在"错误被静默吞掉"的路径。
4. **P4 Scope invariant**: WHERE `Workspace_Mode = chat`, THE Workspace SHALL 不渲染任何匹配以下选择器语义的控件：「Save as Eval Case」「Run Evals」「Plan DAG canvas」「Approvals action row」「Model Calls table」。
5. **P5 Mode-switch preservation invariant**: WHEN 用户在任意两种 `Workspace_Mode` 之间切换, THE Workspace SHALL 保持切换前后 `Active_Path` 中所有 `ConversationNode.id`、`content`、`state` 集合不变，且保持 `draft` 字符串不变。
6. **P6 Composer disabled invariant**: IF `activeStream` 非 null 或 `draft.trim()` 为空, THEN 主发送按钮 SHALL 处于 `disabled` 态，且 Enter 键 SHALL 不触发提交；THE Workspace SHALL 允许用户在此状态下继续在 `Workspace_Composer` 中输入并修改 `draft`，仅阻止提交动作。

## Out of Scope

以下项显式不在本 feature 范围内，需另行立项：

1. **后端 SSE 契约变更**：不修改 `POST /api/agents/:agentId/runs/chat/stream` 的请求体字段或 `AgentChatStreamEvent` 的事件集合；若未来新增事件类型，属于独立 feature。
2. **Agent Studio 重构**：不改动 `/agents` 注册页、Agent 详情表单、系统 Prompt 编辑器等与 Agent 构建相关的现有行为。
3. **Run Detail 页重构**：`/runs/:runId` 的 Plan、Trace、Replay、Tool Calls、Model Calls、Approvals、Assignments、Subagents 面板保持当前形态，仅接收来自 Workspace 的跳转。
4. **Eval Harness 重构**：`/evals` 下的用例管理、Run 评测、Rubric 等功能保持现状；本 feature 不在 Workspace 内新建 Eval Case、不触发 Eval Run。
5. **Observability / Tools / Sandboxes / Subagents 页面重构**：仅作为 Workspace 的跳转目标存在，本次不改它们内部布局。
6. **新增前端框架或图表库**：不引入除现有声明之外的依赖（包括但不限于 Next.js、Radix、Chakra、AntD、Chart.js、D3 等）。
7. **离线 / PWA 支持**：不讨论 Service Worker、离线缓存、本地会话持久化以外的能力；`workspaceStore` 仍然是内存状态，刷新后会重置。
8. **多 Agent 并排对话**：本次仍保持单 Agent 单对话主线，不新增并排或多标签对话视图。
9. **富媒体输入**：不新增图片粘贴、文件上传、语音输入等富媒体能力；文件接入仍由 Tool Runtime 与 Sandbox 承担。
