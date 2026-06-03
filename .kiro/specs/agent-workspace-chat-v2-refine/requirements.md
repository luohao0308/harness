# Requirements Document

## Introduction

本 feature 是对 `agent-workspace-chat-refine`（v1）之后、基于真实用户反馈的 **第二轮 UX 打磨与关键 bug 修复**。v1 已将 `/agents/:agentId/workspace` 重塑为"sticky 顶部 meta bar + 中部 `ChatMessageList` + sticky 底部 Composer + `InspectorDrawer`"的聚焦聊天主界面，并落地了 `ChatSurface`、`ChatMessageList`、`ChatMessageBubble`、`ChatErrorBubble`、`ChatRunSummary`、`ChatWelcomeState`、`ChatModeBanner`、`ChatComposer`、`InspectorDrawer`、`useChatStream`、`markdown.ts`、`sseErrors.ts`、`scroll.ts`、`activePathQueries.ts`、`chatEventReducer.ts`、`examplePrompts.ts` 等资产。

用户在使用新版工作台后反馈了 9 条问题，核心可以归纳为：

1. **布局缩在页面中部，右侧大片空白**；Workspace 没有真正占满浏览器视口。
2. **模型输出看起来不是流式**，尽管 `useChatStream` 已经按 `delta` 事件追加文本；需要排查前端批量更新与后端 / 代理层缓冲两条路径。
3. **Plan (markdown) 模式缺少 Plan 审批浮层**：收到 plan 后应在 Composer 上方弹出"批准并执行 / 修改规划 / 丢弃"。
4. **用户消息不可编辑重发**；每条 `role=user` 气泡应可就地编辑再提交，产生新的分支。
5. **缺少复制按钮**；每条 assistant 与 user 消息都应能一键复制可见文本。
6. **上一版被撤走的"上下文轮数 / Pin 列表 / @tool 提及"控件需要以轻量形式回归**，整合进 Composer 附近而非新开三栏。
7. **元数据（tokens / cost / TTFB / duration / run id）应直接在窗口某处显示**，不必点开 Inspector。
8. **用户消息气泡应改为白底黑字**，不再使用 slate-950 深色气泡。
9. 需要基于现有功能 **主动提出其他改进点**（停止按钮外露、Regenerate、时间戳、对话持久化、模型切换、搜索、导出、快捷键、上下文用量条、错误复制等）。

本 feature 的范围是在 **不变更后端 SSE 契约、不新增 runtime 依赖、不重写 Run Detail / Eval / Observability 等其他页面** 的前提下，完成上述 UX 打磨与流式显示修复。所有改动限定在 `apps/agent-console/` 内部；`useWorkspaceStore`、`AgentChatStreamEvent`、`streamAgentChatRun`、`AgentRunWorkspace` 的类型形状保持向后兼容（允许 additive 新增字段，不得删除或重命名现有字段）。

## Glossary

- **Workspace**: 路由 `/agents/:agentId/workspace` 对应的页面，由 `apps/agent-console/src/features/agents/pages/AgentWorkspacePage.tsx` 渲染。
- **Chat_Surface**: `apps/agent-console/src/features/agents/chat/ChatSurface.tsx` 渲染的垂直三段式容器（`Meta_Bar` + `Message_List` + `Workspace_Composer`）。
- **Meta_Bar**: Workspace 顶部固定条，展示 Agent 名、模型、`Workspace_Mode`、Streaming 徽标、跳转 Run Detail、`Stop_Button`、`Inspector_Drawer` 触发按钮与 `Metadata_Strip`。
- **Metadata_Strip**: `Meta_Bar` 中一行实时元数据小字显示区域，展示最近一次（或当前正在 streaming）assistant 节点的 `input_tokens`、`output_tokens`、`cost_usd`、`ttfb_ms`、`duration_ms`、`run_id` 短哈希。
- **Stop_Button**: 位于 `Meta_Bar` 右侧的"停止生成"按钮，等价于 Composer 次级区的 abort 按钮；在 `activeStream` 非 null 时出现，点击即 `controller.abort()`。
- **Workspace_Composer**: Workspace 底部的多行输入框与其操作按钮组（发送、暂停、继续、模式选择、@ 提及）。
- **Composer_Toolbar**: `Workspace_Composer` 上方或同一容器内承载 `Context_Popover`、`Pin_Popover`、`Tool_Mention_Chips`、`Model_Picker`、`Plan_Approval_Panel` 等轻量控件的行容器。
- **Context_Popover**: `Composer_Toolbar` 上的 chip，点击后弹出包含"上下文轮数"滑杆（2–20，默认 8，绑定 `useWorkspaceStore.contextWindowTurns`）的悬浮面板。
- **Pin_Popover**: `Composer_Toolbar` 上的 chip，显示当前 `pinnedNodeIds.length`，点击后弹出已 Pin 节点列表并允许取消固定。
- **Tool_Mention_Chips**: `Composer_Toolbar` 上 3–5 个常用工具的快捷 chip，点击后向 `draft` 插入 `@tool-name ` 片段。
- **Model_Picker**: `Composer_Toolbar` 上的 provider / model 切换下拉，读取 `getModelSettings()`；切换后更新 Agent 本次 Workspace 会话使用的模型（不持久化到后端 Agent 配置）。
- **Plan_Approval_Panel**: 当最近一条 assistant `ConversationNode` 的 `metadata.workspace_mode ∈ {plan, markdown_plan}` 且 `state = done` 时，显示在 `Workspace_Composer` 正上方的浮层卡片，含「批准并执行」、「修改规划」、「丢弃」、「关闭（X）」四个动作。
- **Message_List**: 中部可滚动消息区域，由 `ChatMessageList` 渲染。
- **Message_Bubble**: 单条消息气泡组件 `ChatMessageBubble`。
- **Message_Actions**: 悬停在 `Message_Bubble` 上出现的一行按钮组，最少包含 `Copy_Button`；user 气泡额外包含 `Edit_Button`；最末 assistant 气泡额外包含 `Regenerate_Button`。
- **Copy_Button**: `Message_Actions` 中的复制按钮；点击 → `navigator.clipboard.writeText(visibleContent)`，剔除 `<think>` 块；成功后按钮 icon 在 1500ms 内显示打勾态。
- **Edit_Button**: user `Message_Bubble` 上的编辑按钮；点击后进入 `Message_Edit_Mode`。
- **Message_Edit_Mode**: user 节点就地编辑态，`Message_Bubble` 变为 `<textarea>` 加两个按钮「保存并重发」、「取消」。
- **Regenerate_Button**: 最末 assistant `Message_Bubble` 上的重新生成按钮；以该 assistant 节点的父 user 节点为 parent，创建新 assistant 分支并触发 `Workspace_Chat_Stream`。
- **ConversationNode**: `apps/agent-console/src/stores/workspaceStore.ts` 中的消息节点，含 `role`、`content`、`state`、`metadata` 等字段（v1 已定义，本 feature 仅 additive）。
- **Workspace_Mode**: Workspace 支持的消息提交模式 `chat` / `markdown_plan` / `plan`（语义沿用 v1）。
- **Workspace_Chat_Stream**: 与后端 `POST /api/agents/:agentId/runs/chat/stream` 建立的 SSE 流（由 `streamAgentChatRun` 发起，`useChatStream` 包装）。
- **SSE**: Server-Sent Events；本 feature 关注其首字节时延与逐帧可见性。
- **Stream_Flush_Policy**: `useChatStream` 将 `delta` / `think_delta` 事件应用到 store 时使用的刷新策略，用于保证"每个到达的 delta 在 ≤16ms 内产生一次 UI 提交"。
- **Active_Path**: 从根节点到 `activeLeafId` 的 `ConversationNode` 序列。
- **Branch**: 在同一 parent 下由 `Message_Edit_Mode` 保存或 `Regenerate_Button` 触发产生的兄弟 `ConversationNode` 集合；每次保存 / 重新生成都会创建一个新兄弟节点。
- **Inspector_Drawer**: Workspace 右侧按需抽屉（v1 已有）；本 feature 保留其为"深度视图（完整 metrics / artifacts / runtime links）"。
- **Shortcut_Overlay**: 快捷键帮助浮层，按 `?` 键打开。
- **Search_Overlay**: 对话内搜索浮层，按 `Cmd+K` / `Ctrl+K` 打开。
- **Export_Action**: 将 `Active_Path` 导出为 Markdown 或 JSON 的菜单项。
- **Local_Persistence**: Workspace 会话在浏览器 `localStorage` 的按 `agentId` 分区持久化，刷新后可恢复。

