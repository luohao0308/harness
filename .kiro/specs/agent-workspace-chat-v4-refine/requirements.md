# Requirements Document

## Introduction

本 feature 是 `/agents/:agentId/workspace` 聊天页的 **第四轮 UX 打磨**（v4），紧跟 v1 / v2 / v3 已上线版本。本轮聚焦用户反馈的 7 条，在 **不改后端 SSE 契约、不新增前端 runtime 依赖、`useWorkspaceStore` 仅 additive 扩展、TypeScript 严格模式不倒退** 的约束内解决：

1. **Composer 仍然太高** — 默认单行起步的高度上限从 v3 的 40px 再瘦一半到 ~20–24px；`maxHeight` 保持 200px；textarea 行高 / padding 需同步收窄。
2. **对话框没有跟随消息滚动** — v3 的 `IntersectionObserver + useLayoutEffect` 方案在流式实际场景中没有稳定贴底；需要重写为一条显式状态机（user-send → snap；assistant-delta + `autoFollow` → snap；手动上滚 > 200px → 中断跟随并显示 `Jump_To_Latest_Button`），并提供属性测试覆盖三条状态转移。
3. **顶栏 metadata 删除** — `TopMetaBar` 里残留的 metadata / model pill 整体移除；只保留 `agent name + Stop + Inspector` 下拉（Workspace mode badge 也隐藏，v3 已把 metadata 下移到 footer 次要行）。
4. **Composer 底部工具栏太挤** — `ComposerToolbar` 的 Context / Pin / Tools / Model 四项统一收进一个"Options"按钮 → popover 面板（含 4 个分区）；Model picker 与 usage 计量保持可见（usage 保留 inline 小字）；popover 必须 `role="dialog"` + focus trap + ESC close。
5. **上下文长度可调整** — 当前 `ContextUsageBar` 硬编码 8192；新增 `contextMaxTokens` slider / numeric input，范围 [2000, 200000]，步进 1000，位于 Options popover 的 Context 分区；状态写回 `useWorkspaceStore.contextMaxTokens`（additive 字段）+ localStorage；usage meter 以该值为分母；发请求时作为 `context_max_tokens` 附加到 payload，后端忽略无副作用。
6. **模型仍然不流式返回** — 顽固 bug；需要在 requirements 里显式列出四个调查层面（后端 FastAPI `StreamingResponse` 与 buffer flush / Nginx `proxy_buffering` 与 `X-Accel-Buffering` 头 / 前端 `TextDecoder` stream 读法 / 浏览器-容器间 keep-alive 与 content-encoding），**端到端可观测目标：用户发送消息后，增量 token 每 ≤50ms 渲染一次；Chrome DevTools Network → EventStream 面板能观察到逐事件到达**。
7. **锦上添花优化** — 从一组候选里选 2–3 条最能提升"像 local Agent CLI / Harness Agent"的体验进入 requirements：**代码块右上角 Copy code 按钮** / **流式期间 caret 动画光标** / **连续同角色消息 group-by-role**。其余（侧栏搜索、按日期分组、`Cmd+Enter` 独立发送键绑定、消息 timestamp hover）归入 Out of Scope 供未来迭代。

本 feature **保留 v3 已交付的所有行为**（slash 命令、历史对话、autogrow 基础设施、P12–P19 属性测试全部继续全绿），仅在明确条目处做最小差异更新。所有改动限定在 `apps/agent-console/` 内部；#6 的诊断可能需要对 `services/api-server/` 或 `deploy/nginx/agent-harness.conf` 做**严格 additive** 的小修（新增响应头 / 复用现有 SSE location 的 proxy_buffering 规则），不改后端 SSE 事件集合、请求方法、URL 或请求体已有字段的语义（新增 `context_max_tokens` 请求体字段对后端为可忽略的 opt-in）。

## Glossary

（沿用 v1 / v2 / v3 术语，以下为本轮新增或语义变更条目）

- **Workspace**: 路由 `/agents/:agentId/workspace` 渲染的页面。
- **Chat_Surface**: `apps/agent-console/src/features/agents/components/ChatSurface.tsx` 渲染的主容器。
- **Workspace_Composer**: `apps/agent-console/src/features/agents/components/ChatComposer.tsx` 渲染的输入区；含 `<textarea>`、工具栏、发送按钮、v3 的 `Slash_Menu`。
- **Composer_Min_Height_V4**: v4 `<textarea>` 的最小高度；v3 为 40px，v4 目标 ≤ 24px（单行 + 收窄的 padding / line-height）。**必须满足** `Composer_Min_Height_V4 ≤ 24`。
- **Composer_Max_Height**: 保持 200px（沿用 v3）。
- **Chat_Message_List**: `apps/agent-console/src/features/agents/components/ChatMessageList.tsx` 渲染的可滚动消息列表。
- **Auto_Follow**: Chat_Message_List 维护的 boolean 状态：`true` 表示自动贴底，`false` 表示用户已主动上滚、暂停跟随。
- **Auto_Follow_Break_Threshold_Px**: 用户向上滚动并使容器距离底部 > 该像素数时，`Auto_Follow` 被强制置为 `false`。v4 取 200（沿用 v3 `JUMP_TO_LATEST_THRESHOLD_PX`）。
- **Auto_Follow_Event**: 触发 `Auto_Follow` 状态机转移的事件之一：`user_submit`（用户发消息）/ `assistant_delta`（流式 token 到达）/ `user_scroll_up`（主动向上滚）/ `user_scroll_to_bottom`（滚回贴底）/ `jump_to_latest_click`。
- **Jump_To_Latest_Button**: 悬浮在消息列表右下的 icon-only 按钮（v3 已存在，v4 保留语义但显示条件改绑新状态机）。
- **Top_Meta_Bar**: `Chat_Surface` 顶栏；v2/v3 含若干 pill，本轮进一步瘦身为 `agentName + Stop + Inspector 下拉` 三件。
- **Inspector_Menu**: v3 已合并的 Inspector 下拉（Metadata / Artifacts / Runtime），v4 保留。
- **Composer_Options_Popover**: v4 新增组件 `ComposerOptionsPopover.tsx`，挂在 `ComposerToolbar` 的「Options」按钮上；渲染 4 个分区 `Context / Pinned / Tools / Model`；`role="dialog"`、`aria-modal="false"`（非全屏模态，允许背景可见）、`aria-label` 双语；内部实现 focus trap 并在 `Escape` 按下时关闭并把焦点交还触发按钮。
- **Composer_Options_Popover_Trigger**: 触发按钮，label 双语「选项 / Options」+ ChevronDown 图标；`aria-haspopup="dialog"`；`aria-expanded` 与 popover 开合同步。
- **Context_Max_Tokens**: v4 新增 `useWorkspaceStore.contextMaxTokens: number`（additive 字段），初始值 8192（兼容 v3 观感），允许范围 `[CONTEXT_MAX_TOKENS_MIN, CONTEXT_MAX_TOKENS_MAX] = [2000, 200000]`，步进 `CONTEXT_MAX_TOKENS_STEP = 1000`。持久化到 localStorage 键 `harness.workspace.v4.<agentId>.contextMaxTokens`（独立小键，避免和 v3 conversations snapshot 绑定）。
- **Context_Max_Tokens_Slider**: Options popover 的 Context 分区渲染的 `<input type="range" min=2000 max=200000 step=1000>` + 并排 `<input type="number">` 输入；两者双向绑定；弹出说明 tooltip 双语。
- **Context_Usage_Bar**: 既有 `ContextUsageBar`，v4 调整其 `limit` 来源为 `Context_Max_Tokens`（而非硬编码 8192）。
- **Streaming_Budget_Ms**: 端到端流式延迟目标；用户发送消息后任意两个连续 `delta` 事件在前端渲染的时间差 SHALL ≤ 50ms（网络乐观假设下的目标；实际测量值作为诊断指标记录，不作为失败判据）。
- **SSE_Stream_Headers**: 端到端流式所需/禁止的响应头集合：
  - **必须**: `Content-Type: text/event-stream; charset=utf-8`、`Cache-Control: no-cache, no-transform`、`Connection: keep-alive`、`X-Accel-Buffering: no`（对 Nginx 明确关闭代理 buffering）。
  - **禁止**: 任何触发 gzip/br 压缩的 `Content-Encoding` 对 `text/event-stream` 资源生效；禁止 `Content-Length`（需要 `Transfer-Encoding: chunked`）。
