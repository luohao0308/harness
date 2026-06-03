# Requirements Document

## Introduction

本 feature 是 `agent-workspace-chat-v2-refine`（v2）之后的 **第三轮 UX 打磨**，聚焦在 6 条真实反馈：

1. **输入框过大**：v2 `min-h-24`（96px）固定高度；希望默认 1 行（约 40px），随内容自动增高，超过阈值内部滚动。
2. **页面不自动跟随对话**：v2 用 `shouldAutoScroll`（阈值 50px）+ `pathLength + lastContentLength` 作为 `useEffect` 依赖，流式 `delta` 过程中若 hidden overflow / 容器高度计算不对 / `shouldAutoScroll` 阈值在 rAF 与实际 scrollHeight 更新之间错位，都会导致"不跟滚"。需要用 `useLayoutEffect` + 底部 sentinel 的 `IntersectionObserver` 重做。
3. **Metadata 太抢焦点**：v2 `MetadataStrip` 挂在 `TopMetaBar` 下面；需要挪到 Composer 上方（次要位置），不再与顶栏徽标同排。
4. **没有历史对话 / 像完整的对话窗口**：需要左侧可折叠的"历史对话"抽屉，列出本 Agent 下的 conversations，支持新建 / 切换 / 删除 / 当前高亮。
5. **用 `/` 命令触发模式和动作**：在 Composer 输入 `/` 弹出命令菜单（`/plan`、`/plan-md`、`/chat`、`/pin`、`/clear`、`/model`、`/tool`、`/search`、`/help`），方向键 + Enter 确认，Esc 关闭；命令执行后 **不把 `/command` 本身发给后端**（除非命令需要 content）。
6. **其他打磨**：顶栏缩小、Inspector 三个按钮合并下拉、`ChatModeBanner` 去掉、Composer 下方按钮瘦身等由设计阶段决定。

本 feature 在 **不变更后端 SSE 契约、不新增 runtime 依赖、不重写其他页面** 的前提下完成以上打磨。所有改动限定在 `apps/agent-console/` 内部。`useWorkspaceStore`、`AgentChatStreamEvent`、`streamAgentChatRun` 保持向后兼容（可 additive 扩展字段 / action）。v1 + v2 已落地的 15+1 property-based 测试必须继续全绿。

## Glossary

（复用 v1 / v2 定义，以下为本轮新增或语义变更的术语）