## Requirements

### Requirement 1: 全屏布局与宽度

**User Story:** As a Workspace 使用者, I want Workspace 占满浏览器可视宽度, so that 我在宽屏下不会看到右侧大片空白、聊天流和 Composer 充分利用屏幕空间。

#### Acceptance Criteria

1. THE Workspace SHALL 使 `Chat_Surface` 的根容器宽度等于 `ConsoleShell` 内容区可用宽度，不对 `Chat_Surface` 外层容器设置 `max-w-3xl`、`max-w-2xl`、`max-w-4xl` 等最大宽度约束。
2. THE Workspace SHALL 使 `Meta_Bar`、`Message_List`、`Workspace_Composer` 三段容器的水平尺寸占满 `Chat_Surface` 的根容器宽度。
3. THE Workspace SHALL 对 `Message_Bubble` 应用"可读阅读行宽"约束，使单条气泡最大宽度不超过 `80ch` 或 `56rem`（取较小值），并在 `Message_List` 的内容列中居中该行宽容器。
4. WHERE `Workspace_Mode = chat` 且浏览器视口宽度 ≥ `1280px`, THE Workspace SHALL 保证 `Chat_Surface` 主列（不含 `Inspector_Drawer`）的单侧水平内边距 ≤ 48 像素（左右合计 ≤ 96 像素），该上限作为硬约束在任意响应式布局断点下均不得被突破。
5. WHEN `Inspector_Drawer` 打开, THE Workspace SHALL 将 `Inspector_Drawer` 以右侧抽屉形式叠加显示，并使 `Chat_Surface` 主列继续占用 `ConsoleShell` 剩余宽度，不在主列两侧新增对称留白。
6. THE Workspace SHALL 使 `Workspace_Composer` 的水平宽度与 `Message_List` 的内容列行宽上限一致，保证用户感知"消息和输入框对齐"，且输入框在宽屏下不出现左右挤压在中央 768 像素以内的视觉。
7. IF 浏览器视口宽度 < `640px`, THEN THE Workspace SHALL 将 `Chat_Surface` 水平内边距压缩到 16 像素以下，且不触发横向滚动条。

### Requirement 2: SSE 流式显示诊断与修复

**User Story:** As a Workspace 使用者, I want 看到模型输出逐字"吐字"而不是最后一次性整条出现, so that 我能直观感知模型在流式生成。

#### Acceptance Criteria