- **Nginx_Chat_Stream_Location**: `deploy/nginx/agent-harness.conf` 中匹配 `^/api/agents/.*/runs/chat/stream$` 的 location block；v4 要求它（像现有 `/api/tasks/.*/events/stream` 一样）显式关 `proxy_buffering` / `proxy_cache` / `chunked_transfer_encoding`，并 pass-through 上面列出的必须响应头。
- **Code_Block_Copy_Button**: v4 新增在渲染 Markdown `<pre><code>` 时，右上角悬浮的「Copy code / 复制代码」icon-only 按钮。
- **Streaming_Caret**: v4 新增在 `ConversationNode.state === "streaming"` 的 assistant 气泡内容尾部渲染的闪烁光标（CSS `@keyframes blink` + `inline-block` 2px 宽 1em 高的 slate-400 块）。
- **Group_By_Role**: v4 新增在 `ChatMessageList` 渲染时，把 `Active_Path` 中连续同 `role` 的消息视觉合并为一组（共享气泡背景 + 角色头像只显示一次），不改 `ConversationNode` 数据结构；Property P8（MetadataStrip 实时绑定到末节点）不受影响。

## Requirements

### Requirement 1: 输入框再瘦一半 / Composer even shorter

> **用户反馈 (原话)**: 输入框再瘦一半 — composer autogrow minHeight 现在 40px 太高, 目标 ~20-24px 单行起步, maxHeight 保持 200px. 需要重新 clamp range 并确保 textarea 行高/padding 一致收窄.
>
> **Translation**: The composer is still too tall — the v3 `minHeight` of 40px should be halved to ~20–24px for a single-line starting state; `maxHeight` remains 200px. The clamp range needs to be redefined and textarea line-height / padding must shrink in parallel.

**User Story:** As Workspace 使用者, I want Workspace_Composer 单行起步高度在 24px 或以下, so that 首屏 Composer 不再有空白浪费、与 chat-first UI / local Agent CLI 的视觉比例更接近。

#### Acceptance Criteria

1. THE Workspace_Composer SHALL 把 `<textarea>` 的最小高度（包含 padding）限制为 ≤ 24 像素的 `Composer_Min_Height_V4`，不再使用 v3 的 40 像素下限。
2. THE Workspace_Composer SHALL 把 `<textarea>` 的最大高度保持为 200 像素 `Composer_Max_Height`（与 v3 一致）。
3. WHEN 用户在 Composer 输入内容致使 `scrollHeight` 大于当前 `style.height`, THE Workspace_Composer SHALL 将 `style.height` 扩展到 `scrollHeight` 对应的像素值，但不得超过 `Composer_Max_Height`。
4. WHEN `<textarea>` 内容 `scrollHeight` 超过 `Composer_Max_Height`, THE Workspace_Composer SHALL 保持 `style.height = Composer_Max_Height` 并启用 CSS `overflow-y: auto`。
5. WHEN 用户删除内容致使 `scrollHeight` 变小, THE Workspace_Composer SHALL 同步收缩 `style.height`，但不得小于 `Composer_Min_Height_V4`。
6. THE Workspace_Composer 的 `<textarea>` SHALL 采用与 `Composer_Min_Height_V4` 一致的行高与垂直 padding（例如 `line-height: 20px; padding-y: 2px;`），保证单行文本不被裁切，视觉仍为 1 行。
7. WHEN `draft` 因外部动作（Slash 命令、Plan「修改规划」、历史对话切换、Options popover 内的 action）被替换, THE Workspace_Composer SHALL 在下一次 layout effect 内同步 `style.height` 以匹配新内容。
8. THE Workspace_Composer SHALL 保留 v3 双语提示文案「Enter 发送 · Shift+Enter 换行 · 输入 / 查看命令」，视觉可缩小字号但不得删除。
9. THE Workspace_Composer SHALL 保持 v3 Slash_Menu 的开合契约不变（Property P12–P14 继续有效）。

### Requirement 2: 对话框跟随消息滚动修复 / Auto-scroll follow state machine