- **Workspace**: 路由 `/agents/:agentId/workspace` 对应的页面。
- **Chat_Surface**: `apps/agent-console/src/features/agents/components/ChatSurface.tsx` 渲染的主容器。
- **Conversation_Summary**: v3 新增的历史对话条目，结构 `{ id, title, created_at, updated_at, nodesById, rootNodeId, activeLeafId, pinnedNodeIds, dismissedPlanNodeIds, draft, contextWindowTurns }`；每条对应 `useWorkspaceStore` 的一份完整快照。
- **Conversation_Title**: 会话标题；默认取首条 `role = user` 的 `ConversationNode.content` 前 40 字符；若还没有 user 消息则显示 `"New conversation" / "新对话"`。
- **History_Panel**: v3 新增组件 `ConversationHistoryPanel`，渲染在 `Chat_Surface` 左侧的可折叠抽屉（默认展开 260px，可收起到 0）。包含顶部「新建对话」按钮、对话列表（按 `updated_at` 倒序）、每项提供「删除」图标。
- **Current_Conversation_Id**: `useWorkspaceStore` 新增字段 `currentConversationId: string`，指向当前活跃的 `Conversation_Summary.id`。
- **Slash_Menu**: v3 新增组件 `SlashCommandMenu`，悬浮在 `Workspace_Composer` textarea 上方，触发条件为 `draft` 以 `/` 开头（光标在 draft 内任意位置均可，只要前缀为 `/`）。
- **Slash_Command**: Slash 菜单的一项，包含 `name`（`"plan" | "plan-md" | "chat" | "pin" | "clear" | "model" | "tool" | "search" | "help"` 等）、`aliases`（例如 `plan-md → plan`）、`args`（是否需要参数）、`description.zh / description.en`。
- **Slash_Parse_Result**: 纯函数 `parseSlashCommand(draft)` 的返回，`{ kind: "none" } | { kind: "matching", prefix, query, candidates } | { kind: "confirmed", command, args, restDraft }`；第三种表示 draft 已满足 `"/cmd<space>...` 或被显式 Enter 触发，可以分派动作。
- **Composer_Autogrow**: Composer 的 textarea 自动高度：初始 `min-height: 40px`（单行）、内容撑高到 `max-height: 200px`、超过内部滚动。实现机制是 `onChange` 读 `scrollHeight` 并写回 `style.height`。
- **Scroll_Sentinel**: `ChatMessageList` 末尾的零高度 `<div>`，用 `IntersectionObserver(root=scrollContainer, threshold=0)` 监测是否可见；可见 → `autoFollow = true`；不可见 + 离底 > 200px → 显示「跳到最新」按钮。
- **Jump_To_Latest_Button**: 悬浮在消息列表右下的 icon-only 按钮，点击后 `scrollToBottom({behavior: "smooth"})` 并重新激活 `autoFollow`。
- **Metadata_Strip_Secondary**: 从 `TopMetaBar` 迁移到 `Composer_Toolbar` 上方（或 Toolbar 同行次要位置）的次要 metadata 行。字段与 v2 相同（In/Out/Cost/TTFB/Duration/Run hash）。
- **Inspector_Menu**: 由 v2 `TopMetaBar` 三个独立按钮（Metadata / Artifacts / Runtime）合并而成的单按钮下拉（Req 24）。
- **Persistence_Key_V3**: 新的分区 localStorage 键 `harness.workspace.v3.<agentId>.conversations`，存储 `Conversations_Snapshot { version: 2, conversations: Conversation_Summary[], currentConversationId: string }`。
- **Legacy_Migration**: 读取 v2 的 `harness.workspace.v2.<agentId>` 键值，若存在则迁移为单条初始 `Conversation_Summary`（id 新生成，title 取首条 user 消息前 40 字符或 `"Imported"`），持久化到 v3 key 后清除 v2 key。

## Requirements

### Requirement 1: Composer 自动增高

**User Story:** As Workspace 使用者, I want Composer 默认只有一行高度并随我输入自动增高, so that 首屏 Composer 不遮挡对话、长输入也能完整显示。

#### Acceptance Criteria

1. THE Workspace_Composer 的 `<textarea>` 的初始最小高度 SHALL ≤ 44 像素（单行 + 一行内边距），不使用 v2 的 `min-h-24`（96px）。
2. WHEN 用户在 Composer 输入内容致使 `scrollHeight` 大于当前 `style.height`, THE Workspace_Composer SHALL 自动把 `<textarea>` 的 `style.height` 扩展到 `scrollHeight` 对应的像素值，但不得超过 200 像素的最大高度。
3. WHEN `<textarea>` 内容 `scrollHeight` 超过 200 像素, THE Workspace_Composer SHALL 保持 `<textarea>` 的 `style.height` 为 200 像素，并在内部显示垂直滚动条（CSS `overflow-y: auto`）。
4. WHEN 用户删除内容致使 `scrollHeight` 变小, THE Workspace_Composer SHALL 同步收缩 `<textarea>` 的 `style.height`，但不得小于第 1 条的最小高度。
5. WHEN 用户 `draft` 被外部动作（例如 Plan「修改规划」/ Slash 命令 / 恢复历史对话）设置, THE Workspace_Composer SHALL 在随后一帧内同步调整 `<textarea>` 高度以匹配新内容。
6. THE Workspace_Composer SHALL 保留"Enter 发送 · Shift+Enter 换行"的双语提示文本，位置可调整但不得移除。

### Requirement 2: 自动跟随滚动修复

**User Story:** As Workspace 使用者, I want 对话页面随流式输出持续自动滚到底部, so that 我不用自己手动下拉就能看到模型最新 tokens。

#### Acceptance Criteria