1. WHEN `Workspace_Chat_Stream` 推送一个 `delta` 事件, THE Workspace SHALL 在 16 毫秒内将该事件的 `content` 片段追加到对应 assistant `ConversationNode.content` 并完成一次 React 渲染提交；即相邻两个 `delta` 的 UI 可见文本差异 SHALL 不晚于第二个 `delta` 到达后的下一帧。
2. THE Workspace SHALL 在 `useChatStream` 应用 `delta` / `think_delta` 事件到 `useWorkspaceStore` 时使用 `Stream_Flush_Policy`，确保多个在同一宏任务到达的 `delta` 事件不会被 React 18 的自动批处理合并成单次可见更新；允许实现手段包括（不限于）`ReactDOM.flushSync`、`queueMicrotask` 切片、或将 store 更新拆分为独立微任务。
3. WHEN `Workspace_Chat_Stream` 推送的 `delta` 事件频率高于每秒 120 次, THE Workspace SHALL 允许在不丢失任何 `content` 字节的前提下将相邻 delta 合并到同一帧提交，但合并后两次 UI 可见更新的时间间隔仍 SHALL 不超过 32 毫秒。
4. THE Workspace SHALL 不得出现"assistant 气泡内容在 `done` 事件到达前保持空白、在 `done` 到达时一次性呈现全部文本"的渲染路径；即 `state = streaming` 期间 `ConversationNode.content` 的可见长度必须随 `delta` 单调非减地更新。
5. WHILE `ConversationNode.state = streaming` 且已收到至少一个 `delta`, THE Workspace SHALL 在 `Meta_Bar` 或 assistant 气泡附近呈现一个轻量进度指示（例如 `Streaming · N chars`），其中 N 为当前已累积的可见字符数，N 随 `delta` 实时更新（更新频率与第 3 条的合并策略一致）。
6. WHEN 前端在本地运行 Vite 开发服务器（`npm run dev`）并连接到同机后端, THE Workspace SHALL 能在 `delta` 事件的真实到达节奏下完成逐字流式渲染；用于验证此节奏的 HTTP 响应头 SHALL 满足 `Content-Type: text/event-stream` 且不被前端 `fetch` 解析逻辑误判为非流式。
7. THE Workspace SHALL 在其 `README` 或 `docs/` 中记录反向代理（Nginx / Ingress / API Gateway）部署 SSE 时必须设置 `X-Accel-Buffering: no` 与 `Cache-Control: no-cache` 的约束，作为"非前端缓冲"排障清单；该文档位置与现有 `docs/` 结构保持一致。
8. IF 前端检测到响应头包含 `Content-Encoding: gzip` 或 `Transfer-Encoding` 缺失 `chunked` 同时 `Content-Length` 存在, THEN THE Workspace SHALL 在该 assistant `ConversationNode` 的 `metadata` 中记录一个可读的诊断标记（字段名以 `streaming_diagnostic` 前缀，具体字段由设计阶段定义），且 SHALL 在消息底部以次要文字提示"检测到可能的代理缓冲"。
9. THE Workspace SHALL 不修改 `streamAgentChatRun`、`POST /api/agents/:agentId/runs/chat/stream` 的请求方法、URL、请求体字段，也不改动 `AgentChatStreamEvent` 的事件集合。

### Requirement 3: Plan 模式审批浮层

**User Story:** As 使用 Plan (markdown) 或 Plan-Act 模式的使用者, I want 在模型返回规划后，Composer 上方出现一个 Plan 审批浮层让我做"批准 / 补充 / 丢弃", so that 我可以快速决定这次规划是执行、改、还是丢弃，而不是回到普通聊天再手动发指令。

#### Acceptance Criteria

1. WHEN `Active_Path` 中最后一个 `ConversationNode` 满足 `role = assistant` 且 `state = done` 且 `metadata.workspace_mode ∈ {plan, markdown_plan}`, THE Workspace SHALL 在 `Workspace_Composer` 正上方渲染 `Plan_Approval_Panel`。
2. THE Plan_Approval_Panel SHALL 呈现四个可操作控件：「批准并执行」、「修改规划」、「丢弃」、「关闭（X 图标）」。
3. WHEN 用户点击「批准并执行」, THE Workspace SHALL 以该 plan 节点的 `content` 作为输入触发一次 `Workspace_Mode = plan` 的 `Workspace_Chat_Stream` 请求（等价于创建 Plan-Act Run），并在请求进行时禁用 `Plan_Approval_Panel` 的四个按钮。
4. WHEN 用户点击「修改规划」, THE Workspace SHALL 把该 plan 节点的 `content` 文本填入 `useWorkspaceStore.draft`，聚焦 `Workspace_Composer`，并隐藏 `Plan_Approval_Panel`；用户再次提交时按当前选择的 `Workspace_Mode`（通常仍为 `markdown_plan` 或 `plan`）重新发起请求。
5. WHEN 用户点击「丢弃」或「关闭（X）」, THE Workspace SHALL 隐藏 `Plan_Approval_Panel` 且 SHALL 不修改 `Active_Path` 中任何 `ConversationNode`；再次进入 Workspace 或切换 `Active_Path` 导致最末节点再次满足条件时，`Plan_Approval_Panel` 可以再次出现。
6. IF `Active_Path` 的最末 `ConversationNode` 不满足第 1 条的条件（例如是 user 节点、或 assistant 节点的 `metadata.workspace_mode = chat`、或 `state ≠ done`）, THEN THE Workspace SHALL 不渲染 `Plan_Approval_Panel`。
7. WHEN `activeStream` 非 null, THE Workspace SHALL 隐藏 `Plan_Approval_Panel`（流中不做审批）。
8. THE Plan_Approval_Panel SHALL 使用现有 Tailwind 设计 tokens（灰白底、`slate-950` 强调色、`rounded-2xl` 卡片、Lucide 图标），不引入新色板或新图标库。
9. THE Plan_Approval_Panel SHALL 通过 `useI18n().text(zh, en)` 提供中英双语文案。

### Requirement 4: 用户消息编辑与重发

**User Story:** As Workspace 使用者, I want 每条我自己发的消息可以编辑并重发, so that 我可以修正笔误或换一种说法让模型重答，而不是重新敲一遍。

#### Acceptance Criteria