> **用户反馈 (原话)**: 对话框没有跟随消息滚动 — v3 的 auto-scroll follow 逻辑没生效, 发消息、收流时列表并未自动贴底. 需要确保: (a) user 发送新消息立刻滚到底, (b) 在 autoFollow=true 时 assistant 增量 token 每次追加都滚到底, (c) 只有用户主动向上滚动 >200px 才中断自动跟随并显示 JumpToLatest. 要属性测试覆盖这三个状态机转移.
>
> **Translation**: The chat list does not auto-follow on send or during streaming; the v3 IntersectionObserver-based fix doesn't actually pin-to-bottom in practice. Need (a) user submit snaps to bottom, (b) while `autoFollow=true` every assistant delta snaps to bottom, (c) only manual upward scroll > 200px breaks follow and shows `Jump_To_Latest_Button`. Property tests must cover all three transitions.

**User Story:** As Workspace 使用者, I want 发消息 / 收流 / 手动上滚 三个动作各自产生可预期的滚动行为, so that 我不会错过最新 token 也不会被强制拖回底部。

#### Acceptance Criteria

1. THE Chat_Message_List SHALL 维护显式的 `Auto_Follow` 布尔状态，并把状态机的所有转移实现为一个纯函数 `reduceAutoFollow(state, event: Auto_Follow_Event): { autoFollow: boolean; shouldSnapToBottom: boolean; showJumpButton: boolean }`，用于接 React state 同步与属性测试。
2. WHEN `Auto_Follow_Event = user_submit`（用户刚点击 Send 或按 Enter 提交新消息）, THE Chat_Message_List SHALL 将 `Auto_Follow` 置为 `true`，并在随后的 layout effect 中把滚动容器的 `scrollTop` 设为 `scrollHeight - clientHeight`（即强制贴底），无论之前 `Auto_Follow` 值为何。
3. WHILE `Auto_Follow = true` 且发生 `Auto_Follow_Event = assistant_delta`（`Active_Path` 末端 assistant 节点的 `content` 长度增加）, THE Chat_Message_List SHALL 在对应的 layout effect 内把 `scrollTop` 设为 `scrollHeight - clientHeight`，使该增量 token 可见。
4. WHILE `Auto_Follow = false`, THE Chat_Message_List SHALL 不得因 `Auto_Follow_Event = assistant_delta` 修改 `scrollTop`。
5. WHEN `Auto_Follow_Event = user_scroll_up` 且当前容器距离底部 > `Auto_Follow_Break_Threshold_Px` (200 像素), THE Chat_Message_List SHALL 将 `Auto_Follow` 置为 `false` 并显示 `Jump_To_Latest_Button`（右下悬浮、双语 `aria-label`「跳到最新 / Jump to latest」）。
6. WHEN `Auto_Follow_Event = user_scroll_up` 但容器距离底部 ≤ `Auto_Follow_Break_Threshold_Px`, THE Chat_Message_List SHALL 保持 `Auto_Follow` 为其当前值，且不显示 `Jump_To_Latest_Button`。
7. WHEN `Auto_Follow_Event = user_scroll_to_bottom`（用户手动滚回贴底，距离底部 ≤ 4 像素）, THE Chat_Message_List SHALL 将 `Auto_Follow` 置为 `true` 并隐藏 `Jump_To_Latest_Button`。
8. WHEN `Auto_Follow_Event = jump_to_latest_click`, THE Chat_Message_List SHALL 调用 `scrollTo({ top: scrollHeight, behavior: "smooth" })` 并把 `Auto_Follow` 置为 `true`、隐藏 `Jump_To_Latest_Button`。
9. THE Chat_Message_List SHALL 在容器底部挂零高度的 `Scroll_Sentinel`（v3 已存在）作为 `IntersectionObserver` 的观察目标；observer 回调 SHALL 翻译为 `user_scroll_up` / `user_scroll_to_bottom` 事件喂给 `reduceAutoFollow`，而不是直接读写 `Auto_Follow`。
10. IF 运行环境没有 `IntersectionObserver`（JSDOM 测试）, THEN THE Chat_Message_List SHALL 退化为 `Auto_Follow = true` 且不显示 `Jump_To_Latest_Button`，layout effect 继续贴底（与 v3 行为一致）。
11. THE Chat_Message_List SHALL 通过属性测试 P20 / P21 / P22 分别覆盖第 2 / 3、4 / 5 条的三条核心状态机转移（见 Req 12）。

### Requirement 3: 顶栏 metadata 最终删除 / TopMetaBar cleanup

> **用户反馈 (原话)**: 上方的 metadata 删除掉 — TopMetaBar 里剩下的 metadata/model pill 整体移除, 顶栏只留 agent name + Stop 按钮 + Inspector 下拉 (如有 workspace mode badge 也隐藏). Metadata 已经下移到 composer footer, 顶部不再重复.
>
> **Translation**: Remove the remaining metadata/model pills from `Top_Meta_Bar`. Keep only `agent name + Stop + Inspector` menu. Hide the workspace-mode badge too (even when non-chat). Metadata has already moved to the composer footer in v3 — no duplication on top.

**User Story:** As Workspace 使用者, I want 顶栏只留下最必要的三个交互点（agent name / Stop / Inspector）, so that 顶部视觉极简、不再和 footer 次要 metadata 重复。

#### Acceptance Criteria

1. THE Top_Meta_Bar SHALL 不再渲染 `modelLabel` 文本 pill，也不渲染 `modelLabelIsFallback` 的 Badge。
2. THE Top_Meta_Bar SHALL 不再渲染 `Workspace_Mode` badge（即无论 `workspaceMode` 取 `"chat" / "markdown_plan" / "plan"` 任何值都隐藏；模式切换靠 v3 的 Slash 命令 `/chat` `/plan` `/Harness Agent` 表达）。
3. THE Top_Meta_Bar SHALL 保留 `streamingLabel` 气泡（`Sparkles` 图标 + "Streaming" 文案 + `Badge` warning tone），与 `Stop` 按钮同组出现且 `isStreaming === true` 时可见，否则隐藏。
4. THE Top_Meta_Bar SHALL 保留 `Inspector_Menu` 下拉（v3 已合并的 Metadata / Artifacts / Runtime 三项），不改其内部结构。
5. THE Top_Meta_Bar SHALL 保留 `Run_Detail` 入口（`GitBranch` 图标 + 双语「Run 详情 / Run Detail」），可见条件维持 v3：`activeRunId` 存在时 primary button、否则 disabled secondary button。
6. THE Top_Meta_Bar SHALL 保留 `agentName` 作为左侧主标题。
7. THE Top_Meta_Bar 的总高度 SHALL 不超过 v3 现值（单行、`py-2`），并维持 `sticky top-0 z-10`。
8. THE Chat_Surface 的 footer 次要 metadata 行（`MetadataStrip`）SHALL 保持 v3 位置与双语不变，确保用户仍能看到 In / Out / Cost / TTFB / Duration / Run 短哈希。
9. THE Top_Meta_Bar SHALL 保留 Property P10（`isStreaming === true` 时 `Stop` 按钮可见），不因本轮精简而被违反。