1. WHEN `Active_Path` 末端 `ConversationNode.content` 增长（无论因 `delta` 事件还是 `appendNode`）, THE ChatMessageList SHALL 在 React commit 之后同步将滚动容器 `scrollTop` 设为 `scrollHeight - clientHeight`（即贴底），前提是用户当前处于"自动跟随"状态（见第 3 条）。
2. THE ChatMessageList SHALL 使用 `useLayoutEffect`（而非 `useEffect`）+ 对 `ConversationNode.content` 长度求和的依赖项，保证对 `content` 增量的敏感度不低于 v2 的 `pathLength + lastContentLength` 阈值。
3. THE ChatMessageList SHALL 在容器底部挂一个零高度的 `Scroll_Sentinel`，并用 `IntersectionObserver(root=scrollContainer, threshold=0, rootMargin="0px")` 观察其可见性：SHALL `autoFollow = entry.isIntersecting`。用户主动向上滚动（sentinel 离开视口）→ `autoFollow = false`；用户再次滚到底部使 sentinel 可见 → `autoFollow = true`。
4. WHILE `autoFollow = false` 且 sentinel 距离视口底部 ≥ 200 像素, THE ChatMessageList SHALL 显示 `Jump_To_Latest_Button`（固定定位在右下，`aria-label` 双语"跳到最新 / Jump to latest"）。
5. WHEN 用户点击 `Jump_To_Latest_Button`, THE ChatMessageList SHALL 调用 `scrollContainer.scrollTo({ top: scrollHeight, behavior: "smooth" })` 并重置 `autoFollow` 为 `true`。
6. WHEN `autoFollow = true` 且 `ConversationNode.content` 长度增加, THE ChatMessageList SHALL 在下一帧（`useLayoutEffect` 回调）内将 `scrollTop` 设为 `scrollHeight - clientHeight`。
7. THE ChatMessageList SHALL 不得在流式进行中错误地把 `scrollTop` 强制拉回底部当用户已经向上滚走（即违反第 3、4 条的观察判定）。

### Requirement 3: Metadata 位置迁移

**User Story:** As Workspace 使用者, I want Metadata 不在顶栏以徽标形式大号出现，而是作为次要信息靠近 Composer, so that 顶部更干净、我需要看 metadata 时又近在手边。

#### Acceptance Criteria

1. THE TopMetaBar SHALL 不再渲染 `MetadataStrip` 子组件（即 v2 的"header 第二行 = metadata strip"被移除）。
2. THE ChatSurface SHALL 在 `Composer_Toolbar` 紧邻上方、或 Toolbar 内部底部一行的次要位置渲染 `Metadata_Strip_Secondary`，字段与 v2 相同（In / Out / Cost / TTFB / Duration / Run 短哈希）。
3. THE Metadata_Strip_Secondary SHALL 使用 `text-[11px]` 或等价的更小字号，并使用 `text-slate-400/500` 等更低饱和色，不与其他 toolbar 控件争视觉焦点。
4. THE Metadata_Strip_Secondary SHALL 保持对 `Active_Path` 末端 `ConversationNode.metadata` 的实时绑定（Property P8 v2 不变）。
5. IF 视口宽度 < 640 像素, THEN THE Metadata_Strip_Secondary SHALL 允许 CSS `overflow-x-auto` 横向滚动或隐藏部分字段，不触发页面级横向滚动条。
6. THE TopMetaBar SHALL 保持 Property P10 的 `Stop_Button` 可见性契约不变（`activeStream !== null` 时显示）。

### Requirement 4: 多对话历史记录

**User Story:** As Workspace 使用者, I want 左侧有一个历史对话列表可以切换, so that 我不会失去之前的上下文、可以同一 Agent 下并行多条主题。

#### Acceptance Criteria