1. WHEN 光标悬停（hover）或焦点聚焦在任意 `role = user` 的 `Message_Bubble` 上, THE Workspace SHALL 在该气泡上显示 `Message_Actions`，其中包含 `Edit_Button`。
2. WHEN 用户点击 `Edit_Button`, THE Workspace SHALL 将该气泡进入 `Message_Edit_Mode`：气泡内容替换为一个 `<textarea>`，其初始值等于原 `ConversationNode.content`，并显示两个按钮「保存并重发」、「取消」。
3. WHILE `Message_Edit_Mode` 处于打开状态, THE Workspace SHALL 禁用 `Workspace_Composer` 的 Enter 提交；用户在 `<textarea>` 中按 Enter SHALL 触发"保存并重发"等价动作，按 Shift+Enter 插入换行，按 Esc 等价于"取消"。
4. WHEN 用户点击「保存并重发」且 `<textarea>` 内容 `trim()` 非空, THE Workspace SHALL 以该 user 节点的父节点为 parent 创建一个新的 user `ConversationNode`（`content` 为新值，`state = done`），随后创建一个新的 assistant `ConversationNode`（`state = streaming`），将 `activeLeafId` 切换到新 assistant 节点，并触发一次 `Workspace_Chat_Stream` 请求。
5. WHEN 用户点击「取消」, THE Workspace SHALL 关闭 `Message_Edit_Mode` 且 SHALL 不修改原 `ConversationNode.content`、`state` 或任何其他字段。
6. THE Workspace SHALL 保留历史分支；即在第 4 条触发的"保存并重发"之后，原 user 节点及其后代 assistant 节点 SHALL 仍存在于 `useWorkspaceStore` 中，用户可通过现有 `switchToBranch`（或等价 API）在兄弟分支间切换。
7. IF `<textarea>` 内容 `trim()` 为空, THEN THE Workspace SHALL 禁用「保存并重发」按钮且按 Enter 不触发保存。
8. IF `activeStream` 非 null, THEN THE Workspace SHALL 禁用所有 user `Message_Bubble` 上的 `Edit_Button` 并不允许进入 `Message_Edit_Mode`。
9. WHEN 用户保存并重发成功后, THE Workspace SHALL 自动退出 `Message_Edit_Mode` 并回到普通 `Message_Bubble` 视图。

### Requirement 5: 每条消息的复制按钮

**User Story:** As Workspace 使用者, I want 每条对话都能一键复制, so that 我能把 assistant 的答案或自己的提问直接粘到别处而不用手工选择文本。

#### Acceptance Criteria

1. WHEN 光标悬停或焦点聚焦在任意 `role ∈ {user, assistant}` 的 `Message_Bubble` 上, THE Workspace SHALL 在该气泡上显示 `Message_Actions`，其中包含 `Copy_Button`。
2. WHEN 用户点击 `Copy_Button`, THE Workspace SHALL 调用 `navigator.clipboard.writeText(visibleContent)`，其中 `visibleContent` 定义为：`ConversationNode.content` 去除所有被渲染为隐藏 thinking 段的 `<think>...</think>` 包裹内容后得到的纯文本。
3. WHEN `navigator.clipboard.writeText` 调用成功, THE Workspace SHALL 将 `Copy_Button` 的图标切换为打勾（checkmark）状态，并在 1500 毫秒后自动恢复为原默认图标；IF 用户在该 1500 毫秒内再次点击同一 `Copy_Button` 且调用成功, THEN THE Workspace SHALL 重置该计时器并从新点击时刻起再次保持打勾态 1500 毫秒。
4. IF `navigator.clipboard.writeText` 调用失败（例如浏览器权限被拒绝）, THEN THE Workspace SHALL 在该 `Message_Bubble` 附近显示可读的错误提示（使用现有 toast 或内联小字均可），且 `Copy_Button` 图标 SHALL 回到默认状态而非停留在打勾态。
5. WHEN `role = assistant` 的 `Message_Bubble` 尚处于 `state = streaming`, THE Workspace SHALL 仍允许用户点击 `Copy_Button`；复制内容 SHALL 为点击时刻已累积的 `visibleContent` 快照。
6. THE Copy_Button SHALL 提供 `aria-label`，并通过 `useI18n().text(zh, en)` 提供中英双语文案（例如 zh "复制" / en "Copy"，成功态 zh "已复制" / en "Copied"）。
7. THE Workspace SHALL 不在复制内容中包含 Markdown 之外的 HTML 标签、气泡装饰元素或"思考中光标"占位符。

### Requirement 6: 轻量上下文与工具控件回归

**User Story:** As Workspace 使用者, I want 上一版三栏布局左侧的「上下文轮数 / Pin 列表 / @tool 提及 / 模型切换」控件以轻量形式回到工作台, so that 我不用离开 Workspace 就能调这些参数。

#### Acceptance Criteria