### Requirement 4: 工具栏合并进 Options popover / Composer options merge

> **用户反馈 (原话)**: 工具收在一个按钮里 太乱了 — Composer 底部工具栏 (context / pin / tools / model / usage) 太拥挤, 统一收进一个 "Options" 按钮, 点击展开 popover 面板, 内含 Context、Pinned、Tools、Model 4 个分区. Model picker 和 usage 计量仍可见 (usage 保持 inline 小字). 需要 popover 的 a11y: role=dialog, focus trap, ESC close.
>
> **Translation**: Collapse the Composer toolbar (context / pin / tools / model / usage) into a single "Options" button → popover with 4 sections (Context, Pinned, Tools, Model). Keep Model picker and usage inline and visible. Popover must have `role=dialog`, focus trap, and ESC to close.

**User Story:** As Workspace 使用者, I want Composer 底部只剩少量按钮 + Options 入口, so that 视觉比当前 chip 海更干净，关键控件仍可达。

#### Acceptance Criteria

1. THE Chat_Surface SHALL 在 `Composer_Toolbar` 中以一个主触发按钮 `Composer_Options_Popover_Trigger`（双语文案「选项 / Options」+ ChevronDown）替代原先分散的 ContextPopover / PinPopover / ToolMentionChips 按钮。
2. WHEN 用户点击 `Composer_Options_Popover_Trigger`（或键盘 Enter / Space）, THE Chat_Surface SHALL 打开 `Composer_Options_Popover`；WHEN 再次点击触发按钮、或按 `Escape`、或点击 popover 外部, THE Chat_Surface SHALL 关闭 popover。
3. THE Composer_Options_Popover SHALL 渲染为 `role="dialog"` 的容器，`aria-modal="false"`（不冻结背景），并具备 `aria-labelledby` 指向内部标题「选项 / Options」。
4. THE Composer_Options_Popover SHALL 实现键盘 focus trap：`Tab` / `Shift+Tab` 在 popover 内第一个 / 最后一个可聚焦元素之间循环；popover 打开时初始焦点移到 Context 分区的第一个 `tabbable` 控件。
5. WHEN `Escape` 被按下且 Composer_Options_Popover 可见, THE Composer_Options_Popover SHALL 关闭并把焦点交还 `Composer_Options_Popover_Trigger`。
6. THE Composer_Options_Popover SHALL 包含按顺序呈现的 4 个分区：
   - **Context**（容纳 `ContextPopover` 现有内容 + v4 新增的 `Context_Max_Tokens_Slider`，见 Req 5）。
   - **Pinned**（容纳现有 `PinPopover` 内容：pinned 节点列表 + 逐条 unpin 按钮）。
   - **Tools**（容纳现有 `ToolMentionChips` 内容；选择一个 tool 后关闭 popover 并把 `@<name> ` 插入 draft）。
   - **Model**（容纳现有 `ModelPicker` 内容）。
7. THE Chat_Surface SHALL 在 `Composer_Toolbar` 主行继续可见地渲染 `ContextUsageBar`（inline、`text-[11px]`/`text-slate-500` 小字），即使 Composer_Options_Popover 处于关闭状态。
8. THE Composer_Toolbar SHALL 保留 v3 的 Export（markdown / JSON）下拉与 Clear Conversation 垃圾桶按钮在主行右侧（不并入 Options popover，因为这两个是一次性破坏/导出动作）。
9. THE Composer_Options_Popover 内各分区 SHALL 双语呈现标题（例如「上下文 / Context」「已固定 / Pinned」「工具 / Tools」「模型 / Model」），使用 `useI18n().text(zh, en)`。
10. THE Composer_Options_Popover SHALL 在 viewport 宽度 < 640 像素时允许垂直滚动（`max-h-[70vh] overflow-y-auto`），不触发页面级横向滚动。
11. WHEN Composer_Options_Popover 可见时, THE Workspace_Composer SHALL 不让 textarea 的键盘事件（包括 Enter 发送、Slash 菜单）冒泡到 popover 焦点陷阱（即 textarea 仍是独立焦点域）；用户先 `Escape` 关闭 popover、再回到 textarea 操作。注意：本 popover 存在期间 textarea 不被抢焦点。
12. THE Composer_Options_Popover 的打开状态 SHALL 存储在 React local state（`ChatSurface` 或其子组件），不依赖 `useWorkspaceStore`；**可选** additive 字段 `useWorkspaceStore.optionsPopoverOpen: boolean` 若添加则不影响其他字段语义（见 Req 9.3）。

### Requirement 5: 上下文长度可调整 / Adjustable context max tokens

> **用户反馈 (原话)**: 上下文长度要可调整 现在只有 8.2k — 新需求: model context window / max input tokens 需要可调整 slider or numeric input, 范围 [2k, 200k], 步进 1k. 放在 Options popover 的 Context 分区. 状态持久化到 useWorkspaceStore (additive field `contextMaxTokens: number`) + localStorage. Usage meter 根据该值显示百分比 (已使用 / contextMaxTokens). 发请求时从 store 读出并 attach 到 request payload 的 `context_max_tokens` 字段 (后端 SSE 契约不动; 前端传, 后端忽略也 OK, 这是 UI-side budgeting).
>
> **Translation**: The context max tokens are currently hardcoded at 8192 — users need to tune this. Add a slider + numeric input, range `[2000, 200000]`, step `1000`, inside the Context section of the Options popover. Persist to `useWorkspaceStore.contextMaxTokens` (additive field) + localStorage. Usage meter now uses this value as denominator. Outgoing requests include a new `context_max_tokens` field (backend SSE contract unchanged; the backend is free to ignore it — this is a UI-side budgeting signal).