1. THE Workspace SHALL 在 `Chat_Surface` 左侧渲染 `History_Panel`，默认展开宽度 260 像素，默认在视口宽度 ≥ 1024 像素时展开，< 1024 像素时默认收起。
2. THE History_Panel SHALL 在顶部显示「新建对话 / New conversation」按钮（double-digit 像素级 icon + 文案），点击后创建一个全新的 `Conversation_Summary`（空 `nodesById`、`activeLeafId = rootNodeId`、空 pinned、空 dismissed、空 draft），并把 `currentConversationId` 设为新条目的 id。
3. THE History_Panel SHALL 以 `updated_at` 倒序渲染 `Conversation_Summary` 列表。
4. THE History_Panel SHALL 对当前 `currentConversationId` 对应的条目应用高亮（例如 `bg-slate-100` 或 `ring-1 ring-slate-300`），以区别于其他条目。
5. WHEN 用户点击历史对话条目, THE Workspace SHALL 把 `useWorkspaceStore` 的 `nodesById / rootNodeId / activeLeafId / pinnedNodeIds / dismissedPlanNodeIds / contextWindowTurns / draft` 原子地换成目标 `Conversation_Summary` 的快照，并更新 `currentConversationId`；THE Workspace SHALL 不触发后端请求。
6. THE History_Panel 的每个条目 SHALL 提供"删除"按钮（hover / focus 可见），点击后：
   - IF 被删的是当前 `currentConversationId`, THEN THE Workspace SHALL 删除该条目并自动切到列表中 `updated_at` 最新的另一条；IF 列表中只剩 1 条（被删后为空）, THEN THE Workspace SHALL 创建一条新的空对话并切换过去（保持始终至少存在 1 条）。
   - ELSE THE Workspace SHALL 仅删除该条目，不切换当前对话。
7. THE History_Panel SHALL 提供收起按钮（可选：通过顶部 X 或 折叠菜单按钮），收起后宽度变为 0，`Chat_Surface` 主列填满剩余宽度；收起状态 SHALL 持久化到 `localStorage`（键 `harness.workspace.v3.<agentId>.historyPanelCollapsed`）。
8. WHEN 用户首次发送 user 消息时（对应 `Conversation_Summary` 的 `title` 仍为默认）, THE Workspace SHALL 自动以 `ConversationNode.content.trim().slice(0, 40)` 更新 `Conversation_Summary.title`；后续消息不再覆盖 title（允许未来增加"重命名"但不在本 feature 范围）。
9. THE Workspace SHALL 在 `nodesById / activeLeafId / pinnedNodeIds / dismissedPlanNodeIds / draft / contextWindowTurns` 任一变化时（v2 的 300ms debounce 仍然有效），把对应字段同步回 `Conversation_Summary`（以 `currentConversationId` 匹配），并把整个 `Conversations_Snapshot` 持久化到 `Persistence_Key_V3`。
10. THE Workspace SHALL 在组件挂载时读取 `Persistence_Key_V3`：
    - IF 存在, THEN THE Workspace SHALL 加载 conversations 列表并恢复 `currentConversationId` 指向的快照（`state === "streaming"` 的节点 SHALL 被重写为 `"paused"`，与 v2 Property P11 一致）。
    - ELSE IF 存在 v2 key `harness.workspace.v2.<agentId>`, THEN THE Workspace SHALL 做一次 `Legacy_Migration`：把 v2 快照转为单条 `Conversation_Summary`，持久化到 `Persistence_Key_V3`，并从 localStorage 清除 v2 key。
    - ELSE THE Workspace SHALL 创建一条空的初始 `Conversation_Summary` 作为起点。
11. IF `localStorage` 不可用（禁用 / 配额超限）, THEN THE Workspace SHALL 降级为仅内存模式（单条对话），与 v2 Req 12.3 的语义一致。

### Requirement 5: Slash 命令

**User Story:** As Workspace 使用者, I want 在 Composer 输入 `/` 就能弹出命令菜单切换模式或执行动作, so that 我不用在工具栏找按钮、也能不把 `/command` 文本直接发给后端。

#### Acceptance Criteria