1. THE Workspace SHALL 在 `Workspace_Composer` 上方（或同一容器的次要行）渲染 `Composer_Toolbar`，包含以下控件（按顺序或按设计阶段决定的排列）：`Context_Popover`、`Pin_Popover`、`Tool_Mention_Chips`、`Model_Picker`。
2. THE Context_Popover SHALL 在点击后弹出一个最多 320 像素宽的面板，包含一条"上下文轮数"滑杆，取值范围 2 到 20，默认 8，当前值绑定 `useWorkspaceStore.contextWindowTurns`；滑杆上方 SHALL 以数字形式显示当前值。
3. THE Pin_Popover SHALL 在 chip 上显示当前 `useWorkspaceStore.pinnedNodeIds.length`，点击后弹出已 Pin 节点列表（展示每个 pinned 节点的 `role`、短预览、创建时间），每项 SHALL 提供「取消固定」按钮。
4. WHEN 用户点击「取消固定」按钮, THE Workspace SHALL 从 `useWorkspaceStore.pinnedNodeIds` 中移除对应节点 id 且 `Pin_Popover` chip 上的计数 SHALL 相应减 1。
5. THE Tool_Mention_Chips SHALL 显示 3 到 5 个常用工具的 chip，数据源来自 `getToolRegistry()` 返回的工具列表；点击任意 chip SHALL 在 `useWorkspaceStore.draft` 的光标位置（若可知）或末尾插入 `@<tool-name> ` 片段。
6. THE Model_Picker SHALL 以下拉菜单形式列出 `getModelSettings()` 返回的可用 provider / model，选中一项后 SHALL 更新本次 Workspace 会话使用的模型标签（仅前端状态，`Meta_Bar` 的模型标签同步更新），不持久化到后端 Agent 配置。
7. THE Composer_Toolbar SHALL 使用 chip / pill / icon-button 等轻量控件，不占用超过 56 像素的垂直高度；所有弹出层 SHALL 使用 popover / dropdown 样式按需展开，默认收起。
8. THE Composer_Toolbar SHALL 通过 `useI18n().text(zh, en)` 为所有可见标签与按钮提供中英双语文案。
9. IF `getToolRegistry()` 请求失败或返回空列表, THEN THE Tool_Mention_Chips SHALL 渲染空态（不显示任何 chip 或显示一条"无可用工具"提示），且 Workspace 主聊天功能 SHALL 保持可用。
10. IF `getModelSettings()` 请求失败, THEN THE Model_Picker SHALL 呈现禁用态，chip 上显示"模型设置不可用"并使用 `agent.data?.model_provider` / `model_name` 作为回退标签。

### Requirement 7: 元数据直接展示

**User Story:** As Workspace 使用者, I want tokens / cost / TTFB / duration / run id 等元数据直接出现在窗口里, so that 我不用点开 Inspector 抽屉就能看到这些数字。

#### Acceptance Criteria

1. THE Workspace SHALL 在 `Meta_Bar` 中渲染 `Metadata_Strip`，展示以下字段：`input_tokens`、`output_tokens`、`cost_usd`（保留 4 位小数，单位 USD）、`ttfb_ms`、`duration_ms`、当前关联 `run_id` 的前 8 位短哈希。
2. WHEN 当前 `Active_Path` 末端为 `state = done` 的 assistant 节点, THE Metadata_Strip SHALL 展示该节点 `metadata` 中记录的上述字段值。
3. WHILE 当前 `Active_Path` 末端为 `state = streaming` 的 assistant 节点且 `Workspace_Chat_Stream` 已推送过至少一个 `usage` 事件, THE Metadata_Strip SHALL 随最新 `usage` 事件实时更新展示的数字。
4. WHEN `Active_Path` 为空或末端节点的 `metadata` 缺少某字段, THE Metadata_Strip SHALL 持续渲染其结构并对该字段显示占位符（例如 `—`）而非 `undefined` / `NaN` / `0`；即 `Metadata_Strip` 容器 SHALL 始终可见，不因无会话或无 metadata 而隐藏。
5. WHEN 用户点击 `Metadata_Strip` 中的 `run_id` 短哈希, THE Workspace SHALL 跳转到 `/runs/:runId`（使用完整 `run_id`），该行为与 v1 已有的 Run Detail 入口保持一致。
6. THE Metadata_Strip SHALL 使用次要字号（不大于 `text-xs`）与 `slate-500` 左右级别的低饱和色，不与 Agent 名 / 模型标签争抢视觉焦点。
7. THE Workspace SHALL 保留 `Inspector_Drawer` 作为完整 metrics / artifacts / runtime links 的深度视图，且 `Metadata_Strip` 不替代 `Inspector_Drawer` 的内部明细表格。
8. THE Workspace SHALL 通过 `useI18n().text(zh, en)` 为 `Metadata_Strip` 中的字段标签提供中英双语文案（`input_tokens` → zh "输入" / en "In"，`output_tokens` → zh "输出" / en "Out" 等；具体文案允许由设计阶段微调但必须双语）。

### Requirement 8: 用户消息样式

**User Story:** As Workspace 使用者, I want 用户消息气泡是白底黑字, so that 它在整体灰白主题下更清爽、更像主流 Chat 产品（主流聊天工具）的用户气泡。

#### Acceptance Criteria

1. WHEN `ConversationNode.role = user`, THE Message_Bubble SHALL 使用 `bg-white`、`border border-slate-200`、`text-slate-900` 组合（或等价 Tailwind tokens），不使用 `slate-950` 深色底、不使用白色文字。
2. THE Message_Bubble（`role = user`）SHALL 继续靠右对齐，不改变 v1 已有的左右分栏语义。
3. THE Message_Bubble（`role = user`）SHALL 使用 `rounded-2xl` 圆角与 v1 一致的内边距，保证高度与 assistant 气泡视觉协调。
4. THE Message_Bubble（`role = user`）的最大宽度 SHALL 不超过 `Message_List` 内容列实际渲染宽度的 75%（当内容列超过 `80ch` 时仍按 75% × 实际渲染宽度计算，不回退到 75% × 80ch 的较小值）；同时 SHALL 遵循 Requirement 1.3 定义的 `80ch` 或 `56rem` 的消息列内容上限。
5. WHILE `Message_Bubble` 处于 `Message_Edit_Mode`, THE textarea 背景 SHALL 保持白底黑字，与非编辑态视觉一致。
6. THE Message_Bubble（`role = assistant`）SHALL 保持 v1 已定义的 `slate-50` 浅灰底与 `slate-800` 文字样式不变。
7. THE Workspace SHALL 更新所有用到用户气泡的色彩引用（包括 `ChatMessageBubble`、`ChatWelcomeState` 示例预览、`Message_Edit_Mode` 等），保证前端无残留的 `slate-950` 用户气泡样式。

### Requirement 9: 停止生成按钮外露（P0）

**User Story:** As Workspace 使用者, I want 在 `Meta_Bar` 上也能看到「停止生成」按钮, so that 当输出过长时我可以快速从顶部停止，而不必滚到 Composer 次级区找暂停按钮。