**User Story:** As Workspace 使用者, I want 我能调整模型的上下文窗口上限, so that 不同模型 / 不同实验场景下我可以合理预算 token 用量。

#### Acceptance Criteria

1. THE useWorkspaceStore SHALL additive 新增 `contextMaxTokens: number` 字段，初始值 `8192`；additive 新增 action `setContextMaxTokens(value: number): void`，不删除或重命名任何既有字段。
2. THE setContextMaxTokens SHALL 把传入值用 `clampContextMaxTokens(value)` 纯函数钳制到 `[CONTEXT_MAX_TOKENS_MIN, CONTEXT_MAX_TOKENS_MAX] = [2000, 200000]`，并按 `CONTEXT_MAX_TOKENS_STEP = 1000` 取整（`Math.round(value / 1000) * 1000`，再次 clamp 回区间），写入 store。
3. THE Composer_Options_Popover 的 Context 分区 SHALL 渲染 `Context_Max_Tokens_Slider`：
   - `<input type="range" min={CONTEXT_MAX_TOKENS_MIN} max={CONTEXT_MAX_TOKENS_MAX} step={CONTEXT_MAX_TOKENS_STEP}>` + 相邻 `<input type="number">` + 单位后缀 `tokens`。
   - 两者 `value` 双向绑定到 `store.contextMaxTokens`；任意输入立即调用 `setContextMaxTokens`。
   - 旁附双语说明文案：「模型上下文最大长度，越大越耗 token / Model context window; larger values consume more tokens per request」。
4. THE ContextUsageBar SHALL 读取 `store.contextMaxTokens` 作为 `limit` 分母（而非 v3 硬编码 8192）；`ratio = clamp(current / limit, 0, 1)`；显示文案沿用 v3（`current / limit · NN%`）。
5. THE useChatStream SHALL 在构造 `AgentChatStreamPayload` 时，additive 附加 `context_max_tokens: store.contextMaxTokens` 字段；该字段 SHALL 不改变 `AgentChatStreamPayload` 既有字段的任何语义；后端可忽略（当前后端未读）而不影响流程。
6. THE Workspace SHALL 把 `contextMaxTokens` 持久化到 localStorage 键 `harness.workspace.v4.<agentId>.contextMaxTokens`（小键，独立于 v3 conversations snapshot），debounce 同 v3（300ms）或更短；读写失败时降级为仅内存（与 v3 Req 4.11 一致语义）。
7. WHEN Workspace 首次挂载并 `setAgentScope(agentId)` 生效, THE Workspace SHALL 尝试从上条 localStorage 键读取 `contextMaxTokens`；若存在且落在区间内 → `setContextMaxTokens(value)`；若不存在或无效 → 保持初始 `8192`。
8. THE Context_Max_Tokens_Slider SHALL 对视障用户提供双语 `aria-label`（「上下文最大 tokens / Context max tokens」），并通过 `aria-valuemin` / `aria-valuemax` / `aria-valuenow` 暴露当前数值。
9. THE useWorkspaceStore SHALL 保持 v1 / v2 / v3 已声明字段（包括 `contextWindowTurns`）的形状与语义不变；`contextWindowTurns`（turns 数）与 `contextMaxTokens`（token 数）是两个正交的 UI 预算控件，共存。

### Requirement 6: 流式返回修复 / End-to-end streaming diagnosis

> **用户反馈 (原话)**: 模型还是没有流式返回消息 — 顽固 bug. 请在 requirements 里列出需要调查的 4 个层面:
> (a) 后端 FastAPI /api/agents/:agentId/runs/chat/stream 的 StreamingResponse media_type="text/event-stream" 是否设置, 是否存在 buffer flush 问题.
> (b) docker/nginx 反向代理是否关了 proxy_buffering 和 X-Accel-Buffering: no 头.
> (c) 前端 fetch 是否在 response.body.getReader() 上按 TextDecoder stream=true 逐 chunk 解析, 没有一次性 await text().
> (d) 浏览器到容器之间的 keep-alive + content-encoding (gzip 会把 event-stream 拆成块).
> Requirement 必须是"端到端用户发起对话后, 每 ≤50ms 渲染一次增量 token; 在 chrome devtools Network → EventStream 可看到流式事件".
>
> **Translation**: Streaming still doesn't work end-to-end — this is a stubborn bug. Requirements must cover four diagnostic layers: (a) FastAPI `StreamingResponse` media type + flush semantics; (b) Nginx / docker reverse proxy `proxy_buffering` off + `X-Accel-Buffering: no`; (c) frontend `TextDecoder({stream:true})` per-chunk parse (no one-shot `.text()`); (d) browser-to-container keep-alive + content-encoding (gzip will re-chunk the event stream). End-to-end acceptance: after sending a message, delta tokens render every ≤50ms; Chrome DevTools Network → EventStream shows per-event arrival.

**User Story:** As Workspace 使用者, I want `/agents/:agentId/workspace` 发消息后 assistant 回复立刻逐 token 显现, so that 我不用等几秒钟才看到完整一块文本。

#### Acceptance Criteria

1. THE api-server `/api/agents/{agent_id}/runs/chat/stream` endpoint SHALL 返回 FastAPI `StreamingResponse(..., media_type="text/event-stream")`（已是现状），并在响应头显式设置 `Cache-Control: "no-cache, no-transform"`、`Connection: "keep-alive"`、`X-Accel-Buffering: "no"`（这三个对 Nginx / 其他反向代理有效关闭代理 buffering 的 hint）。
2. THE api-server SSE 事件生成器 SHALL 使用 `yield` 逐事件产出，不得一次性 `join` 后 `yield`；每个 `yield` 的字符串 SHALL 以 `\n\n` 结尾（SSE 帧分隔），保证代理层逐帧转发。
3. THE api-server SHALL 不对 `/api/agents/*/runs/chat/stream` 的响应启用 gzip/br `Content-Encoding`（可通过 endpoint-level 装饰器、或中间件 allowlist 跳过压缩；实现细节在 design 阶段决定）。
4. THE deploy/nginx/agent-harness.conf SHALL 为 `^/api/agents/.*/runs/chat/stream$` 匹配一个独立 `location` block（类比现有 `^/api/tasks/.*/events/stream$`），启用以下指令：
   - `proxy_pass $agent_api;`
   - `proxy_http_version 1.1;`
   - `proxy_set_header Connection "";`
   - `proxy_buffering off;`
   - `proxy_cache off;`
   - `proxy_read_timeout 3600s;`
   - `chunked_transfer_encoding off;`