1. WHEN `draft` 的第一个字符为 `/` 且 `draft` 不包含换行, THE Workspace_Composer SHALL 显示 `Slash_Menu` 悬浮在 textarea 上方。
2. THE Slash_Menu SHALL 包含以下命令（双语 description）：
   - `/plan` → 切换 `Workspace_Mode = "plan"`（Plan-Act Run）。
   - `/plan-md` → 切换 `Workspace_Mode = "markdown_plan"`（Plan markdown）。
   - `/chat` → 切换 `Workspace_Mode = "chat"`。
   - `/pin` → 把 `Active_Path` 末端 `ConversationNode`（若存在）pin 到 `pinnedNodeIds`。
   - `/clear` → 触发与「清空对话」相同的二次确认后清空当前 `Conversation_Summary`（等价于调用 `useWorkspaceStore.reset()`）。
   - `/model` → 打开 `Model_Picker` 下拉。
   - `/tool <name>` → 向 `draft` 插入 `@<name> ` 提及。
   - `/search` → 打开 `Search_Overlay`。
   - `/help` → 打开 `Shortcut_Overlay`。
3. THE Slash_Menu SHALL 根据 `/` 后的前缀过滤命令候选（例如 `/pl` → 只显示 `/plan`、`/plan-md`），大小写不敏感，支持别名匹配。
4. WHEN 用户按 `ArrowDown` / `ArrowUp`, THE Slash_Menu SHALL 在候选项间循环切换高亮。
5. WHEN 用户按 `Enter`（在 Slash_Menu 可见时）, THE Workspace SHALL:
   - 如高亮项无 `args`（如 `/plan`、`/chat`、`/pin`、`/clear`、`/model`、`/search`、`/help`）→ 分派对应动作并从 `draft` 中移除整个 `/command` 前缀（以及其后的第一个空格），清空 `draft`（若 `draft` 只有 `/command`），不触发 `stream.start`；SHALL 不把 `/command` 文本作为 goal 发给后端。
   - 如高亮项有 `args`（`/tool`）→ 若当前 draft 已经形如 `/tool <name>` 或 `/tool <name> <rest>`, 则解析 `<name>` 并分派 `onInsertMention(<name>)`，把 draft 中的 `/tool <name>` 替换为 `@<name> `；若 draft 仍是 `/tool` 或 `/tool `（没有 name），SHALL 保持 menu 打开并不发送。
6. WHEN 用户按 `Escape`（Slash_Menu 可见时）, THE Slash_Menu SHALL 关闭，不修改 `draft`，并把焦点返回 textarea。
7. WHEN 用户按 `Tab`（Slash_Menu 可见时）, THE Slash_Menu SHALL 用高亮命令的完整名称（带一个尾随空格）替换 draft 中当前的 `/prefix`（允许用户继续输入参数，如 `/tool curl`）。
8. WHEN Slash_Menu 可见时 THE Workspace_Composer SHALL 拦截 `ArrowDown`、`ArrowUp`、`Enter`、`Escape`、`Tab` 五个按键，不让其触发默认 composer 语义（例如 Enter 不提交对话）。
9. WHEN `draft` 第一个字符不是 `/`，或 draft 中已经含换行, THE Slash_Menu SHALL 关闭，且 composer 恢复正常键绑定。
10. WHEN 用户按下 `Enter` 且 draft 是 `/cmd <extra>` 形式（即 `/cmd ` 后有内容），但 `cmd` 无 args, THE Workspace SHALL 忽略 `<extra>`、仅分派 `cmd` 对应动作、清空 draft。
11. THE Slash_Menu SHALL 通过 `useI18n().text(zh, en)` 渲染所有命令描述、空态与标题；所有候选行 SHALL 在 Tab 顺序中可达、聚焦时有 `focus-visible` 环。

### Requirement 6: 布局精简与次要打磨

**User Story:** As Workspace 使用者, I want 顶栏更紧凑、Inspector 三按钮合并、Mode Badge 通过 slash 命令暗示而不用显式大徽标, so that 我在聊天主流程中视觉干扰更少。

#### Acceptance Criteria