#### Acceptance Criteria

1. WHILE `activeStream` 非 null, THE Meta_Bar SHALL 立即渲染 `Stop_Button`（不设抖动延迟阈值）；其文案为 zh "停止生成" / en "Stop"，图标使用 Lucide `Square` 或 `CircleStop`。
2. WHEN 用户点击 `Stop_Button`, THE Workspace SHALL 调用 `activeStream.controller.abort()`，将当前 assistant `ConversationNode.state` 置为 `paused` 并将 `useWorkspaceStore.activeStream` 置为 null，行为与 v1 Composer 暂停按钮一致。
3. WHEN `activeStream` 为 null, THE Meta_Bar SHALL 不渲染 `Stop_Button`。
4. THE Workspace SHALL 保留 Composer 次级区的暂停按钮，不删除 v1 已有暂停控件。
5. THE Stop_Button SHALL 在键盘 Tab 顺序中可达，并在聚焦时呈现 `focus-visible` 环。

### Requirement 10: Regenerate（P1）

**User Story:** As Workspace 使用者, I want 最末 assistant 消息上有「重新生成」按钮, so that 我可以让模型换一次答，同时保留旧答作为历史分支。

#### Acceptance Criteria

1. WHEN `Active_Path` 末端为 `role = assistant` 且 `state ∈ {done, error, paused}` 的 `ConversationNode`, THE Message_Bubble SHALL 在 `Message_Actions` 中显示 `Regenerate_Button`。
2. WHEN 用户点击 `Regenerate_Button`, THE Workspace SHALL 以该 assistant 节点的父 user 节点的 `content` 为 `goal`，在同一父节点下创建一个新的兄弟 assistant `ConversationNode`（`state = streaming`），将 `activeLeafId` 切换到新节点，并触发 `Workspace_Chat_Stream`。
3. THE Workspace SHALL 保留原 assistant 节点于 `useWorkspaceStore` 中作为历史分支，用户可通过 `switchToBranch` 在兄弟间切换。
4. IF `activeStream` 非 null, THEN THE Regenerate_Button SHALL 处于禁用态。
5. IF 目标 assistant 节点没有 `role = user` 的父节点（理论上不可达，但作为兜底）, THEN THE Regenerate_Button SHALL 处于禁用态。

### Requirement 11: 消息时间戳（P1）

**User Story:** As Workspace 使用者, I want 每条消息有时间戳, so that 我能知道对话发生在什么时候。

#### Acceptance Criteria

1. THE Message_Bubble SHALL 在气泡外的次要位置（底部或一角）显示相对时间（例如 zh "3 分钟前" / en "3 min ago"），文字使用次要字号与低饱和色。
2. WHEN 鼠标悬停在相对时间文字上, THE Workspace SHALL 通过 `title` 属性或 tooltip 展示完整 ISO 8601 时间戳（本地时区）。
3. THE Workspace SHALL 使用 `ConversationNode.metadata.created_at` 或等价字段作为时间源；若该字段缺失则使用节点首次加入 `useWorkspaceStore` 的客户端时间作为兜底，但 SHALL 不回写为 `created_at` 字段避免污染服务端数据。
4. THE Workspace SHALL 通过 `useI18n().text(zh, en)` 为相对时间格式提供双语输出。

### Requirement 12: 本地持久化（P1）

**User Story:** As Workspace 使用者, I want 刷新浏览器后我的对话还在, so that 我不会因为误刷导致上下文全丢。

#### Acceptance Criteria

1. THE Workspace SHALL 将 `useWorkspaceStore` 中 `nodesById`、`rootNodeId`、`activeLeafId`、`pinnedNodeIds`、`contextWindowTurns`、`draft` 按 `agentId` 分区持久化到 `localStorage`，键名以 `harness.workspace.v2.<agentId>` 前缀。
2. WHEN 用户刷新浏览器并重新进入同一 `agentId` 的 Workspace, THE Workspace SHALL 从 `localStorage` 恢复上述字段，并以此渲染 `Active_Path` 与 `Workspace_Composer` 的 `draft`。
3. IF `localStorage` 写入操作实际失败（例如用户禁用本地存储或超出配额时触发异常）, THEN THE Workspace SHALL 从该失败时刻起降级为仅内存状态，且 SHALL 不影响主聊天功能；THE Workspace SHALL 不在首屏预先检测 `localStorage` 可用性并提前降级，而是按实际写入结果反应式切换。
4. IF `localStorage` 中读取到的数据与当前 TypeScript 类型不兼容（例如 schema 版本变更）, THEN THE Workspace SHALL 丢弃该条数据，使用空初始状态，且 SHALL 不抛出未捕获异常阻塞首屏。
5. THE Workspace SHALL 在 `Composer_Toolbar` 或 `Meta_Bar` 提供「清空对话」入口，点击后清除内存状态与本 `agentId` 分区的 `localStorage` 数据；点击前 SHALL 有二次确认。
6. THE Workspace SHALL 不持久化 `activeStream`、任何 `AbortController` 实例或 `Workspace_Chat_Stream` 中间状态；刷新后 `activeStream` SHALL 为 null，当时处于 `state = streaming` 的节点 SHALL 在恢复后被重写为 `state = paused` 或 `state = error`（由设计阶段决定，但必须明确其中一种且不得保持 `streaming`）。

### Requirement 13: 其他改进（P2）

**User Story:** As Workspace 使用者, I want 一组可选的效率增强（搜索、导出、快捷键、上下文用量条、错误复制）, so that Workspace 使用体验更接近成熟 AI IDE。

#### Acceptance Criteria