5. THE deploy/nginx/agent-harness.conf SHALL 对上述 location 额外传递 `X-Accel-Buffering: no` 响应头（由后端写出后 nginx 不剥离；或 nginx 侧 `add_header X-Accel-Buffering no always;`）。
6. THE useChatStream hook SHALL 用 `response.body.getReader()` + `TextDecoder("utf-8").decode(value, { stream: true })` 逐 chunk 解析（已是现状），SHALL 不得调用 `response.text()` / `response.json()` 一次性读取。
7. THE useChatStream hook SHALL 在每次 `delta` 事件到达时，把增量 token 通过现有 `useStreamFlush.commit` 写入 store；SHALL 不在多个 `delta` 事件间做批量合并以致触发 > `Streaming_Budget_Ms` (50ms) 的渲染间隔。
8. WHEN 用户发送一条消息且后端正常响应, THE Workspace SHALL 在 Chrome DevTools Network → Response Headers 面板能观察到：
   - `Content-Type: text/event-stream; charset=utf-8` （或兼容的 `text/event-stream`）
   - `Cache-Control` 包含 `no-cache`
   - `X-Accel-Buffering: no`
   - **不得** 出现 `Content-Encoding: gzip|br|deflate`
   - **不得** 出现 `Content-Length`（应为 `Transfer-Encoding: chunked`）
9. WHEN 用户发送一条消息且后端流正常产生 N ≥ 3 个 `delta` 事件, THE Workspace SHALL 在 Chrome DevTools Network → 选中该请求 → EventStream 标签页中观察到 N 条独立事件行按时间顺序到达（而不是一次性全部显现）。
10. WHEN 用户发送一条消息且前后端配置均符合第 1–7 条, THE Chat_Message_List SHALL 在 assistant 节点上的增量渲染触发间隔（时间戳由 `delta` 到 commit）的中位数 ≤ `Streaming_Budget_Ms` (50ms)；测量方法与失败判据在 design 阶段决定（允许作为诊断指标而非 CI 硬门禁）。
11. IF 响应头 `Content-Encoding` 命中 `gzip|br|deflate` 或 `Transfer-Encoding` 缺少 `chunked`（即 nginx/压缩中间件未按第 3–4 条正确配置）, THEN THE useChatStream SHALL 把 `streaming_diagnostic: "possible_buffering"` 写到 assistant 节点 metadata（v3 已实现该分支；v4 保持不倒退）。
12. THE /api/agents/{agent_id}/runs/chat/stream endpoint SHALL 保持既有请求方法（`POST`）、URL、请求体字段及 `AgentChatStreamEvent` 事件集合不变；v4 对后端的改动严格限定在响应头与（若需要）压缩中间件 allowlist 的 additive 调整上。

### Requirement 7: local Agent CLI / Harness Agent 风格微调 / local Agent CLI-Code-like polish

> **用户反馈 (原话)**: 根据你的想法看看哪里还可以优化 — 列 3-5 条轻量改进 ... 从中选 2-3 条最能提升"像 local Agent CLI / Harness Agent"的放进 requirements.

**User Story:** As Workspace 使用者, I want 对话界面有若干"local Agent CLI / Harness Agent 式"的细节, so that 使用体验更接近行业标杆 CLI / Web 产品。

v4 选入以下 3 条（其余见 Out of Scope）：

#### Acceptance Criteria

1. **代码块右上角 Copy code 按钮 / `Code_Block_Copy_Button`**
   1.1. WHEN `ChatMessageBubble` 渲染 Markdown 内容时遇到 `<pre><code>` 块, THE ChatMessageBubble SHALL 在该块右上角悬浮一个 icon-only 按钮（`Copy` 图标 + 双语 `aria-label`「复制代码 / Copy code」）。
   1.2. WHEN 用户点击 `Code_Block_Copy_Button`, THE Workspace SHALL 调用既有 `copyText(code)` 工具函数把代码块原始文本复制到剪贴板；复制成功时按钮 SHALL 短暂切换图标为 `Check`（≤ 1500ms）并切回 `Copy`。
   1.3. THE Code_Block_Copy_Button SHALL 在按钮父容器 hover / focus-within 时才可见（`group-hover` / `focus-within:opacity-100`），非交互时以 `opacity-0` 或 `opacity-40` 不抢视觉焦点。
   1.4. THE Code_Block_Copy_Button SHALL 对键盘用户可达（`Tab` 可聚焦，`Enter` / `Space` 触发），且聚焦时显示 `focus-visible` 环。

2. **流式 caret 动画 / `Streaming_Caret`**
   2.1. WHEN `Active_Path` 末端 assistant 节点 `state === "streaming"`, THE ChatMessageBubble SHALL 在其渲染内容的尾部追加一个 `Streaming_Caret`（2 像素宽、1em 高的 slate-500 方块，`@keyframes blink` 周期 1s）。
   2.2. WHEN 该节点 `state` 变更为 `"done" / "paused" / "error"`, THE ChatMessageBubble SHALL 移除 `Streaming_Caret`。
   2.3. THE Streaming_Caret SHALL 使用 CSS 动画实现，不引入任何新 runtime 依赖；SHALL 尊重 `prefers-reduced-motion: reduce`（减少动画时改为静态方块，不闪烁）。
   2.4. THE Streaming_Caret SHALL 仅渲染在 assistant 角色气泡上，不出现在 user / system / tool 气泡。