1. THE TopMetaBar SHALL 以单行紧凑形式展示 `agentName + modelLabel + streaming 徽标 + Run Detail 按钮`；v2 的两行布局（meta 行 + metadata strip 行）SHALL 合并为一行（metadata strip 已迁移到 Composer 上方）。
2. THE TopMetaBar SHALL 合并 v2 的三个 Inspector 按钮（Metadata / Artifacts / Runtime）为一个 `Inspector_Menu` 下拉：默认显示一个 "Inspector" 按钮，点击后弹出三行菜单项（Metadata / Artifacts / Runtime），点击任一项打开 `Inspector_Drawer` 到对应 section。
3. THE ChatSurface SHALL 不再渲染 `ChatModeBanner`（v3 靠 `/chat`、`/plan`、`/plan-md` slash 命令 + 顶栏 mode badge 表达当前模式；`ChatModeBanner` 组件文件保留但不再从 `ChatSurface` 挂载，以减少 diff 面积）。
4. THE TopMetaBar 的 `Workspace_Mode` badge 在 `Workspace_Mode = "chat"` 时 SHALL 隐藏；仅在 `plan` / `markdown_plan` 时显示。
5. THE ChatSurface SHALL 保持 Property P1（无 `max-w-3xl` 等宽度约束）、P8（MetadataStrip 字段实时绑定）、P10（Stop button 可见性）、P11（持久化刷新安全）等 v2 不变量。
6. THE ChatWelcomeState SHALL 保留现有 3 个示例 prompt 卡片；不再新增额外卡片（瘦身）。
7. THE Workspace_Composer SHALL 不再在 `<textarea>` 正下方显示 mode badge 的圆形切换 chip；模式切换通过 slash 命令完成。v2 的 `ModeOption` radiogroup UI SHALL 移除。
8. THE ChatSurface 组件 SHALL 不依赖 `ChatModeBanner`（允许保留 import 用于类型，但不在 JSX 中渲染）。

### Requirement 7: 国际化与可访问性（v3 增量）

**User Story:** As 多语言 Workspace 使用者, I want v3 新增的所有控件保持中英双语与键盘可达, so that i18n / a11y 不倒退。

#### Acceptance Criteria

1. THE Workspace SHALL 通过 `useI18n().text(zh, en)` 为 v3 新增的所有可见文案提供中英双语：`History_Panel`（标题、按钮、删除提示、空态）、`Slash_Menu`（每条命令描述、空态、提示）、`Jump_To_Latest_Button`（aria-label）、`Metadata_Strip_Secondary`（复用 v2 双语）。
2. THE History_Panel、Slash_Menu、Jump_To_Latest_Button、Inspector_Menu SHALL 在键盘 Tab 顺序中可达，聚焦时呈现 `focus-visible` 环。
3. THE Slash_Menu SHALL 对视障用户通过 `role="listbox"` / `aria-activedescendant` / 或等价 ARIA 语义宣告当前高亮项；双语 `aria-label` 放在菜单根元素。
4. THE Jump_To_Latest_Button SHALL 使用 icon-only + 双语 `aria-label`，不使用纯表情符号。

### Requirement 8: 非功能性约束（v3 增量）

**User Story:** As Harness 维护者, I want v3 不破坏现有编译门禁、不新增依赖、不改后端契约, so that 合并后无须协同升级其他模块。

#### Acceptance Criteria

1. THE Workspace SHALL 不引入除 `apps/agent-console/package.json` 已声明以外的任何 runtime 依赖。
2. THE Workspace SHALL 不修改 `POST /api/agents/:agentId/runs/chat/stream` 的请求方法、URL、请求体字段或 `AgentChatStreamEvent` 事件集合。
3. THE Workspace SHALL 保持 `useWorkspaceStore` 的既有字段（v1 + v2 已声明）形状向后兼容；本 feature 允许 additive 新增字段（`conversations`、`currentConversationId`、`historyPanelCollapsed`）与 additive actions（`newConversation`、`setCurrentConversation`、`deleteConversation`、`renameConversation`、`setHistoryPanelCollapsed`），SHALL 不删除、不重命名、不更改 v1 / v2 字段的语义。
4. THE Workspace SHALL 通过 `apps/agent-console` 现有的 TypeScript 严格模式编译，不新增 `any`、`as any` 或 `@ts-ignore` / `@ts-expect-error`。
5. THE Workspace SHALL 保持 v1 + v2 已通过的所有属性测试（15 条 + 1 条支撑）继续全绿；新增的 v3 纯函数（`parseSlashCommand`、`sortConversationsByUpdatedAt`、`legacyMigration`）SHALL 额外编写属性测试，使总数 ≥ 19 条。
6. THE Workspace SHALL 在首屏 1 秒内完成 `Chat_Surface` + `History_Panel` 骨架渲染，不阻塞等待 `getModelSettings` / `getToolRegistry` 返回。
7. THE Workspace SHALL 不改变 `/agents/:agentId/workspace` 的 URL 或其在 `apps/agent-console/src/app/routes.tsx` 中的声明位置。