1. WHEN 用户按下 `Cmd+K`（macOS）或 `Ctrl+K`（其他）, THE Workspace SHALL 打开 `Search_Overlay`；在其中输入关键字 SHALL 在当前 `agentId` 的本地 `nodesById` 中做不区分大小写的子串匹配，命中节点 SHALL 以列表形式展示，点击命中项 SHALL 把 `Message_List` 滚动并高亮该节点。
2. WHEN 用户按下 `?` 且焦点不在 `<textarea>` / `<input>` 中, THE Workspace SHALL 打开 `Shortcut_Overlay`，列出 Workspace 支持的所有快捷键（至少包含 Enter 发送、Shift+Enter 换行、Cmd/Ctrl+K 搜索、Esc 关闭浮层、? 打开帮助）。
3. THE Workspace SHALL 在 `Composer_Toolbar` 或 `Meta_Bar` 提供 `Export_Action` 菜单，包含「导出为 Markdown」与「导出为 JSON」两个选项；点击后 SHALL 把当前 `Active_Path` 序列化为对应格式并触发浏览器下载。
4. THE Workspace SHALL 在 `Metadata_Strip` 或 `Composer_Toolbar` 显示一个上下文用量条形图（简单进度条即可），其长度比例为 `sum(output_tokens + input_tokens across contextWindowTurns) / context_window_limit`；`context_window_limit` 可从 `getModelSettings()` 读取，缺失时使用默认 8192。
5. WHEN 上下文用量比例 ≥ 0.8, THE Workspace SHALL 在用量条旁显示警示图标与"可能需要裁剪上下文"的次要提示。
6. WHEN `ConversationNode.state = error`, THE ChatErrorBubble SHALL 在气泡内提供「复制错误详情」按钮，点击后复制包含 HTTP 状态、网络错误消息、响应体预览（若存在）与当前 `agentId` / `run_id`（若存在）的多行文本。
7. THE Workspace SHALL 通过 `useI18n().text(zh, en)` 为本需求涉及的所有可见文案提供中英双语。
8. WHERE 浏览器不支持 `navigator.clipboard.writeText`, THE Workspace SHALL 对 `Copy_Button` 与「复制错误详情」采用 `document.execCommand('copy')` 的回退路径或直接禁用这两个按钮并呈现"不支持自动复制"的提示。

### Requirement 14: 国际化与可访问性

**User Story:** As 多语言 Workspace 使用者, I want v2 新增的所有控件保持中英双语, so that i18n 不因本次打磨受损。

#### Acceptance Criteria

1. THE Workspace SHALL 通过 `apps/agent-console/src/lib/i18n.ts` 的 `useI18n().text(zh, en)` 为 v2 新增的全部可见文案提供中英双语。
2. THE Workspace SHALL 保证 `Stop_Button`、`Plan_Approval_Panel` 的四个按钮、`Copy_Button`、`Edit_Button`、`Regenerate_Button`、`Context_Popover`、`Pin_Popover`、`Tool_Mention_Chips`、`Model_Picker`、`Search_Overlay`、`Shortcut_Overlay`、`Export_Action` 在键盘 Tab 顺序中可达，且聚焦时呈现 `focus-visible` 环。
3. THE Workspace SHALL 为所有纯图标按钮（含 `Copy_Button` 的默认态与打勾态、`Edit_Button`、`Regenerate_Button`、`Stop_Button`、`Plan_Approval_Panel` 的关闭 X）提供 `aria-label` 或附带可见文字。
4. WHEN `Plan_Approval_Panel` 或任意 popover / overlay 打开, THE Workspace SHALL 允许用户按 Esc 关闭该浮层，且关闭 SHALL 不改变 `useWorkspaceStore.draft` 或 `Active_Path` 内容。

### Requirement 15: 非功能性约束

**User Story:** As Harness 维护者, I want 本次打磨不引入新依赖、不改后端契约、不破坏现有编译门禁, so that 合并后无须协同升级其他模块。

#### Acceptance Criteria

1. THE Workspace SHALL 不引入除 `apps/agent-console/package.json` 已声明以外的任何 runtime 依赖（React 18、Vite 6、Tailwind 3.4、Zustand 5、@tanstack/react-query、react-router-dom、lucide-react 属于已有依赖）。
2. THE Workspace SHALL 不修改 `POST /api/agents/:agentId/runs/chat/stream` 的请求方法、URL、请求体字段或 `AgentChatStreamEvent` 事件集合。
3. THE Workspace SHALL 保持 `useWorkspaceStore` 的既有字段（`nodesById`、`rootNodeId`、`activeLeafId`、`pinnedNodeIds`、`activeStream`、`draft`、`contextWindowTurns` 等）形状向后兼容；本 feature 允许 additive 新增字段（例如编辑分支辅助字段、Plan_Approval_Panel 显隐状态、Streaming 诊断字段），但 SHALL 不删除、不重命名、不更改现有字段的类型语义。
4. THE Workspace SHALL 通过 `apps/agent-console` 现有的 TypeScript 严格模式编译，不新增 `any`、`as any` 或 `@ts-ignore` / `@ts-expect-error`（除非是为未解决类型问题临时标注并关联 TODO，且设计阶段明确批准）。
5. THE Workspace SHALL 继续通过 `ConsoleShell` 渲染顶栏与侧栏，不自定义 header 搜索框或侧栏导航。
6. THE Workspace SHALL 在首屏 1 秒内完成 `Chat_Surface` 骨架渲染，不阻塞等待 `getModelSettings` 与 `getToolRegistry` 返回；v1 已达成的 "低带宽下 1 秒内渲染 Welcome 或 Active_Path" 不变。
7. THE Workspace SHALL 保持 v1 已通过的所有路由与 ConsoleShell 约束，不变更 `/agents/:agentId/workspace` 的 URL 或其在 `apps/agent-console/src/app/routes.tsx` 中的声明位置。

### Requirement 16: 正确性属性（交叉验证）

**User Story:** As Harness 质量工程师, I want 一组可执行的不变量覆盖本次 UX 打磨的关键行为, so that PR 门禁可以用属性测试或断言自动校验。