3. **同角色消息 group-by-role / `Group_By_Role`**
   3.1. THE Chat_Message_List SHALL 在渲染 `Active_Path` 时，把连续 `role` 相同的 `ConversationNode` 视觉合并为一组：仅组内第一条显示角色头像 / 名称条，后续同角色消息共享一个更薄的分隔线。
   3.2. THE Chat_Message_List SHALL 不修改 `ConversationNode` 数据结构或 `activePath()` 的返回值；分组纯粹是渲染层 `useMemo` 派生。
   3.3. WHEN 两条连续消息其中有一条 `state === "error"`, THE Chat_Message_List SHALL **不** 把它们合并到同一视觉组（error 气泡保持独立视觉边界以避免误导）。
   3.4. THE Chat_Message_List SHALL 保持 Property P8（`MetadataStrip` 绑定到 `Active_Path` 末端节点 metadata）不受 grouping 影响；即 tail 仍是 `activePath[activePath.length - 1]`。
   3.5. THE Chat_Message_List SHALL 允许用户对 group 内任一条单独触发 Copy / Regenerate / Edit（v2 Req 4 / 5 / 10 的消息级操作不被合并吃掉）。

### Requirement 8: 国际化与可访问性（v4 增量）

**User Story:** As 多语言 Workspace 使用者, I want v4 新增的所有控件保持中英双语与键盘可达, so that i18n / a11y 不倒退。

#### Acceptance Criteria

1. THE Workspace SHALL 通过 `useI18n().text(zh, en)` 为 v4 新增的所有可见文案提供中英双语：
   - `Composer_Options_Popover_Trigger`（「选项 / Options」+ `aria-label`）。
   - `Composer_Options_Popover` 各分区标题（Context / Pinned / Tools / Model）。
   - `Context_Max_Tokens_Slider`（`aria-label` + 说明文案）。
   - `Code_Block_Copy_Button`（`aria-label`「复制代码 / Copy code」）。
   - `Jump_To_Latest_Button`（复用 v3 双语不变）。
2. THE Composer_Options_Popover SHALL 使用 `role="dialog"` + `aria-labelledby` 与内部 `<h2>` 标题关联；实现键盘 focus trap（见 Req 4.4）；`Escape` 关闭时焦点返回触发按钮。
3. THE Context_Max_Tokens_Slider SHALL 暴露 `aria-valuemin` / `aria-valuemax` / `aria-valuenow` / `aria-label`，并允许左右箭头键调整值（`<input type="range">` 原生支持）。
4. THE Code_Block_Copy_Button SHALL 使用 icon-only + 双语 `aria-label`，可通过 Tab 聚焦、Enter/Space 触发。
5. THE Streaming_Caret SHALL 尊重 `prefers-reduced-motion: reduce`（见 Req 7.2.3），不对视觉敏感用户造成困扰。
6. THE Composer_Options_Popover SHALL 在关闭后不残留 `aria-expanded="true"` 于触发按钮。

### Requirement 9: 非功能性约束（v4 增量，硬约束）

**User Story:** As Harness 维护者, I want v4 不破坏现有编译门禁、不新增 runtime 依赖、不改 SSE 事件集合, so that 合并后不需要协同升级其他模块。

#### Acceptance Criteria

1. THE Workspace SHALL 不引入除 `apps/agent-console/package.json` 已声明以外的任何 **runtime** 依赖；devDeps（如 `vitest`、`fast-check`、`msw` 等）允许 additive 新增。
2. THE api-server SHALL 保持 `POST /api/agents/:agentId/runs/chat/stream` 的请求方法、URL、既有请求体字段与 `AgentChatStreamEvent` 事件集合不变；v4 允许 additive 的：
   - 新请求体字段 `context_max_tokens: number`（后端可忽略，不影响行为）。
   - 新响应头 `X-Accel-Buffering`、强化 `Cache-Control` / `Connection`（Req 6）。
   - nginx location block 新增（`deploy/nginx/agent-harness.conf`）。
3. THE useWorkspaceStore SHALL 保持 v1 / v2 / v3 已声明字段的形状与语义不变；v4 允许 additive 新增字段：
   - `contextMaxTokens: number`（必添加；Req 5）。
   - `optionsPopoverOpen?: boolean`（可选；若不添加则用 React local state，与 Req 4.12 一致）。
   v4 SHALL 不删除、不重命名、不更改 v1 / v2 / v3 字段的 runtime 语义。
4. THE Workspace SHALL 通过 `apps/agent-console` 现有的 TypeScript 严格模式编译，不新增 `any`、`as any`、`@ts-ignore` 或 `@ts-expect-error`。
5. THE Workspace SHALL 保持 v1 / v2 / v3 已通过的所有属性测试（P1–P19，至少 19 条）继续全绿；v4 SHALL 新增 ≥ 5 条属性测试（编号 P20–P24，见 Req 12），使总数 ≥ 24 条。
6. THE Workspace SHALL 通过 `npm run lint` / `npm run build` / `npm run test` 全绿门禁（在 `apps/agent-console` 工作目录下）。
7. THE Workspace SHALL 能通过 `docker compose -f deploy/docker-compose/docker-compose.yml build` 与 `docker compose -f deploy/docker-compose/docker-compose.yml up` 完成本地部署，#6 的 nginx 变更在此流程下生效。
8. THE Workspace SHALL 不改变 `/agents/:agentId/workspace` 的 URL 或其在 `apps/agent-console/src/app/routes.tsx` 的声明位置；不改变其他页面的布局或行为。
9. THE Workspace SHALL 保持 v3 已交付的 slash 命令 / 历史对话 / autogrow / 跟滚降级逻辑的外部语义不变（除 Req 1 / 2 明确收紧的数值外）；P12–P19 继续全绿（回归）。

### Requirement 10: 向后兼容（v1 / v2 / v3 回归守护）

**User Story:** As Harness 维护者 & 老用户, I want v4 不打断已上线 v3 的任何行为, so that 老 localStorage 快照、老 URL、老属性测试全部继续工作。

#### Acceptance Criteria

1. THE Workspace SHALL 继续支持 v3 的 localStorage 键 `harness.workspace.v3.<agentId>.conversations` 的读写语义（保留 `Legacy_Migration` 的 v2 → v3 迁移路径）。v4 新增的 `contextMaxTokens` 使用独立小键 `harness.workspace.v4.<agentId>.contextMaxTokens`，SHALL 不破坏 v3 conversations 快照。
2. THE Workspace SHALL 继续支持 v3 的 `Slash_Menu` 全部 9 条命令（`/plan` `/Harness Agent` `/chat` `/pin` `/clear` `/model` `/tool` `/search` `/help`），包括方向键 / Enter / Esc / Tab 键绑定。
3. THE Workspace SHALL 继续支持 v3 的 `ConversationHistoryPanel` 行为（新建 / 切换 / 删除 / 折叠 / 持久化）。
4. THE Workspace SHALL 继续支持 v1 / v2 的所有属性 P1–P11（含 v2 P8 MetadataStrip 实时绑定、P10 Stop 可见、P11 持久化刷新安全等）。
5. THE Workspace SHALL 继续支持 v2 的 Edit / Copy / Regenerate 三操作与 Plan-approve 流程（v2 Req 4 / 5 / 10）；Req 7.3.5（Group_By_Role 不吞操作）是对这条的显式重申。