### Requirement 9: 正确性属性（交叉验证）

**User Story:** As Harness 质量工程师, I want 一组可执行的不变量覆盖本次 UX 打磨的关键行为, so that PR 门禁可以用属性测试自动校验。

#### Acceptance Criteria

1. **P12 Slash parser total**: `parseSlashCommand(draft)` SHALL 对任意字符串输入 TOTAL（不抛异常），且对以 `/` 开头的 draft 返回 `{ kind: "matching" | "confirmed", ... }`，对其他任意 draft 返回 `{ kind: "none" }`。
2. **P13 Slash confirmation idempotence**: 对任意确认字符串 `"/cmd"` 或 `"/cmd <args>"`, 连续两次解析 `parseSlashCommand(s)` SHALL 返回深等价的结果（纯函数）。
3. **P14 Slash parser does not keep slash**: WHEN `parseSlashCommand(draft).kind === "confirmed"`, THE `result.restDraft` SHALL 不包含形如 `"/<commandName>"` 的前缀，且 `result.args` 在命令无参时 SHALL 为空字符串。
4. **P15 Conversation sort stability**: `sortConversationsByUpdatedAt(list)` SHALL 对任意 `Conversation_Summary[]` 输入按 `updated_at` 倒序排序，并对 `updated_at` 相同的两条保持输入中的相对顺序稳定。
5. **P16 Conversation switch preserves snapshots**: WHEN 用户从 `currentConversationId = A` 切到 `B` 再切回 `A`, THE `Conversation_Summary` A 的 `nodesById / activeLeafId / pinnedNodeIds / dismissedPlanNodeIds / draft / contextWindowTurns` SHALL 与切换前深等价（没有任何字段丢失）。
6. **P17 Legacy migration determinism**: `legacyMigration(v2Snapshot, now)` SHALL 对任意合法 v2 `PersistedSnapshot` 输出一个单元素 `Conversation_Summary[]`，该元素的 `nodesById / rootNodeId / activeLeafId / pinnedNodeIds / dismissedPlanNodeIds / draft / contextWindowTurns` 与 v2 snapshot 一致（`state === "streaming"` 节点已被重写为 `"paused"`），`title` 来自首条 user 消息前 40 字符或兜底字符串。
7. **P18 Autogrow bounded**: THE Composer textarea 的 `style.height` SHALL 始终 ∈ [40, 200] 像素区间（闭区间）；超过 200 时以 200 为上限 + 内部滚动。
8. **P19 Auto-scroll follow state**: WHILE `autoFollow === true`, `ChatMessageList` 在每次 `content` 长度增加后的 layout commit 完成时 SHALL 满足 `scrollHeight - scrollTop - clientHeight ≤ 4`（像素级贴底，允许 4px 误差）；WHILE `autoFollow === false`, `ChatMessageList` SHALL 不修改 `scrollTop`。

## Out of Scope

1. **后端 SSE 契约变更**：不修改 `POST /api/agents/:agentId/runs/chat/stream` 的请求体字段、响应事件集合或语义。
2. **反向代理配置修改**：本 feature 不修改任何 Nginx / Ingress / 云厂商网关的实际配置。
3. **Run Detail / Eval / Observability / Tools / Sandboxes / Subagents 页面重构**。
4. **新增 runtime 依赖**。
5. **富媒体输入**（图片粘贴、文件上传、语音输入）。
6. **对话标题手动重命名 UI**（仅自动取首条 user 消息前 40 字符；未来可加）。
7. **多窗口或跨 tab 实时同步**（localStorage 同步事件跨 tab 传播不在本轮保证范围）。
8. **Slash 命令的自定义扩展点**（硬编码 9 条；未来再抽象插件 API）。