#### Acceptance Criteria

1. **P1 Full-width invariant**: THE Chat_Surface 根容器 SHALL 不被 `max-w-3xl`、`max-w-2xl`、`max-w-4xl` 等最大宽度类限制；且在视口宽度 ≥ `1280px` 时，其水平内边距合计 SHALL ≤ 96 像素。
2. **P2 Monotonic streaming invariant**: WHILE `ConversationNode.state = streaming`, 该节点 `content` 的可见文本长度 SHALL 在每次 UI 可见更新后单调非减，且相邻两次可见更新的时间间隔 SHALL ≤ 32 毫秒（在 `delta` 事件持续到达的前提下）。
3. **P3 No-batch invariant**: THE Workspace SHALL 保证每次 `delta` 事件到达后，对应 `ConversationNode.content` 的变化在 ≤ 16 毫秒内产生一次 React 渲染提交（或在高频场景下按第 2 条合并策略于 ≤ 32 毫秒内提交）。
4. **P4 Plan-panel precondition invariant**: THE Plan_Approval_Panel SHALL 仅在 `Active_Path` 末端 `ConversationNode` 满足 `role = assistant ∧ state = done ∧ metadata.workspace_mode ∈ {plan, markdown_plan}` 且 `activeStream = null` 时可见；其他所有情况下 SHALL 不可见。
5. **P5 Discard safety invariant**: WHEN 用户点击 `Plan_Approval_Panel` 的「丢弃」或「关闭（X）」, THE Workspace SHALL 不修改 `useWorkspaceStore` 中任何 `ConversationNode` 字段；即操作前后 `nodesById` 深等价。
6. **P6 Edit does not delete invariant**: WHEN 用户在 user 气泡点击「保存并重发」, THE Workspace SHALL 保留原 user `ConversationNode` 及其所有后代节点于 `useWorkspaceStore.nodesById` 中，且该原 user 节点的父节点下 SHALL 至少存在 2 个兄弟 user 节点（原节点 + 新节点）；形式化：`getSiblings(originalUserNodeId).length >= 2`。
7. **P7 Copy purity invariant**: WHEN 用户点击 `Copy_Button`, THE clipboard 中写入的文本 SHALL 等于 `ConversationNode.content` 去除所有 `<think>...</think>` 包裹段后的字符串；不得包含气泡装饰 HTML 或 React 内部元素。
8. **P8 Metadata consistency invariant**: THE Metadata_Strip 展示的 `input_tokens`、`output_tokens`、`cost_usd`、`ttfb_ms`、`duration_ms`、`run_id` 值 SHALL 在任意时刻等于 `Active_Path` 末端 `ConversationNode.metadata` 中对应字段的值（缺失字段以占位符显示），不存在 `Inspector_Drawer` 与 `Metadata_Strip` 展示数值不一致的时刻。
9. **P9 User bubble color invariant**: WHERE `ConversationNode.role = user`, THE Message_Bubble 的背景颜色 token SHALL 为 `bg-white`（或等价 token），且文本颜色 token SHALL 为 `text-slate-900`（或等价 token）；不得匹配 `bg-slate-950` / `text-white` 的用户气泡样式。
10. **P10 Stop button visibility invariant**: WHILE `useWorkspaceStore.activeStream !== null`, THE Meta_Bar SHALL 渲染 `Stop_Button`；WHILE `useWorkspaceStore.activeStream === null`, THE Meta_Bar SHALL 不渲染 `Stop_Button`。
11. **P11 Persistence safety invariant**: WHEN 浏览器刷新后恢复 `useWorkspaceStore`, THE Workspace SHALL 不存在任何 `ConversationNode.state = streaming` 的节点（所有此前处于 streaming 的节点 SHALL 恢复为 `paused` 或 `error`，由设计阶段统一选择）；该约束仅在刷新恢复路径上生效，正常运行期间 `state = streaming` 节点 SHALL 允许按 Requirement 2 与 Requirement 9 的语义存在。

## Out of Scope

以下项显式不在本 feature 范围内：

1. **后端 SSE 契约变更**：不修改 `POST /api/agents/:agentId/runs/chat/stream` 的请求体字段、响应事件集合或语义。
2. **反向代理配置修改**：本 feature 仅在 `docs/` 层面记录反向代理部署 SSE 的建议配置（`X-Accel-Buffering: no` 等），不修改任何 Nginx / Ingress / 云厂商网关的实际配置。
3. **Run Detail / Eval / Observability / Tools / Sandboxes / Subagents 页面重构**：这些页面仅作为 Workspace 跳转目标存在，本次不改它们内部布局。
4. **Agent Studio 重构**：不改 `/agents` 注册页、Agent 详情表单、系统 Prompt 编辑器。
5. **新增 runtime 依赖**：不引入除 `apps/agent-console/package.json` 现有声明以外的前端依赖（含 Next.js、Radix、AntD、Chakra、Chart.js、D3、dayjs / date-fns 等）。允许复用现有依赖与 Vite 内置能力实现所有功能（相对时间格式可用 `Intl.RelativeTimeFormat`）。
6. **富媒体输入**：不新增图片粘贴、文件上传、语音输入等富媒体能力；文件仍由 Tool Runtime / Sandbox 承担。
7. **多 Agent 并排对话**：保持单 Agent 单对话主线，不新增并排或多标签对话视图。
8. **上下文裁剪算法**：Requirement 13 的"上下文用量条"仅做可视化与警示，不改变后端实际 `context_window_turns` 的裁剪算法。
9. **Model_Picker 后端持久化**：本 feature 的 Model_Picker 仅影响前端会话标签；不调用后端 API 修改 Agent 配置文件或 provider 设置。
10. **PBT 框架引入**：Requirement 16 的正确性属性以断言 / 单元测试形式落地（允许使用现有测试框架），不强制引入新的 property-based testing 库。