### Requirement 11: 可观测性诊断（#6 支撑）

**User Story:** As Harness 维护者, I want 当流式 bug 再次出现时，前端能在 metadata 层面给出可定位的诊断, so that 我能快速定位是代理缓冲 / gzip / 前端读法问题。

#### Acceptance Criteria

1. THE useChatStream SHALL 维持 v2/v3 已实现的 `streaming_diagnostic: "possible_buffering"` 写入路径（当响应头 `Content-Encoding` 命中压缩 或 `Transfer-Encoding: chunked` 缺失时触发）。
2. THE MetadataStrip 或其子组件 SHALL 在 assistant 节点 `metadata.streaming_diagnostic === "possible_buffering"` 时显示双语提示「可能被代理缓冲 / Possibly buffered by proxy」作为低饱和警示（不阻塞对话）。
3. THE useChatStream SHALL additive 记录首个 `delta` 的 `ttfb_ms` 与最后一个 `delta` 的 `duration_ms`（v2 已有，v4 保持不倒退）。
4. THE Workspace SHALL 不把原始响应头写入 `ConversationNode.metadata`（避免泄露潜在的认证 token / 内部 header），仅写派生的枚举诊断字段。

### Requirement 12: 正确性属性（v4 新增，交叉验证）

**User Story:** As Harness 质量工程师, I want 一组可执行的不变量覆盖 v4 关键纯函数与状态机, so that PR 门禁可以用属性测试自动校验。

v4 新增属性编号 P20–P24，沿用 v1–v3 的 P1–P19。所有属性必须在 `apps/agent-console/src/features/agents/__tests__/` 下有对应 fast-check 测试文件，并在 CI 中全绿。

#### Acceptance Criteria

1. **P20 Auto-follow user_submit snap**: WHEN `Auto_Follow_Event = user_submit`, `reduceAutoFollow({ autoFollow: any, distanceToBottomPx: any }, event)` SHALL 返回 `{ autoFollow: true, shouldSnapToBottom: true, showJumpButton: false }`，对任意先前状态 TOTAL。
2. **P21 Auto-follow assistant_delta gated**: WHEN `Auto_Follow_Event = assistant_delta` 且前一状态 `autoFollow === true`, THEN `reduceAutoFollow` SHALL 返回 `shouldSnapToBottom: true`；WHEN 前一状态 `autoFollow === false`, THEN `reduceAutoFollow` SHALL 返回 `shouldSnapToBottom: false`（在 assistant_delta 下保持用户的上滚上下文不被覆盖）。
3. **P22 Auto-follow user_scroll_up threshold**: WHEN `Auto_Follow_Event = user_scroll_up` 携带 `distanceToBottomPx > Auto_Follow_Break_Threshold_Px` (200), THEN `reduceAutoFollow` SHALL 返回 `{ autoFollow: false, shouldSnapToBottom: false, showJumpButton: true }`；WHEN `distanceToBottomPx <= 200`, THEN SHALL 返回 `showJumpButton: false`。
4. **P23 Context max tokens clamp idempotent**: THE `clampContextMaxTokens(value)` SHALL 对任意数值输入（包括 `NaN` / `±Infinity` / 负数 / 超大正数）TOTAL 不抛异常，且返回值 `r` 满足：`CONTEXT_MAX_TOKENS_MIN ≤ r ≤ CONTEXT_MAX_TOKENS_MAX` 且 `r % CONTEXT_MAX_TOKENS_STEP === 0`；连续两次调用 `clampContextMaxTokens(clampContextMaxTokens(x)) === clampContextMaxTokens(x)`（幂等）。
5. **P24 Group-by-role totality & equivalence**: THE `groupByRole(activePath)` 纯函数 SHALL 对任意合法 `ConversationNode[]` 返回分组数组 `ConversationNode[][]`，满足：
   - 合并后的扁平序列 `flatMap(groups) === activePath`（保序，不丢不加）。
   - 同一组内所有节点 `role` 相同。
   - 任一 `state === "error"` 的节点独占一组（即该节点前后分隔出新组），与 Req 7.3.3 一致。
   - 对空数组输入返回空数组，不抛异常。

## Out of Scope

以下"锦上添花优化"在 Req 7 的 3 条之外；本 v4 不实现，留待未来迭代：

1. 历史对话侧栏**搜索框**（基于 title 的前缀匹配）。
2. 历史对话侧栏**按日期分组**（Today / Yesterday / Earlier）。
3. **Cmd+Enter** = send 独立于 Enter 的键绑定（允许纯 Enter 换行、仅 Cmd+Enter 提交）。
4. **消息级 timestamp hover tooltip**（鼠标悬停显示绝对时间）。
5. **对话标题手动重命名 UI**（v3 自动取首条 user 消息前 40 字符，未来可加手动入口）。
6. **代码块语法高亮**（`prismjs` / `highlight.js` 会新增 runtime 依赖，违反 Req 9.1）。
7. **图片 / 文件 / 语音输入**（v3 / v4 均未涉及）。
8. **多窗口或跨 tab 实时同步**（localStorage storage 事件跨 tab 传播）。
9. **后端真正读取 `context_max_tokens`**（Req 5.5 仅要求前端发出字段、后端可忽略；未来后端若需据此截断上下文可作为单独 feature）。
10. **Slash 命令自定义扩展点**（v3 已硬编码 9 条，v4 不新增命令）。
11. **模型级 context_window 元数据**（`ModelSettings` 目前不暴露 per-model 上下文窗口；v4 用单一 `contextMaxTokens` 用户可调值代替，不读 model-specific 值）。
12. **docker-compose 层面的 gzip / compression 中间件变更**（若后端 FastAPI 当前未启用压缩中间件，则 Req 6.3 天然满足；无需改 compose）。
